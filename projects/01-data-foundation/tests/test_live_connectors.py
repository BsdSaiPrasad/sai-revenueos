"""Mocked acceptance scenarios for P1.6 live connector behavior."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from collections import deque
from pathlib import Path
from typing import Any, Mapping, Optional


PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
sys.path.insert(0, str(SRC))

from sai_revenueos_connectors import (  # noqa: E402
    ApiRequestError,
    ConfigurationError,
    HttpResponse,
    HubSpotAccessToken,
    HubSpotConnector,
    JsonHttpClient,
    LiveIngestionRunner,
    RequestTrace,
    RetryPolicy,
    SalesforceConnector,
    SalesforceOAuthFile,
    StaticSalesforceToken,
    VendorRecord,
)
from sai_revenueos_identity import IdentityStore  # noqa: E402
from sai_revenueos_sources import SourceStore, standardize_event  # noqa: E402


def response(document: object, status: int = 200, headers: Optional[Mapping[str, str]] = None) -> HttpResponse:
    return HttpResponse(status, headers or {}, json.dumps(document).encode("utf-8"))


class QueueTransport:
    """Capture outgoing requests and return queued responses or failures."""

    def __init__(self, replies: list[object]) -> None:
        self.replies = deque(replies)
        self.requests: list[dict[str, Any]] = []

    def request(self, method: str, url: str, headers: Mapping[str, str], body: Optional[bytes], timeout: float):
        self.requests.append({"method": method, "url": url, "headers": dict(headers), "body": body})
        if not self.replies:
            raise AssertionError("no queued response for %s %s" % (method, url))
        reply = self.replies.popleft()
        if isinstance(reply, Exception):
            raise reply
        return reply


def client(transport: QueueTransport, traces: Optional[list[RequestTrace]] = None, sleeps: Optional[list[float]] = None):
    return JsonHttpClient(
        transport=transport,
        retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=1, max_delay_seconds=8, jitter_ratio=0),
        sleep=(sleeps if sleeps is not None else []).append,
        random_source=lambda: 0,
        trace=(traces if traces is not None else []).append,
    )


def sf_connector(transport: QueueTransport, **kwargs: object) -> SalesforceConnector:
    return SalesforceConnector(
        StaticSalesforceToken("sf-secret-token", "https://example.my.salesforce.com", "00DTEST"),
        http=client(transport, **kwargs),
        api_version="v68.0",
    )


def hs_connector(transport: QueueTransport, **kwargs: object) -> HubSpotConnector:
    return HubSpotConnector(
        HubSpotAccessToken("hs-secret-token", "123456"),
        http=client(transport, **kwargs),
        api_version="2026-09",
    )


class HttpReliabilityTests(unittest.TestCase):
    def test_01_rate_limit_uses_retry_after_then_succeeds(self) -> None:
        """HTTP 429 waits for Retry-After and remains within the attempt bound."""
        transport = QueueTransport([
            response({"message": "slow down"}, 429, {"Retry-After": "2"}),
            response({"ok": True}),
        ])
        sleeps: list[float] = []
        result = client(transport, sleeps=sleeps).request_json("GET", "https://vendor.example/records")
        self.assertEqual({"ok": True}, result)
        self.assertEqual([2.0], sleeps)
        self.assertEqual(2, len(transport.requests))

    def test_02_errors_and_traces_do_not_expose_bearer_tokens(self) -> None:
        """A vendor echo cannot leak the supplied token into diagnostics."""
        traces: list[RequestTrace] = []
        transport = QueueTransport([response({"message": "bad token hs-secret-token"}, 401)])
        with self.assertRaises(ApiRequestError) as caught:
            client(transport, traces=traces).request_json(
                "GET", "https://vendor.example/records", headers={"Authorization": "Bearer hs-secret-token"}
            )
        self.assertNotIn("hs-secret-token", str(caught.exception))
        self.assertNotIn("hs-secret-token", repr(traces))

    def test_03_network_failures_use_exponential_backoff_and_stop(self) -> None:
        """Transient connection errors retry twice and then surface one safe error."""
        transport = QueueTransport([OSError("reset"), OSError("reset"), OSError("reset")])
        sleeps: list[float] = []
        with self.assertRaises(ApiRequestError):
            client(transport, sleeps=sleeps).request_json("GET", "https://vendor.example/records")
        self.assertEqual([1.0, 2.0], sleeps)
        self.assertEqual(3, len(transport.requests))


class SalesforceConnectorTests(unittest.TestCase):
    def test_04_initial_sync_follows_query_pagination_and_fetches_full_records(self) -> None:
        """Salesforce QueryAll page cursors lead to complete source-native record reads."""
        first = {"Id": "001A", "Name": "Globex", "LastModifiedDate": "2026-10-12T12:00:00Z", "IsDeleted": False}
        second = {"Id": "001B", "Name": "Northstar", "LastModifiedDate": "2026-10-12T12:01:00Z", "IsDeleted": False}
        transport = QueueTransport([
            response({"records": [{"Id": "001A", "LastModifiedDate": first["LastModifiedDate"], "IsDeleted": False}], "nextRecordsUrl": "/services/data/v68.0/query/next"}),
            response(first),
            response({"records": [{"Id": "001B", "LastModifiedDate": second["LastModifiedDate"], "IsDeleted": False}], "done": True}),
            response(second),
        ])
        records = list(sf_connector(transport).fetch_records("Account", "initial", None, "2026-10-12T13:00:00Z"))
        self.assertEqual(["001A", "001B"], [record.object_id for record in records])
        self.assertEqual("Globex", records[0].payload["Name"])
        self.assertIn("/query/next", transport.requests[2]["url"])

    def test_05_incremental_sync_combines_updated_and_deleted_records(self) -> None:
        """Salesforce replication endpoints produce upserts and deletion tombstones."""
        updated = {"Id": "001A", "Name": "Globex v2", "LastModifiedDate": "2026-10-12T12:30:00Z", "IsDeleted": False}
        transport = QueueTransport([
            response({"ids": ["001A"], "latestDateCovered": "2026-10-12T13:00:00Z"}),
            response(updated),
            response({"deletedRecords": [{"id": "001B", "deletedDate": "2026-10-12T12:45:00Z"}]}),
        ])
        records = list(sf_connector(transport).fetch_records(
            "Account", "incremental", "2026-10-12T12:00:00Z", "2026-10-12T13:00:00Z"
        ))
        self.assertEqual(["upsert", "delete"], [record.event_type for record in records])
        self.assertEqual(
            {"id": "001B", "deletedDate": "2026-10-12T12:45:00Z"},
            records[1].payload["SalesforceDeletedRecord"],
        )
        self.assertTrue(standardize_event(records[1].to_event(records[1].source_updated_at))["is_deleted"])

    def test_06_seed_refuses_an_unmarked_salesforce_collision(self) -> None:
        """The explicit test seeder never adopts or modifies a normal Account."""
        transport = QueueTransport([response({"records": [{
            "Id": "001REAL", "Website": "https://globex-p16.invalid", "Description": "normal account", "IsDeleted": False,
        }], "done": True})])
        with self.assertRaises(ConfigurationError):
            sf_connector(transport).ensure_globex_test_account()

    def test_07_salesforce_seed_is_repeatable_and_updates_only_marked_record(self) -> None:
        """Create, confirm, and update reuse one explicitly marked fictional Account."""
        marked = {
            "Id": "001TEST", "Name": "[SAI TEST] Globex Health",
            "Website": "https://globex-p16.invalid", "Description": "SAI_REVENUEOS_P16_TEST_ONLY",
            "LastModifiedDate": "2026-10-12T12:00:00Z", "IsDeleted": False,
        }
        changed = {**marked, "Name": "[SAI TEST] Globex Health - Updated", "LastModifiedDate": "2026-10-12T12:01:00Z"}
        transport = QueueTransport([
            response({"records": [], "done": True}),
            response({"id": "001TEST", "success": True}, 201), response(marked),
            response({"records": [marked], "done": True}), response(marked),
            response(marked), response({}, 204), response(changed),
        ])
        connector = sf_connector(transport)
        self.assertEqual("001TEST", connector.ensure_globex_test_account()["Id"])
        self.assertEqual("001TEST", connector.ensure_globex_test_account()["Id"])
        result = connector.update_globex_test_name("001TEST", changed["Name"])
        self.assertEqual(changed["Name"], result["Name"])
        self.assertEqual(1, sum(item["method"] == "POST" and item["url"].endswith("/Account/") for item in transport.requests))

    def test_08_salesforce_refresh_rotates_tokens_in_ignored_local_file(self) -> None:
        """OAuth refresh replaces rotated values without printing or committing them."""
        with tempfile.TemporaryDirectory(prefix="p16-oauth-") as temp:
            path = Path(temp) / "salesforce.json"
            path.write_text(json.dumps({
                "client_id": "client-id", "refresh_token": "old-refresh",
                "access_token": "old-access", "instance_url": "https://old.example",
                "tenant": "00DTEST", "login_url": "https://login.salesforce.com",
            }), encoding="utf-8")
            transport = QueueTransport([response({
                "access_token": "new-access", "refresh_token": "new-refresh",
                "instance_url": "https://new.example",
            })])
            provider = SalesforceOAuthFile(path, http=client(transport))
            self.assertEqual("new-access", provider.access_token(force_refresh=True))
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual("new-refresh", saved["refresh_token"])
            self.assertEqual("https://new.example", provider.instance_url)
            self.assertEqual(0o600, path.stat().st_mode & 0o777)


class HubSpotConnectorTests(unittest.TestCase):
    def test_09_initial_sync_paginates_active_and_archived_objects(self) -> None:
        """HubSpot paging cursors and archived records become ordered source versions."""
        active_a = {"id": "10", "properties": {"name": "Globex"}, "updatedAt": "2026-10-12T12:00:00Z", "archived": False}
        active_b = {"id": "11", "properties": {"name": "Northstar"}, "updatedAt": "2026-10-12T12:01:00Z", "archived": False}
        archived = {"id": "12", "properties": {}, "updatedAt": "2026-10-11T12:00:00Z", "archived": True, "archivedAt": "2026-10-12T12:02:00Z"}
        transport = QueueTransport([
            response({"results": [active_a], "paging": {"next": {"after": "10"}}}),
            response({"results": [active_b]}),
            response({"results": [archived]}),
        ])
        records = list(hs_connector(transport).fetch_records("Company", "initial", None, "2026-10-12T13:00:00Z"))
        self.assertEqual(["10", "11", "12"], [record.object_id for record in records])
        self.assertEqual("delete", records[-1].event_type)
        self.assertIn("after=10", transport.requests[1]["url"])

    def test_10_incremental_search_filters_active_and_archived_windows(self) -> None:
        """HubSpot search returns changes while archived polling detects deletions."""
        changed = {"id": "10", "properties": {"name": "Globex v2"}, "updatedAt": "2026-10-12T12:30:00Z", "archived": False}
        old_archive = {"id": "11", "properties": {}, "updatedAt": "2026-10-01T00:00:00Z", "archived": True, "archivedAt": "2026-10-01T01:00:00Z"}
        new_archive = {"id": "12", "properties": {}, "updatedAt": "2026-10-10T00:00:00Z", "archived": True, "archivedAt": "2026-10-12T12:45:00Z"}
        transport = QueueTransport([
            response({"results": [changed]}),
            response({"results": [old_archive, new_archive]}),
        ])
        records = list(hs_connector(transport).fetch_records(
            "Company", "incremental", "2026-10-12T12:00:00Z", "2026-10-12T13:00:00Z"
        ))
        self.assertEqual(["10", "12"], [record.object_id for record in records])
        self.assertEqual("POST", transport.requests[0]["method"])
        self.assertIn("hs_lastmodifieddate", transport.requests[0]["body"].decode())

    def test_11_seed_refuses_an_unmarked_hubspot_collision(self) -> None:
        """The HubSpot seeder rejects an existing normal Company on the test domain."""
        transport = QueueTransport([response({"results": [{
            "id": "99", "properties": {"domain": "globex-p16.invalid", "description": "normal company"},
        }]})])
        with self.assertRaises(ConfigurationError):
            hs_connector(transport).ensure_globex_test_company()

    def test_12_hubspot_seed_is_repeatable_and_updates_only_marked_record(self) -> None:
        """Create, confirm, and update reuse one explicitly marked fictional Company."""
        marked = {
            "id": "101", "properties": {
                "name": "[SAI TEST] Globex Health", "domain": "globex-p16.invalid",
                "description": "SAI_REVENUEOS_P16_TEST_ONLY",
            },
            "updatedAt": "2026-10-12T12:00:00Z", "archived": False,
        }
        changed = json.loads(json.dumps(marked))
        changed["properties"]["name"] = "[SAI TEST] Globex Health - Updated"
        changed["updatedAt"] = "2026-10-12T12:01:00Z"
        transport = QueueTransport([
            response({"results": []}), response({"id": "101"}, 201), response(marked),
            response({"results": [marked]}), response(marked),
            response(marked), response(changed), response(changed),
        ])
        connector = hs_connector(transport)
        self.assertEqual("101", connector.ensure_globex_test_company()["id"])
        self.assertEqual("101", connector.ensure_globex_test_company()["id"])
        result = connector.update_globex_test_name("101", changed["properties"]["name"])
        self.assertEqual(changed["properties"]["name"], result["properties"]["name"])
        self.assertEqual(1, sum(item["method"] == "POST" and item["url"].endswith("/companies") for item in transport.requests))


class LiveRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="p16-tests-")
        root = Path(self.temp.name)
        self.identity = IdentityStore(str(root / "identity.sqlite3"))
        self.sources = SourceStore(str(root / "sources.sqlite3"))

    def tearDown(self) -> None:
        self.sources.close()
        self.identity.close()
        self.temp.cleanup()

    @staticmethod
    def _initial_replies(last_viewed: str = "2026-10-12T12:00:01Z") -> list[object]:
        payload = {
            "Id": "001A", "Name": "Globex", "Website": "https://globex.invalid",
            "LastModifiedDate": "2026-10-12T12:00:00Z", "IsDeleted": False,
            "LastViewedDate": last_viewed, "LastReferencedDate": last_viewed,
            "Unmodeled_Field__c": "preserved",
        }
        return [
            response({"records": [{"Id": "001A", "LastModifiedDate": payload["LastModifiedDate"], "IsDeleted": False}], "done": True}),
            response(payload),
        ]

    def test_13_runner_preserves_raw_data_and_leaves_identity_unresolved(self) -> None:
        """Live reads reuse P1.3 raw storage and P1.2 without automatic approval."""
        connector = sf_connector(QueueTransport(self._initial_replies()))
        run = LiveIngestionRunner(self.sources, self.identity).sync(
            connector, "initial", ("Account",), until="2026-10-12T13:00:00Z"
        )
        event = self.sources.get_event(run.streams[0].last_event_id)
        self.assertEqual("preserved", event["raw_payload"]["Unmodeled_Field__c"])
        case = self.identity.resolution_case_for_source(event["source_record_id"])
        self.assertEqual("unresolved", case["status"])
        self.assertIsNone(self.identity.active_mapping_for_source(event["source_record_id"]))

    def test_14_repeated_sync_is_idempotent(self) -> None:
        """Repeated initial reads ignore Salesforce view timestamps but keep raw data."""
        transport = QueueTransport(
            self._initial_replies("2026-10-12T12:00:01Z")
            + self._initial_replies("2026-10-12T12:05:01Z")
        )
        connector = sf_connector(transport)
        runner = LiveIngestionRunner(self.sources, self.identity)
        first = runner.sync(connector, "initial", ("Account",), until="2026-10-12T13:00:00Z")
        second = runner.sync(connector, "initial", ("Account",), until="2026-10-12T13:05:00Z")
        self.assertEqual(1, first.processed)
        self.assertEqual(1, second.replayed)
        self.assertEqual(1, self.sources.count("source_event"))
        self.assertEqual(1, self.sources.count("source_record_version"))
        stored = self.sources.get_event(first.streams[0].last_event_id)
        self.assertEqual("2026-10-12T12:00:01Z", stored["raw_payload"]["LastViewedDate"])

    def test_15_api_failure_does_not_advance_checkpoint_and_retry_recovers(self) -> None:
        """A failed API poll leaves the durable cursor intact until a later success."""
        initial_transport = QueueTransport(self._initial_replies())
        runner = LiveIngestionRunner(self.sources, self.identity)
        initial = runner.sync(sf_connector(initial_transport), "initial", ("Account",), until="2026-10-12T13:00:00Z")
        before = initial.streams[0].checkpoint_after
        failed_transport = QueueTransport([OSError("reset"), OSError("reset"), OSError("reset")])
        failed = runner.sync(
            sf_connector(failed_transport), "incremental", ("Account",), until="2026-10-12T13:30:00Z"
        )
        self.assertEqual(1, failed.streams[0].failed)
        self.assertEqual(before, failed.streams[0].checkpoint_after)

        updated = {"Id": "001A", "Name": "Globex v2", "LastModifiedDate": "2026-10-12T13:15:00Z", "IsDeleted": False}
        recovery_transport = QueueTransport([
            response({"ids": ["001A"]}), response(updated), response({"deletedRecords": []}),
        ])
        recovered = runner.sync(
            sf_connector(recovery_transport), "incremental", ("Account",), until="2026-10-12T13:30:00Z"
        )
        self.assertTrue(recovered.succeeded)
        self.assertEqual("2026-10-12T13:15:00.000000Z", recovered.streams[0].checkpoint_after)

    def test_16_processing_failure_stores_raw_input_but_not_checkpoint(self) -> None:
        """An injected durable-processing failure rolls back history and checkpoint."""
        connector = sf_connector(QueueTransport(self._initial_replies()))
        run = LiveIngestionRunner(self.sources, self.identity).sync(
            connector,
            "initial",
            ("Account",),
            until="2026-10-12T13:00:00Z",
            simulate_failure_after=0,
        )
        self.assertEqual(1, run.streams[0].failed)
        self.assertIsNone(run.streams[0].checkpoint_after)
        self.assertEqual(1, self.sources.count("source_event"))
        self.assertEqual(0, self.sources.count("source_record_version"))

    def test_17_hubspot_archived_at_becomes_a_durable_tombstone_time(self) -> None:
        """HubSpot archivedAt validates as deletion time without erasing updatedAt evidence."""
        archived = {
            "id": "12",
            "properties": {},
            "updatedAt": "2026-10-11T12:00:00Z",
            "archived": True,
            "archivedAt": "2026-10-12T12:02:00Z",
        }
        connector = hs_connector(QueueTransport([
            response({"results": []}), response({"results": [archived]}),
        ]))
        run = LiveIngestionRunner(self.sources, self.identity).sync(
            connector, "initial", ("Company",), until="2026-10-12T13:00:00Z"
        )
        self.assertTrue(run.succeeded)
        event = self.sources.get_event(run.streams[0].last_event_id)
        current = self.sources.current_state(event["source_record_id"])
        self.assertEqual("2026-10-12T12:02:00.000000Z", current["source_updated_at"])
        self.assertEqual(1, current["is_deleted"])
        self.assertEqual("2026-10-11T12:00:00Z", event["raw_payload"]["updatedAt"])

    def test_18_overlap_poll_replays_unchanged_salesforce_version(self) -> None:
        """Incremental overlap can refetch a record without appending read-only changes."""
        unchanged_two = {
            "Id": "001A", "Name": "Globex", "Website": "https://globex.invalid",
            "LastModifiedDate": "2026-10-12T12:00:00Z", "IsDeleted": False,
            "LastViewedDate": "2026-10-12T12:05:01Z",
            "LastReferencedDate": "2026-10-12T12:05:01Z",
            "Unmodeled_Field__c": "preserved",
        }
        unchanged_three = {
            **unchanged_two,
            "LastViewedDate": "2026-10-12T12:10:01Z",
            "LastReferencedDate": "2026-10-12T12:10:01Z",
        }
        transport = QueueTransport(self._initial_replies() + [
            response({"ids": ["001A"]}), response(unchanged_two), response({"deletedRecords": []}),
            response({"ids": ["001A"]}), response(unchanged_three), response({"deletedRecords": []}),
        ])
        runner = LiveIngestionRunner(self.sources, self.identity)
        connector = sf_connector(transport)
        initial = runner.sync(connector, "initial", ("Account",), until="2026-10-12T12:01:00Z")
        first_repeat = runner.sync(connector, "incremental", ("Account",), until="2026-10-12T12:06:00Z")
        second_repeat = runner.sync(connector, "incremental", ("Account",), until="2026-10-12T12:11:00Z")
        self.assertEqual(1, initial.processed)
        self.assertEqual((1, 0, 1), (
            first_repeat.streams[0].fetched, first_repeat.processed, first_repeat.replayed,
        ))
        self.assertEqual((1, 0, 1), (
            second_repeat.streams[0].fetched, second_repeat.processed, second_repeat.replayed,
        ))
        self.assertEqual(initial.streams[0].checkpoint_after, second_repeat.streams[0].checkpoint_after)
        self.assertEqual(1, self.sources.count("source_event"))
        self.assertEqual(1, self.sources.count("source_record_version"))

    def test_19_stable_business_field_change_is_not_suppressed(self) -> None:
        """A real payload difference remains a new event even at the same vendor timestamp."""
        changed = {
            "Id": "001A", "Name": "Globex Health", "Website": "https://globex.invalid",
            "LastModifiedDate": "2026-10-12T12:00:00Z", "IsDeleted": False,
            "LastViewedDate": "2026-10-12T12:05:01Z",
            "LastReferencedDate": "2026-10-12T12:05:01Z",
            "Unmodeled_Field__c": "preserved",
        }
        transport = QueueTransport(self._initial_replies() + [
            response({"ids": ["001A"]}), response(changed), response({"deletedRecords": []}),
        ])
        runner = LiveIngestionRunner(self.sources, self.identity)
        connector = sf_connector(transport)
        runner.sync(connector, "initial", ("Account",), until="2026-10-12T12:01:00Z")
        changed_run = runner.sync(connector, "incremental", ("Account",), until="2026-10-12T12:06:00Z")
        self.assertEqual(1, changed_run.processed)
        self.assertEqual(0, changed_run.replayed)
        self.assertEqual(2, self.sources.count("source_event"))
        self.assertEqual(2, self.sources.count("source_record_version"))

    def test_20_pre_fix_event_is_reused_without_rewriting_history(self) -> None:
        """Existing history made with the old hash remains the replay target."""
        old_payload = {
            "Id": "001A", "Name": "Globex", "Website": "https://globex.invalid",
            "LastModifiedDate": "2026-10-12T12:00:00Z", "IsDeleted": False,
            "LastViewedDate": "2026-10-12T12:00:01Z",
            "LastReferencedDate": "2026-10-12T12:00:01Z",
            "Unmodeled_Field__c": "preserved",
        }
        legacy = VendorRecord(
            "salesforce", "00DTEST", "Account", "001A", "upsert",
            old_payload["LastModifiedDate"], old_payload,
            "2026-10-12T12:00:00Z|001A", "GET", "https://example.invalid/001A",
        ).to_event(old_payload["LastModifiedDate"])
        self.sources.process_event(legacy, self.identity)

        connector = sf_connector(QueueTransport(self._initial_replies("2026-10-12T12:05:01Z")))
        replay = LiveIngestionRunner(self.sources, self.identity).sync(
            connector, "initial", ("Account",), until="2026-10-12T12:06:00Z"
        )
        self.assertEqual(0, replay.processed)
        self.assertEqual(1, replay.replayed)
        self.assertEqual(legacy.event_id, replay.streams[0].last_event_id)
        self.assertEqual(1, self.sources.count("source_event"))
        self.assertEqual(1, self.sources.count("source_record_version"))


if __name__ == "__main__":
    unittest.main()

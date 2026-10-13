"""Credential-free acceptance scenarios for P1.7 Snowflake and dbt artifacts."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from typing import Any, Iterable, List, Optional, Tuple


PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
SCRIPTS = PROJECT / "scripts"
DBT = PROJECT / "warehouse/dbt"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(SCRIPTS))

from demo_snowflake_dbt import summary_lines  # noqa: E402
from sai_revenueos_warehouse import (  # noqa: E402
    LoadConflictError,
    SourceEventRow,
    dbt_environment,
    load_source_events,
    load_snowflake_credentials,
    read_source_events,
)


def source_row(event_id: str, envelope_hash: str = "envelope-a") -> SourceEventRow:
    """Build one complete source-event row without containing a real credential."""
    return SourceEventRow((
        event_id,
        "1.0.0",
        "hubspot",
        "tenant-test",
        "Company",
        "company-1",
        "upsert",
        "2026-10-12T23:14:40.388000Z",
        "2026-10-12T23:14:41.000000Z",
        "trace-test",
        "extract-test",
        "Company",
        "cursor-test",
        "2026-10-12T23:14:40.388000Z",
        '{"id":"company-1","properties":{"name":"Globex Health"}}',
        "payload-a",
        envelope_hash,
        "processed",
        1,
        None,
        None,
        "sai_src_test",
        1,
        "2026-10-12T23:14:41.000000Z",
        "2026-10-12T23:14:42.000000Z",
    ))


class FakeCursor:
    """Emulate only the Snowflake cursor behavior exercised by the RAW loader."""

    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection
        self.result: Optional[Tuple[Any, ...]] = None

    def execute(self, sql: str) -> "FakeCursor":
        normalized = " ".join(sql.upper().split())
        if normalized.startswith("CREATE OR REPLACE TEMPORARY TABLE"):
            self.connection.temporary = []
        elif "WHERE T.ENVELOPE_SHA256<>S.ENVELOPE_SHA256" in normalized:
            conflict = next((
                row[0] for row in self.connection.temporary
                if row[0] in self.connection.target and self.connection.target[row[0]] != row[16]
            ), None)
            self.result = None if conflict is None else (conflict,)
        elif "JOIN" in normalized and normalized.startswith("SELECT COUNT(*)"):
            count = sum(1 for row in self.connection.temporary if row[0] in self.connection.target)
            self.result = (count,)
        elif normalized.startswith("SELECT COUNT(*)"):
            self.result = (len(self.connection.target),)
        elif normalized.startswith("MERGE INTO"):
            for row in self.connection.temporary:
                self.connection.target.setdefault(row[0], row[16])
        else:
            raise AssertionError("unexpected SQL: %s" % sql)
        return self

    def executemany(self, _sql: str, values: Iterable[Tuple[Any, ...]]) -> None:
        self.connection.temporary = list(values)

    def fetchone(self) -> Optional[Tuple[Any, ...]]:
        return self.result

    def close(self) -> None:
        return None


class FakeConnection:
    """Hold fake RAW state and transaction counters for loader tests."""

    def __init__(self) -> None:
        self.target: dict[str, str] = {}
        self.temporary: List[Tuple[Any, ...]] = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class WarehouseStagingTests(unittest.TestCase):
    """Protect RAW idempotency, staging coverage, quality tests, and safeguards."""

    def test_01_sqlite_reader_preserves_complete_event_order(self) -> None:
        """The loader reads every immutable event field in original arrival order."""
        columns = [
            "event_id", "contract_version", "source_system", "source_tenant",
            "source_object_type", "source_object_id", "event_type", "source_updated_at",
            "observed_at", "trace_id", "extraction_id", "stream_name", "checkpoint_cursor",
            "checkpoint_high_watermark_at", "raw_payload_json", "payload_sha256",
            "envelope_sha256", "processing_status", "processing_attempts", "last_error_type",
            "last_error_message", "source_record_id", "became_current", "received_at", "processed_at",
        ]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sources.sqlite3"
            with sqlite3.connect(path) as connection:
                connection.execute("CREATE TABLE source_event (%s)" % ", ".join(columns))
                later = list(source_row("event-later").values)
                earlier = list(source_row("event-earlier").values)
                later[23] = "2026-10-12T23:20:00Z"
                earlier[23] = "2026-10-12T23:10:00Z"
                placeholders = ",".join("?" for _ in columns)
                connection.execute("INSERT INTO source_event VALUES (%s)" % placeholders, later)
                connection.execute("INSERT INTO source_event VALUES (%s)" % placeholders, earlier)
            rows = read_source_events(path)
        self.assertEqual(["event-earlier", "event-later"], [row.event_id for row in rows])
        self.assertEqual(25, len(rows[0].values))

    def test_02_raw_load_inserts_new_event_atomically(self) -> None:
        """A new source event becomes one committed Snowflake RAW row."""
        connection = FakeConnection()
        result = load_source_events(connection, [source_row("event-1")])
        self.assertEqual((1, 1, 0, 0, 1), (
            result.selected, result.inserted, result.replayed, result.before_count, result.after_count
        ))
        self.assertEqual(1, connection.commits)
        self.assertEqual(0, connection.rollbacks)

    def test_03_exact_replay_does_not_duplicate_raw_history(self) -> None:
        """Loading the same event ID and envelope twice reports one replay and no insert."""
        connection = FakeConnection()
        load_source_events(connection, [source_row("event-1")])
        repeated = load_source_events(connection, [source_row("event-1")])
        self.assertEqual((0, 1, 1), (repeated.inserted, repeated.replayed, repeated.after_count))

    def test_04_conflicting_event_id_rolls_back_batch(self) -> None:
        """An event ID cannot silently acquire a different immutable envelope."""
        connection = FakeConnection()
        load_source_events(connection, [source_row("event-1", "hash-original")])
        with self.assertRaises(LoadConflictError):
            load_source_events(connection, [source_row("event-1", "hash-changed")])
        self.assertEqual(1, connection.rollbacks)
        self.assertEqual("hash-original", connection.target["event-1"])

    def test_05_policy_keeps_snowflake_and_live_completion_gate(self) -> None:
        """The versioned policy forbids DuckDB substitution and premature completion."""
        policy = json.loads((PROJECT / "contracts/warehouse-normalization-policy.v1.json").read_text())
        self.assertEqual("snowflake", policy["platform"]["warehouse"])
        self.assertFalse(policy["platform"]["local_substitute_allowed"])
        self.assertTrue(policy["completion_gate"]["authenticated_snowflake_load_required"])
        self.assertTrue(policy["completion_gate"]["authenticated_dbt_build_and_test_required"])

    def test_06_dbt_covers_all_contracted_source_objects(self) -> None:
        """Seven source-specific models reuse the four Salesforce and three HubSpot objects."""
        expected = {
            "salesforce/stg_salesforce_accounts.sql",
            "salesforce/stg_salesforce_leads.sql",
            "salesforce/stg_salesforce_contacts.sql",
            "salesforce/stg_salesforce_opportunities.sql",
            "hubspot/stg_hubspot_companies.sql",
            "hubspot/stg_hubspot_contacts.sql",
            "hubspot/stg_hubspot_deals.sql",
        }
        present = {
            str(path.relative_to(DBT / "models/staging"))
            for path in (DBT / "models/staging").rglob("stg_*.sql")
        }
        self.assertTrue(expected.issubset(present))

    def test_07_type_and_history_protection_are_executable_sql(self) -> None:
        """Staging SQL uses safe casts and retains latest and late-arriving evidence."""
        sql = "\n".join(path.read_text() for path in (DBT / "models/staging").rglob("*.sql"))
        for marker in ("try_to_timestamp_tz", "try_to_decimal", "is_latest_source_version", "is_late_arriving"):
            self.assertIn(marker, sql.casefold())

    def test_08_quality_tests_cover_identity_relationships_types_and_history(self) -> None:
        """dbt checks keys, relationships, conversions, history parity, and latest versions."""
        yaml_text = (DBT / "models/staging/staging.yml").read_text()
        test_sql = "\n".join(path.read_text() for path in (DBT / "tests").glob("*.sql"))
        for marker in ("unique", "not_null", "relationships"):
            self.assertIn(marker, yaml_text)
        for marker in ("raw_count", "is_source_updated_at_valid", "count_if", "payload_source_object_id"):
            self.assertIn(marker, test_sql)

    def test_09_failure_demo_is_isolated_and_excluded_by_command(self) -> None:
        """The intentional NULL fixture is tagged and has an explicit cleanup macro."""
        seed = (DBT / "seeds/p17_invalid_globex.csv").read_text()
        properties = (DBT / "seeds/properties.yml").read_text()
        cleanup = (DBT / "macros/cleanup_failure_demo.sql").read_text()
        self.assertTrue(seed.rstrip().endswith(","))
        self.assertIn("failure_demo", properties)
        self.assertIn("drop table if exists", cleanup.casefold())

    def test_10_bootstrap_enforces_cost_and_access_boundaries(self) -> None:
        """The setup uses X-Small compute, auto-suspend, a credit cap, and separate roles."""
        sql = (PROJECT / "warehouse/snowflake/bootstrap.sql").read_text().upper()
        for marker in (
            "WAREHOUSE_SIZE = XSMALL", "AUTO_SUSPEND = 60", "MAX_CLUSTER_COUNT = 1",
            "CREDIT_QUOTA = 1", "DO SUSPEND_IMMEDIATE", "SAI_REVENUEOS_LOADER",
            "SAI_REVENUEOS_DBT",
        ):
            self.assertIn(marker, sql)

    def test_11_default_live_demo_summary_stays_within_fifteen_lines(self) -> None:
        """The authenticated Globex walkthrough remains concise by default."""
        raw = [
            {"event_id": "before", "company_name": "[SAI TEST] Globex Health"},
            {"event_id": "after", "company_name": "[SAI TEST] Globex Health - Incremental Update"},
        ]
        staged = {
            "source_object_id": "351778399989",
            "name": "[SAI TEST] Globex Health - Incremental Update",
            "source_updated_at": "2026-10-12T23:14:40.388000Z",
            "source_tenant": "247604181",
        }
        lines = summary_lines(raw, staged)
        self.assertGreaterEqual(len(lines), 10)
        self.assertLessEqual(len(lines), 15)
        self.assertIn("Before name:", "\n".join(lines))
        self.assertIn("After name:", "\n".join(lines))

    def test_12_role_restricted_pats_are_loaded_only_from_mode_600_file(self) -> None:
        """Local PATs stay ignored, permission-restricted, and separate by role."""
        document = {
            "account": "organization-account",
            "profiles": {
                "loader": {"user": "loader-service", "token": "loader-secret", "role": "LOADER"},
                "dbt": {"user": "dbt-service", "token": "dbt-secret", "role": "DBT"},
            },
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "credentials.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            path.chmod(0o600)
            with patch.dict("os.environ", {"SNOWFLAKE_CREDENTIALS_FILE": str(path)}, clear=False):
                loader = load_snowflake_credentials("loader")
                environment = dbt_environment({"SAFE": "yes"})
                self.assertEqual("loader-service", loader["user"])
                self.assertEqual("loader-secret", loader["password"])
                self.assertEqual("dbt-service", environment["SNOWFLAKE_USER"])
                self.assertEqual("dbt-secret", environment["SNOWFLAKE_DBT_TOKEN"])
                path.chmod(0o644)
                with self.assertRaisesRegex(RuntimeError, "permissions 600"):
                    load_snowflake_credentials("dbt")


if __name__ == "__main__":
    unittest.main()

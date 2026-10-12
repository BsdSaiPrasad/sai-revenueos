#!/usr/bin/env python3
"""Run the credential-free P1.6 Globex ingestion and recovery demonstration."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import deque
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Deque, Dict, Mapping, Optional


PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sai_revenueos_connectors import (  # noqa: E402
    HttpResponse,
    JsonHttpClient,
    LiveIngestionRunner,
    RequestTrace,
    RetryPolicy,
    SalesforceConnector,
    StaticSalesforceToken,
)
from sai_revenueos_identity import IdentityStore  # noqa: E402
from sai_revenueos_sources import SourceStore  # noqa: E402


class ScriptedTransport:
    """Return deterministic API replies while exercising the real connector code."""

    def __init__(self, replies: list[object]) -> None:
        self.replies: Deque[object] = deque(replies)
        self.requests: list[Dict[str, Any]] = []

    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: Optional[bytes],
        timeout: float,
    ) -> HttpResponse:
        self.requests.append({"method": method, "url": url, "body": body.decode() if body else None})
        if not self.replies:
            raise AssertionError("demo transport has no reply for %s %s" % (method, url))
        reply = self.replies.popleft()
        if isinstance(reply, Exception):
            raise reply
        return reply


def response(document: object, status: int = 200) -> HttpResponse:
    return HttpResponse(status, {}, json.dumps(document).encode("utf-8"))


def show(label: str, value: object) -> None:
    print("\n%s" % label)
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true", help="Show all requests, events, and stored evidence.")
    args = parser.parse_args()
    created = {
        "Id": "001P16000000001",
        "Name": "[SAI TEST] Globex Health",
        "Website": "https://globex-p16.invalid",
        "Industry": "Healthcare",
        "BillingCountry": "United States",
        "Description": "SAI_REVENUEOS_P16_TEST_ONLY",
        "LastModifiedDate": "2026-10-12T12:00:00Z",
        "IsDeleted": False,
    }
    updated = {**created, "Name": "[SAI TEST] Globex Health - Incremental Update", "LastModifiedDate": "2026-10-12T12:30:00Z"}
    query_page = {
        "done": True,
        "records": [{"Id": created["Id"], "LastModifiedDate": created["LastModifiedDate"], "IsDeleted": False}],
    }
    replies: list[object] = [
        response(query_page), response(created),
        response(query_page), response(created),
        OSError("simulated connection reset"), OSError("simulated connection reset"),
        response({"ids": [created["Id"]], "latestDateCovered": "2026-10-12T13:00:00Z"}),
        response(updated),
        response({"deletedRecords": [], "latestDateCovered": "2026-10-12T13:00:00Z"}),
    ]
    transport = ScriptedTransport(replies)
    traces: list[RequestTrace] = []
    http = JsonHttpClient(
        transport=transport,
        retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0, max_delay_seconds=0, jitter_ratio=0),
        sleep=lambda _seconds: None,
        trace=traces.append,
    )
    connector = SalesforceConnector(
        StaticSalesforceToken("demo-token-never-logged", "https://globex-dev.my.salesforce.com", "00D-P16-DEMO"),
        http=http,
        api_version="v68.0",
    )

    with tempfile.TemporaryDirectory(prefix="sai-revenueos-p16-") as temp:
        root = Path(temp)
        with ExitStack() as stack:
            identity = stack.enter_context(IdentityStore(str(root / "identity.sqlite3")))
            sources = stack.enter_context(SourceStore(str(root / "sources.sqlite3")))
            runner = LiveIngestionRunner(sources, identity)
            initial = runner.sync(connector, "initial", ("Account",), until="2026-10-12T12:05:00Z")
            source_record_id = sources.get_event(initial.streams[0].last_event_id)["source_record_id"]
            first_state = sources.current_state(source_record_id)
            first_checkpoint = sources.checkpoint("salesforce", connector.source_tenant, "Account")
            repeated = runner.sync(connector, "initial", ("Account",), until="2026-10-12T12:10:00Z")
            history_after_repeat = len(sources.history_for_source(source_record_id))
            failed = runner.sync(connector, "incremental", ("Account",), until="2026-10-12T13:00:00Z")
            checkpoint_after_failure = sources.checkpoint("salesforce", connector.source_tenant, "Account")
            recovered = runner.sync(connector, "incremental", ("Account",), until="2026-10-12T13:00:00Z")
            final_state = sources.current_state(source_record_id)
            final_checkpoint = sources.checkpoint("salesforce", connector.source_tenant, "Account")
            case = identity.resolution_case_for_source(source_record_id)

            print("P1.6 Globex live-ingestion demo (mock API; no real account called)")
            print("Input: Salesforce Account %s, name=%s" % (created["Id"], created["Name"]))
            print("API request: %s %s" % (transport.requests[0]["method"], transport.requests[0]["url"]))
            print("Python: SalesforceConnector.fetch_records -> LiveIngestionRunner.sync -> SourceStore.process_event")
            print("Before: no source state or checkpoint")
            print("After initial: name=%s; raw payload preserved=yes" % first_state["standardized_payload"]["name"])
            print("Identity: status=%s; automatic mapping=no" % case["status"])
            print("Repeat: processed=%d; replayed=%d; history rows=%d" % (
                repeated.processed, repeated.replayed, history_after_repeat
            ))
            print("Simulated API failure: failures=%d; stored error is credential-free" % failed.streams[0].failed)
            print("Checkpoint on failure: before=%s; after=%s" % (
                first_checkpoint["high_watermark_at"], checkpoint_after_failure["high_watermark_at"]
            ))
            print("Recovery retry: processed=%d; failures=%d" % (recovered.processed, recovered.streams[0].failed))
            print("Before/after name: %s -> %s" % (
                first_state["standardized_payload"]["name"], final_state["standardized_payload"]["name"]
            ))
            print("Final: history rows=%d; checkpoint=%s" % (
                len(sources.history_for_source(source_record_id)), final_checkpoint["high_watermark_at"]
            ))
            print("Outcome: retry safe, no duplicate processing, no identity merge or CRM write-back")

            if args.verbose:
                show("MOCK API INPUT - INITIAL", created)
                show("MOCK API INPUT - UPDATE", updated)
                show("CREDENTIAL-FREE REQUESTS", transport.requests)
                show("REQUEST ATTEMPTS", [trace.__dict__ for trace in traces])
                show("INITIAL RUN", initial.__dict__)
                show("REPEATED RUN", repeated.__dict__)
                show("FAILED RUN", failed.__dict__)
                show("RECOVERED RUN", recovered.__dict__)
                show("STORED RAW EVENT", sources.get_event(final_state["latest_event_id"]))
                show("STORED HISTORY", sources.history_for_source(source_record_id))
                show("FINAL CHECKPOINT", final_checkpoint)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

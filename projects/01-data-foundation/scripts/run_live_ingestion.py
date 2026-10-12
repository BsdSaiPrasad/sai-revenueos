#!/usr/bin/env python3
"""Run authenticated P1.6 Salesforce and/or HubSpot ingestion."""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import ExitStack
from pathlib import Path
from typing import Iterable


PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
REPO = PROJECT.parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sai_revenueos_connectors import (  # noqa: E402
    HubSpotConnector,
    JsonHttpClient,
    LiveIngestionRunner,
    RequestTrace,
    SalesforceConnector,
    SalesforceOAuthFile,
    SyncRunResult,
    load_hubspot_token,
)
from sai_revenueos_identity import IdentityStore  # noqa: E402
from sai_revenueos_sources import SourceStore  # noqa: E402


DEFAULT_ROOT = REPO / "generated-data" / "p16-live"


def _trace(item: RequestTrace) -> None:
    print("API: %s %s -> %s (attempt %d)" % (
        item.method, item.url, item.status if item.status is not None else "network error", item.attempt
    ))


def _print_run(run: SyncRunResult, sources: SourceStore, verbose: bool) -> None:
    print("%s %s sync: %s" % (run.source_system, run.mode, "passed" if run.succeeded else "failed"))
    for stream in run.streams:
        print(
            "  %s: fetched=%d processed=%d replayed=%d deleted=%d checkpoint=%s failures=%d"
            % (
                stream.object_type,
                stream.fetched,
                stream.processed,
                stream.replayed,
                stream.tombstones,
                stream.checkpoint_after or "unchanged",
                stream.failed,
            )
        )
        for error in stream.errors:
            print("    error: %s" % error)
        if verbose and stream.last_event_id:
            event = sources.get_event(stream.last_event_id)
            print("    stored raw event (credential-free):")
            print(json.dumps(event, indent=2, sort_keys=True, default=str))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=("salesforce", "hubspot", "both"), required=True)
    parser.add_argument("--mode", choices=("initial", "incremental"), required=True)
    parser.add_argument("--objects", nargs="*", help="Optional source object names; defaults to all supported.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_ROOT / "data")
    parser.add_argument("--credential-dir", type=Path, default=DEFAULT_ROOT / "credentials")
    parser.add_argument("--overlap-seconds", type=int, default=300)
    parser.add_argument("--seed-globex", action="store_true", help="Create or confirm the marked test record.")
    parser.add_argument("--update-globex", action="store_true", help="Update only the marked test record name.")
    parser.add_argument(
        "--confirm-test-write",
        action="store_true",
        help="Required with either explicit fictional-record write option.",
    )
    parser.add_argument("--verbose", action="store_true", help="Show credential-free API request traces.")
    args = parser.parse_args()
    if (args.seed_globex or args.update_globex) and not args.confirm_test_write:
        parser.error("--seed-globex/--update-globex requires --confirm-test-write")

    args.data_dir.mkdir(parents=True, exist_ok=True)
    http = JsonHttpClient(trace=_trace if args.verbose else None)
    platforms = ("salesforce", "hubspot") if args.platform == "both" else (args.platform,)
    exit_code = 0
    with ExitStack() as stack:
        identity = stack.enter_context(IdentityStore(str(args.data_dir / "identity.sqlite3")))
        sources = stack.enter_context(SourceStore(str(args.data_dir / "sources.sqlite3")))
        runner = LiveIngestionRunner(sources, identity, overlap_seconds=args.overlap_seconds)
        for platform in platforms:
            if platform == "salesforce":
                connector = SalesforceConnector(
                    SalesforceOAuthFile(args.credential_dir / "salesforce.json", http=http),
                    http=http,
                )
                default_objects: Iterable[str] = connector.supported_object_types
                if args.seed_globex or args.update_globex:
                    record = connector.ensure_globex_test_account()
                    if args.update_globex:
                        record = connector.update_globex_test_name(
                            str(record["Id"]), "[SAI TEST] Globex Health - Incremental Update"
                        )
                    print("Salesforce fictional test Account confirmed: %s" % record["Id"])
            else:
                connector = HubSpotConnector(
                    load_hubspot_token(args.credential_dir / "hubspot.json"),
                    http=http,
                )
                default_objects = connector.supported_object_types
                if args.seed_globex or args.update_globex:
                    record = connector.ensure_globex_test_company()
                    if args.update_globex:
                        record = connector.update_globex_test_name(
                            str(record["id"]), "[SAI TEST] Globex Health - Incremental Update"
                        )
                    print("HubSpot fictional test Company confirmed: %s" % record["id"])
            selected = tuple(args.objects or default_objects)
            run = runner.sync(connector, args.mode, selected)
            _print_run(run, sources, args.verbose)
            if not run.succeeded:
                exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Load local P1.6 source events into Snowflake RAW exactly once per event ID."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
REPO = PROJECT.parents[1]
SRC = PROJECT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sai_revenueos_warehouse import connect_to_snowflake, load_source_events, read_source_events  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-db",
        type=Path,
        default=REPO / "generated-data/p16-live/data/sources.sqlite3",
        help="Ignored P1.6 SQLite source-history database.",
    )
    parser.add_argument("--limit", type=int, help="Load only the earliest N events for a controlled check.")
    parser.add_argument("--verbose", action="store_true", help="Show event IDs without printing payloads.")
    args = parser.parse_args()

    rows = read_source_events(args.source_db, args.limit)
    connection = connect_to_snowflake("SNOWFLAKE_LOADER_ROLE")
    try:
        result = load_source_events(
            connection,
            rows,
            database=os.environ.get("SNOWFLAKE_DATABASE", "SAI_REVENUEOS"),
            raw_schema=os.environ.get("SNOWFLAKE_RAW_SCHEMA", "RAW"),
        )
    finally:
        connection.close()

    print("P1.7 Snowflake RAW load (authenticated; payloads not printed)")
    print("Input: %s" % args.source_db)
    print("Selected: %d immutable source events" % result.selected)
    print("Before/after RAW rows: %d -> %d" % (result.before_count, result.after_count))
    print("Inserted: %d; replayed: %d" % (result.inserted, result.replayed))
    print("Outcome: event IDs and raw payload history preserved idempotently")
    if args.verbose:
        print("Event IDs:")
        for row in rows:
            print("  - %s" % row.event_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

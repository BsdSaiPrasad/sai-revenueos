#!/usr/bin/env python3
"""Publish an ignored P1.8 active-mapping output to Snowflake for P1.9."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
REPO = PROJECT.parents[1]
SRC = PROJECT / "src"
DEFAULT_INPUT = REPO / "generated-data/p19-canonical/identity-resolution-output.json"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sai_revenueos_canonical import IdentityMappingPublisher  # noqa: E402
from sai_revenueos_warehouse import connect_to_snowflake  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args()
    try:
        document = json.loads(args.input.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit("P1.8 mapping output cannot be loaded: %s" % exc)
    connection = connect_to_snowflake("SNOWFLAKE_DBT_ROLE")
    try:
        result = IdentityMappingPublisher(connection).publish(document)
    finally:
        connection.close()
    print("P1.8 mapping publication: %s" % result.publication_id)
    print("Approved mappings: %d" % result.mapping_count)
    print("Inserted: %s" % result.inserted)
    print("Replayed: %s" % result.replayed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

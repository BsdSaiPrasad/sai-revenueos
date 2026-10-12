#!/usr/bin/env python3
"""Generate deterministic P1.5 synthetic GTM files without external services."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sai_revenueos_synthetic import (  # noqa: E402
    GenerationConfig,
    generate_dataset,
    validate_dataset,
    write_dataset,
)


def main() -> int:
    """Generate, validate, and write one reproducible synthetic dataset."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--companies",
        type=int,
        default=25,
        help="Company count: preset 25, 250, 2500, or a custom value of at least 3.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Deterministic random seed (default: 42).")
    parser.add_argument(
        "--output",
        type=Path,
        help="Output directory (default: generated-data/p15-<companies>-seed-<seed>).",
    )
    parser.add_argument("--verbose", action="store_true", help="Print the complete scenario manifest.")
    args = parser.parse_args()

    try:
        config = GenerationConfig(company_count=args.companies, seed=args.seed)
    except ValueError as exc:
        parser.error(str(exc))
    output = args.output or Path("generated-data") / (
        "p15-%d-companies-seed-%d" % (config.company_count, config.seed)
    )
    dataset = generate_dataset(config)
    report = validate_dataset(dataset)
    report.raise_for_errors()
    paths = write_dataset(dataset, output)
    counts = dataset.counts()

    print("P1.5 synthetic GTM dataset generated (fictional; no vendor API called)")
    print("Config: companies=%d; seed=%d" % (config.company_count, config.seed))
    print("Fingerprint: %s" % dataset.fingerprint())
    print(
        "Core records: companies=%d; people=%d; opportunities=%d; activities=%d"
        % (counts["companies"], counts["people"], counts["opportunities"], counts["activities"])
    )
    print(
        "Source events: Salesforce=%d; HubSpot=%d; validated=%d"
        % (counts["salesforce_events"], counts["hubspot_events"], report.checked_source_events)
    )
    print(
        "Edge cases: quality issues=%d; duplicate replays=%d; late streams=%d"
        % (counts["quality_issues"], report.duplicate_event_replays, report.late_event_streams)
    )
    print("Identity outcome: unresolved by default; automatic merge=false")
    print("Files: %d JSON, JSONL, and CSV outputs" % len(paths))
    print("Output: %s" % output.resolve())
    print("Outcome: deterministic dataset validated successfully")
    if args.verbose:
        print("\nCOMPLETE SCENARIO MANIFEST")
        print(json.dumps(dataset.manifest(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

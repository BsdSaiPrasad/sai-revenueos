"""Write deterministic P1.5 JSON, JSON Lines, CSV, and manifest files."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .generator import SyntheticDataset
from .validation import validate_dataset


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    lines = [json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("CSV output requires at least one row")
    fieldnames = sorted({field for row in rows for field in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_dataset(dataset: SyntheticDataset, output_directory: Path) -> Dict[str, Path]:
    """Validate and write one dataset, replacing only its known output files."""
    report = validate_dataset(dataset)
    report.raise_for_errors()
    output_directory.mkdir(parents=True, exist_ok=True)
    paths = {
        "dataset": output_directory / "synthetic-gtm-dataset.v1.json",
        "salesforce_jsonl": output_directory / "salesforce-events.v1.jsonl",
        "hubspot_jsonl": output_directory / "hubspot-events.v1.jsonl",
        "companies_csv": output_directory / "companies.csv",
        "account_name_history_csv": output_directory / "account-name-history.csv",
        "account_relationships_csv": output_directory / "account-relationships.csv",
        "people_csv": output_directory / "people.csv",
        "employment_history_csv": output_directory / "employment-history.csv",
        "opportunities_csv": output_directory / "opportunities.csv",
        "activities_csv": output_directory / "activities.csv",
        "manifest": output_directory / "scenario-manifest.v1.json",
    }
    _write_json(paths["dataset"], dataset.as_document())
    _write_jsonl(paths["salesforce_jsonl"], dataset.salesforce_events)
    _write_jsonl(paths["hubspot_jsonl"], dataset.hubspot_events)
    _write_csv(paths["companies_csv"], dataset.companies)
    _write_csv(paths["account_name_history_csv"], dataset.account_name_history)
    _write_csv(paths["account_relationships_csv"], dataset.account_relationships)
    _write_csv(paths["people_csv"], dataset.people)
    _write_csv(paths["employment_history_csv"], dataset.employment_history)
    _write_csv(paths["opportunities_csv"], dataset.opportunities)
    _write_csv(paths["activities_csv"], dataset.activities)
    _write_json(paths["manifest"], dataset.manifest())
    return paths

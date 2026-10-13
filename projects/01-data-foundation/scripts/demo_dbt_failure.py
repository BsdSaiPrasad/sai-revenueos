#!/usr/bin/env python3
"""Run one isolated dbt test that is expected to fail, then remove its table."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List


PROJECT = Path(__file__).resolve().parents[1]
DBT_PROJECT = PROJECT / "warehouse/dbt"
SRC = PROJECT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sai_revenueos_warehouse import dbt_environment  # noqa: E402


def _run(dbt: str, arguments: List[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [dbt, *arguments, "--project-dir", str(DBT_PROJECT), "--profiles-dir", str(DBT_PROJECT)],
        check=False,
        capture_output=True,
        text=True,
        env=dbt_environment(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true", help="Show complete dbt output.")
    args = parser.parse_args()
    adjacent_dbt = Path(sys.executable).with_name("dbt")
    dbt = shutil.which("dbt") or (str(adjacent_dbt) if adjacent_dbt.is_file() else None)
    if dbt is None:
        raise SystemExit("dbt is not installed; activate the documented Python 3.12 virtual environment")

    seeded = _run(dbt, ["seed", "--select", "tag:failure_demo"])
    if seeded.returncode != 0:
        if args.verbose:
            print(seeded.stdout)
            print(seeded.stderr)
        raise SystemExit("could not create isolated failure-demo data")
    tested = _run(dbt, ["test", "--select", "tag:failure_demo"])
    cleaned = _run(dbt, ["run-operation", "cleanup_failure_demo"])
    if tested.returncode == 0:
        raise SystemExit("failure demonstration unexpectedly passed")
    if cleaned.returncode != 0:
        raise SystemExit("failure demonstration ran, but cleanup failed")

    print("P1.7 isolated dbt failure demonstration")
    print("Input: p17_invalid_globex with company_name=NULL")
    print("Test: not_null_p17_invalid_globex_company_name")
    print("Expected result: FAIL")
    print("Actual dbt exit code: %d" % tested.returncode)
    print("Protection: the missing required value was detected")
    print("Cleanup: isolated P17_INVALID_GLOBEX table removed")
    if args.verbose:
        print("\nDBT SEED OUTPUT\n%s" % seeded.stdout)
        print("\nDBT TEST OUTPUT\n%s" % tested.stdout)
        print("\nDBT CLEANUP OUTPUT\n%s" % cleaned.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

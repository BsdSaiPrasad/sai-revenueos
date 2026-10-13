#!/usr/bin/env python3
"""Run dbt with the ignored local Snowflake PAT injected only in memory."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
DBT_PROJECT = PROJECT / "warehouse/dbt"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sai_revenueos_warehouse import dbt_environment  # noqa: E402


def main() -> int:
    adjacent_dbt = Path(sys.executable).with_name("dbt")
    dbt = shutil.which("dbt") or (str(adjacent_dbt) if adjacent_dbt.is_file() else None)
    if dbt is None:
        raise SystemExit("dbt is not installed; use the documented Python 3.12 environment")
    if len(sys.argv) == 1:
        raise SystemExit("provide a dbt command, for example: run_snowflake_dbt.py debug")
    command = [
        dbt,
        *sys.argv[1:],
        "--project-dir", str(DBT_PROJECT),
        "--profiles-dir", str(DBT_PROJECT),
    ]
    return subprocess.run(command, env=dbt_environment(), check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())

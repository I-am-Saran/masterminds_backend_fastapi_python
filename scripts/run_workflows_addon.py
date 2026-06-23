#!/usr/bin/env python3
"""Apply only the workflows mappings addon (safe to re-run)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from services.db_service import execute_query  # noqa: E402


def main() -> None:
    path = os.path.join(ROOT, "scripts", "sql", "workflows_mappings_addon.sql")
    with open(path, encoding="utf-8") as f:
        sql = f.read()
    for stmt in [s.strip() for s in sql.split(";") if s.strip() and not s.strip().startswith("--")]:
        print(f"Executing: {stmt[:72]}...")
        execute_query(stmt + ";", fetch_all=False)
    print("Workflow mappings addon applied.")


if __name__ == "__main__":
    main()

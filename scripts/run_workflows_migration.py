#!/usr/bin/env python3
"""Apply workflows SQL migrations (base module + mappings addon)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from services.db_service import execute_query  # noqa: E402


def run_sql_file(relative_path: str) -> None:
    sql_path = os.path.join(ROOT, relative_path)
    with open(sql_path, "r", encoding="utf-8") as f:
        sql = f.read()
    statements = [s.strip() for s in sql.split(";") if s.strip() and not s.strip().startswith("--")]
    for stmt in statements:
        if not stmt:
            continue
        print(f"Executing: {stmt[:72]}...")
        # DDL / DML without RETURNING must not fetch rows
        execute_query(stmt + ";", fetch_all=False)


def main() -> None:
    run_sql_file("scripts/sql/workflows_module.sql")
    print("Base workflow tables migration completed.")
    run_sql_file("scripts/sql/workflows_mappings_addon.sql")
    print("Workflow mappings addon migration completed.")


if __name__ == "__main__":
    main()

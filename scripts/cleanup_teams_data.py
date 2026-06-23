#!/usr/bin/env python3
"""
Data cleanup: remove all team records and related mappings.
Preserves users, roles, projects, workflows, tickets, and other master data.

Usage:
  python scripts/cleanup_teams_data.py          # dry-run (counts + backup only)
  python scripts/cleanup_teams_data.py --execute  # perform deletion
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from services.db_service import execute_query  # noqa: E402

BACKUP_DIR = os.path.join(ROOT, "db", "backups")
TEAM_TABLES = ("teams", "team_users", "team_projects")
OPTIONAL_TABLES = ("workflow_level_assignments",)


def table_exists(table_name: str) -> bool:
    row = execute_query(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
        ) AS exists
        """,
        (table_name,),
        fetch_one=True,
    )
    return bool(row and row.get("exists"))


def count_rows(table_name: str) -> int:
    row = execute_query(f"SELECT COUNT(*) AS c FROM {table_name}", fetch_one=True)
    return int(row["c"]) if row else 0


def export_table_csv(table_name: str, backup_path: str) -> int:
    rows = execute_query(f"SELECT * FROM {table_name}", fetch_all=True) or []
    if not rows:
        with open(backup_path, "w", newline="", encoding="utf-8") as f:
            f.write("")
        return 0

    fieldnames = list(rows[0].keys())
    with open(backup_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if v is None else str(v)) for k, v in row.items()})
    return len(rows)


def export_workflow_team_refs(backup_path: str) -> int:
    if not table_exists("workflow_levels"):
        return 0
    rows = execute_query(
        """
        SELECT id, workflow_id, assignment_type, assignment_value
        FROM workflow_levels
        WHERE assignment_type = 'TEAM' AND assignment_value IS NOT NULL AND btrim(assignment_value) <> ''
        """,
        fetch_all=True,
    ) or []
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, default=str)
    return len(rows)


def get_pre_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in TEAM_TABLES:
        counts[table] = count_rows(table)
    for table in OPTIONAL_TABLES:
        if table_exists(table):
            counts[table] = count_rows(table)
    if table_exists("workflow_levels"):
        row = execute_query(
            """
            SELECT COUNT(*) AS c
            FROM workflow_levels
            WHERE assignment_type = 'TEAM' AND assignment_value IS NOT NULL AND btrim(assignment_value) <> ''
            """,
            fetch_one=True,
        )
        counts["workflow_levels_team_refs"] = int(row["c"]) if row else 0
    return counts


def run_backup(timestamp: str) -> dict[str, str]:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    paths: dict[str, str] = {}
    for table in TEAM_TABLES:
        path = os.path.join(BACKUP_DIR, f"teams_cleanup_{timestamp}_{table}.csv")
        export_table_csv(table, path)
        paths[table] = path
    if table_exists("workflow_level_assignments"):
        path = os.path.join(BACKUP_DIR, f"teams_cleanup_{timestamp}_workflow_level_assignments.csv")
        export_table_csv("workflow_level_assignments", path)
        paths["workflow_level_assignments"] = path
    if table_exists("workflow_levels"):
        path = os.path.join(BACKUP_DIR, f"teams_cleanup_{timestamp}_workflow_levels_team_refs.json")
        export_workflow_team_refs(path)
        paths["workflow_levels_team_refs"] = path
    return paths


def execute_cleanup() -> dict[str, int]:
    deleted: dict[str, int] = {}

    if table_exists("workflow_level_assignments"):
        row = execute_query(
            "SELECT COUNT(*) AS c FROM workflow_level_assignments WHERE team_id IS NOT NULL",
            fetch_one=True,
        )
        team_assignments = int(row["c"]) if row else 0
        if team_assignments:
            execute_query(
                "DELETE FROM workflow_level_assignments WHERE team_id IS NOT NULL",
                fetch_all=False,
            )
        deleted["workflow_level_assignments"] = team_assignments

    if table_exists("workflow_levels"):
        row = execute_query(
            """
            SELECT COUNT(*) AS c
            FROM workflow_levels
            WHERE assignment_type = 'TEAM' AND assignment_value IS NOT NULL AND btrim(assignment_value) <> ''
            """,
            fetch_one=True,
        )
        refs = int(row["c"]) if row else 0
        if refs:
            execute_query(
                """
                UPDATE workflow_levels
                SET assignment_value = NULL
                WHERE assignment_type = 'TEAM' AND assignment_value IS NOT NULL AND btrim(assignment_value) <> ''
                """,
                fetch_all=False,
            )
        deleted["workflow_levels_team_refs_cleared"] = refs

    for table in ("team_users", "team_projects"):
        before = count_rows(table)
        execute_query(f"DELETE FROM {table}", fetch_all=False)
        deleted[table] = before

    before_teams = count_rows("teams")
    execute_query("DELETE FROM teams", fetch_all=False)
    deleted["teams"] = before_teams

    return deleted


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean up all team data from the database.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform deletion after backup (default: dry-run only).",
    )
    args = parser.parse_args()

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    print("=== Teams data cleanup ===")
    print(f"Mode: {'EXECUTE' if args.execute else 'DRY-RUN'}")

    pre_counts = get_pre_counts()
    print("\nPre-cleanup record counts:")
    for table, count in pre_counts.items():
        print(f"  {table}: {count}")

    backup_paths = run_backup(timestamp)
    print("\nBackup files written:")
    for name, path in backup_paths.items():
        print(f"  {name}: {path}")

    if not args.execute:
        print("\nDry-run complete. Re-run with --execute to delete data.")
        return

    if sum(pre_counts.get(t, 0) for t in TEAM_TABLES) == 0:
        print("\nNo team records found. Nothing to delete.")
        return

    deleted = execute_cleanup()
    post_counts = get_pre_counts()

    print("\nRecords deleted:")
    for table, count in deleted.items():
        print(f"  {table}: {count}")

    print("\nPost-cleanup record counts:")
    for table in TEAM_TABLES:
        print(f"  {table}: {post_counts.get(table, 0)}")
    if "workflow_level_assignments" in pre_counts:
        print(f"  workflow_level_assignments: {post_counts.get('workflow_level_assignments', 0)}")
    if "workflow_levels_team_refs" in pre_counts:
        print(f"  workflow_levels_team_refs: {post_counts.get('workflow_levels_team_refs', 0)}")

    print("\nCleanup completed successfully.")


if __name__ == "__main__":
    main()

"""
Add columns to projects and builds to align with schema:
- projects: project_name, start_date, end_date (if not exist)
- builds: build_name, version, status, start_date, end_date, created_by, updated_by (if not exist)
Does not change primary key types (builds may stay BIGSERIAL).
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.db_service import execute_query


def run():
    # --- projects ---
    for col_sql in [
        'ADD COLUMN IF NOT EXISTS project_name TEXT',
        'ADD COLUMN IF NOT EXISTS start_date DATE',
        'ADD COLUMN IF NOT EXISTS end_date DATE',
    ]:
        try:
            execute_query(f"ALTER TABLE public.projects {col_sql}", fetch_all=False)
            print(f"  projects: {col_sql}")
        except Exception as e:
            print(f"  projects {col_sql}: {e}")

    # Backfill project_name from application_name where project_name is null
    try:
        execute_query(
            "UPDATE public.projects SET project_name = COALESCE(application_name, '') WHERE project_name IS NULL",
            fetch_all=False,
        )
        print("  projects: backfilled project_name from application_name")
    except Exception as e:
        print(f"  projects backfill: {e}")

    # --- builds ---
    for col_sql in [
        "ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT '00000000-0000-0000-0000-000000000001'",
        'ADD COLUMN IF NOT EXISTS build_name TEXT',
        'ADD COLUMN IF NOT EXISTS version TEXT',
        'ADD COLUMN IF NOT EXISTS status TEXT DEFAULT \'Active\'',
        'ADD COLUMN IF NOT EXISTS start_date DATE',
        'ADD COLUMN IF NOT EXISTS end_date DATE',
        'ADD COLUMN IF NOT EXISTS created_by UUID',
        'ADD COLUMN IF NOT EXISTS updated_by UUID',
    ]:
        try:
            execute_query(f"ALTER TABLE public.builds {col_sql}", fetch_all=False)
            print(f"  builds: {col_sql}")
        except Exception as e:
            print(f"  builds {col_sql}: {e}")

    # Indexes for builds (idempotent)
    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS idx_builds_tenant_id ON builds(tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_builds_project_id ON builds(project_id)",
        "CREATE INDEX IF NOT EXISTS idx_builds_status ON builds(status)",
        "CREATE INDEX IF NOT EXISTS idx_builds_created_at ON builds(created_at)",
    ]:
        try:
            execute_query(idx_sql, fetch_all=False)
            print(f"  builds: {idx_sql[:60]}...")
        except Exception as e:
            print(f"  builds index: {e}")

    print("Done.")


if __name__ == "__main__":
    run()

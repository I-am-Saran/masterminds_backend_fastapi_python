"""
Idempotent migration: qa_bug_snapshot_daily table + generate_daily_bug_snapshot().
"""

import os
import sys

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_URL  # noqa: E402


def run_migration() -> None:
    sql_path = os.path.join(os.path.dirname(__file__), "sql", "add_qa_bug_snapshot_daily.sql")
    with open(sql_path, "r", encoding="utf-8") as f:
        sql = f.read()

    print(f"Connecting to database: {DB_URL}")
    conn = psycopg2.connect(DB_URL)
    try:
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()
        print("qa_bug_snapshot_daily migration applied successfully.")
    except Exception as exc:
        conn.rollback()
        print(f"Migration failed: {exc}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()

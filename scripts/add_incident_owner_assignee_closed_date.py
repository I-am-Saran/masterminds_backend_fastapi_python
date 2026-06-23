"""Add incident_owner, incident_assignee, incident_closed_date to incident_registers."""
import psycopg2
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_URL

def add_columns():
    try:
        print(f"Connecting to database: {DB_URL}")
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()

        table = "incident_registers"
        columns = [
            {"name": "incident_owner", "type": "TEXT", "default": "NULL"},
            {"name": "incident_assignee", "type": "TEXT", "default": "NULL"},
            {"name": "incident_closed_date", "type": "TIMESTAMP WITH TIME ZONE", "default": "NULL"},
        ]

        for col in columns:
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name=%s AND column_name=%s;",
                (table, col["name"]),
            )
            if cur.fetchone():
                print(f"  Column '{col['name']}' already exists in {table}.")
            else:
                print(f"  Adding column '{col['name']}' to {table}...")
                cur.execute(
                    f'ALTER TABLE public.{table} ADD COLUMN "{col["name"]}" {col["type"]} DEFAULT {col["default"]};'
                )
                print(f"  Column '{col['name']}' added.")

        conn.commit()
        print("Done.")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    add_columns()

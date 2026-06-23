
import os
import sys

# Ensure the current directory is in the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.db_service import execute_query

def add_columns():
    columns_to_add = [
        ("code", "TEXT"),
        ("summary", "TEXT"),
        ("implementation_guidance", "TEXT"),
        ("organization", "TEXT"),
        ("organization_id", "UUID")
    ]

    print("Checking and adding columns to security_controls table...")
    
    # First check what columns exist
    existing_columns = []
    try:
        rows = execute_query(
            "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='security_controls'",
            fetch_all=True
        )
        if rows:
            existing_columns = [r['column_name'] for r in rows]
    except Exception as e:
        print(f"Error checking existing columns: {e}")
        return

    for col_name, col_type in columns_to_add:
        if col_name not in existing_columns:
            print(f"Adding column {col_name} ({col_type})...")
            try:
                execute_query(f'ALTER TABLE security_controls ADD COLUMN "{col_name}" {col_type}', fetch_all=False)
                print(f"Successfully added {col_name}")
            except Exception as e:
                print(f"Failed to add {col_name}: {e}")
        else:
            print(f"Column {col_name} already exists.")

if __name__ == "__main__":
    add_columns()

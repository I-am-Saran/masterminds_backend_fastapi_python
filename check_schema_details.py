
from services.db_service import execute_query
import json

def check_schema():
    print("Checking projects table schema...")
    try:
        # Get column details
        sql = """
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'projects';
        """
        rows = execute_query(sql, fetch_all=True)
        print(json.dumps(rows, indent=2, default=str))
        
        print("\nChecking builds table schema (project_id and id)...")
    sql_builds = """
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'builds' AND column_name IN ('project_id', 'id');
    """
    rows_builds = execute_query(sql_builds, fetch_all=True)
    print(json.dumps(rows_builds, indent=2, default=str))

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_schema()


from services.db_service import execute_query
import json

def get_bugs_constraints():
    print("Fetching constraints for 'bugs' table...")
    
    # Query to get constraint definitions
    sql = """
    SELECT conname as constraint_name, pg_get_constraintdef(c.oid) as constraint_def
    FROM pg_constraint c
    JOIN pg_class t ON c.conrelid = t.oid
    WHERE t.relname = 'bugs'
    AND t.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public');
    """
    
    try:
        rows = execute_query(sql, fetch_all=True)
        if rows:
            print(f"Found {len(rows)} constraints:")
            for row in rows:
                print(f"Constraint: {row['constraint_name']}")
                print(f"Definition: {row['constraint_def']}")
                print("-" * 40)
        else:
            print("No constraints found for table 'bugs'.")
            
    except Exception as e:
        print(f"Error executing query: {e}")

if __name__ == "__main__":
    get_bugs_constraints()

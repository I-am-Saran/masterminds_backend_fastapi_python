
from services.db_service import execute_query
import json

def inspect_bugs_details():
    print("Fetching constraints and indexes for 'bugs' table...")
    
    # Get constraints with types
    sql_constraints = """
    SELECT 
        conname as name, 
        pg_get_constraintdef(c.oid) as definition,
        contype as type
    FROM pg_constraint c
    JOIN pg_class t ON c.conrelid = t.oid
    WHERE t.relname = 'bugs'
    AND t.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public');
    """
    
    # Get indexes
    sql_indexes = """
    SELECT 
        indexname as name, 
        indexdef as definition
    FROM pg_indexes
    WHERE tablename = 'bugs'
    AND schemaname = 'public';
    """
    
    try:
        print("\n--- CONSTRAINTS ---")
        rows = execute_query(sql_constraints, fetch_all=True)
        if rows:
            for row in rows:
                type_map = {'c': 'CHECK', 'f': 'FOREIGN KEY', 'p': 'PRIMARY KEY', 'u': 'UNIQUE', 't': 'TRIGGER', 'x': 'EXCLUSION'}
                ctype = type_map.get(row['type'], row['type'])
                print(f"Name: {row['name']}")
                print(f"Type: {ctype}")
                print(f"Definition: {row['definition']}")
                print("-" * 20)
        else:
            print("No constraints found.")

        print("\n--- INDEXES ---")
        rows = execute_query(sql_indexes, fetch_all=True)
        if rows:
            for row in rows:
                print(f"Name: {row['name']}")
                print(f"Definition: {row['definition']}")
                print("-" * 20)
        else:
            print("No indexes found.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect_bugs_details()

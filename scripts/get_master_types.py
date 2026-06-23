from services.db_service import execute_query
import json

def main():
    try:
        results = execute_query("SELECT DISTINCT type FROM masters", fetch_all=True)
        print(json.dumps(results, indent=2))
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()

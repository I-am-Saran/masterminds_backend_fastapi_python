from services.db_service import execute_query

try:
    cols = execute_query(
        "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'builds'",
        fetch_all=True
    )
    print("Builds table columns:", cols)
except Exception as e:
    print("Error:", e)

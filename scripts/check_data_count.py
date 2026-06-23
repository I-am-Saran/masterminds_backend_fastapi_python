from services.db_service import execute_query

try:
    p_count = execute_query("SELECT count(*) as c FROM projects", fetch_one=True)
    b_count = execute_query("SELECT count(*) as c FROM builds", fetch_one=True)
    print("Projects count:", p_count)
    print("Builds count:", b_count)
except Exception as e:
    print("Error:", e)

import sys
import os
import psycopg2

# Add parent directory to path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

def run_sql_file(filename):
    try:
        conn = psycopg2.connect(config.DB_URL)
        cur = conn.cursor()
        
        print(f"Executing SQL from {filename}...")
        
        with open(filename, 'r') as f:
            sql = f.read()
            
        cur.execute(sql)
        conn.commit()
        
        print("SQL executed successfully.")
        return True
    except Exception as e:
        if 'conn' in locals() and conn:
            conn.rollback()
        print(f"Error: {e}")
        return False
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sql_file = os.path.join(script_dir, "create_new_tables.sql")
    run_sql_file(sql_file)


import psycopg2
import os
import sys
from dotenv import load_dotenv

# Add parent directory to path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# Load environment variables
load_dotenv()

DB_URL = config.DB_URL

def inspect_schema():
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        
        print("--- USERS Table Schema ---")
        cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'users'")
        for row in cur.fetchall():
            print(row)
            
        print("\n--- PROJECTS Table Schema ---")
        cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'projects'")
        for row in cur.fetchall():
            print(row)
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    inspect_schema()

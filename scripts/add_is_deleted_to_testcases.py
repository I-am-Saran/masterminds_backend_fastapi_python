
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

def add_is_deleted_column():
    conn = None
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        
        print("Checking if is_deleted column exists in testcases table...")
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='testcases' AND column_name='is_deleted';
        """)
        exists = cur.fetchone()
        
        if not exists:
            print("Adding is_deleted column...")
            cur.execute("""
                ALTER TABLE testcases 
                ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE;
            """)
            
            # Update existing records to have is_deleted = FALSE
            cur.execute("UPDATE testcases SET is_deleted = FALSE WHERE is_deleted IS NULL;")
            
            # Optional: Add index for performance
            cur.execute("CREATE INDEX IF NOT EXISTS idx_testcases_is_deleted ON testcases(is_deleted);")
            
            conn.commit()
            print("Column added successfully.")
        else:
            print("Column is_deleted already exists.")
            
    except Exception as e:
        print(f"Error: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            cur.close()
            conn.close()

if __name__ == "__main__":
    add_is_deleted_column()

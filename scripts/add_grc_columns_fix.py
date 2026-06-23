import psycopg2
import sys
import os

# Add parent directory to path to import config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_URL

def add_columns():
    try:
        print(f"Connecting to database: {DB_URL}")
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        
        tables = ["risk_registers", "management_review_meetings", "incident_registers"]
        columns = [
            {"name": "created_by", "type": "TEXT", "default": "NULL"},
            {"name": "tenant_id", "type": "TEXT", "default": "'00000000-0000-0000-0000-000000000001'"} 
        ]
        
        # Note: Using TEXT for tenant_id to be safe with string/uuid mismatches, 
        # but typically it should be UUID. Given the error "can't adapt type 'UUID'" 
        # previously seen, keeping it flexible might be better, or we cast.
        # However, organization_id is UUID. Let's check organization_id type first?
        # Nah, let's just use TEXT for tenant_id to avoid headaches, as the Pydantic model uses str.
        # Actually, if I use TEXT, I don't need to worry about UUID casting.
        
        for table in tables:
            print(f"Processing table: {table}")
            for col in columns:
                # Check if column exists
                cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name='{table}' AND column_name='{col['name']}';")
                if cur.fetchone():
                    print(f"  Column '{col['name']}' already exists in {table}.")
                else:
                    print(f"  Adding column '{col['name']}' to {table}...")
                    cur.execute(f'ALTER TABLE public.{table} ADD COLUMN "{col["name"]}" {col["type"]} DEFAULT {col["default"]};')
                    print(f"  Column '{col['name']}' added.")
            
        conn.commit()
        print("All columns processed successfully.")
            
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    add_columns()

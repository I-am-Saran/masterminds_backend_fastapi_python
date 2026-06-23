
import os
import uuid
import sys
from services.db_service import local_db as supabase
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

RECORD_ID = "af60068d-0b03-451d-b48a-d28104d55153"
TENANT_ID = "00000000-0000-0000-0000-000000000001"

print(f"Checking for record: {RECORD_ID}")

# Check by ID
try:
    print(f"1. Checking by 'id' column...")
    resp = supabase.table("security_controls").select("*").eq("id", RECORD_ID).execute()
    if resp.data:
        print(f"Found by ID! count: {len(resp.data)}")
        print(f"Tenant ID: {resp.data[0].get('tenant_id')}")
        print(f"Is Deleted: {resp.data[0].get('is_deleted', 'N/A')}")
    else:
        print("Not found by ID.")
except Exception as e:
    print(f"Error checking by ID: {e}")

# Check by UUID
try:
    print(f"2. Checking by 'uuid' column...")
    resp = supabase.table("security_controls").select("*").eq("uuid", RECORD_ID).execute()
    if resp.data:
        print(f"Found by UUID! count: {len(resp.data)}")
        print(f"Tenant ID: {resp.data[0].get('tenant_id')}")
        print(f"Is Deleted: {resp.data[0].get('is_deleted', 'N/A')}")
    else:
        print("Not found by UUID.")
except Exception as e:
    print(f"Error checking by UUID: {e}")

# Check if it exists at all (ignoring tenant)
try:
    print(f"3. Checking global existence (ignoring tenant)...")
    resp = supabase.table("security_controls").select("id, uuid, tenant_id").or_(f"id.eq.{RECORD_ID},uuid.eq.{RECORD_ID}").execute()
    if resp.data:
        print("Found in database:")
        for row in resp.data:
            print(f" - ID: {row.get('id')}")
            print(f" - UUID: {row.get('uuid')}")
            print(f" - Tenant: {row.get('tenant_id')}")
    else:
        print("Absolutely not found in database.")

except Exception as e:
    print(f"Error checking global: {e}")

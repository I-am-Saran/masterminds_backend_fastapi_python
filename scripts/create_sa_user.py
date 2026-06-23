
import psycopg2
import uuid
import os
import sys
import bcrypt
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DB_URL = os.getenv("DB_URL")
if not DB_URL:
    print("Error: DB_URL environment variable not set")
    sys.exit(1)

DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"
SA_EMAIL = "sa@kaizen.com"
SA_PASSWORD = "Password@123"
SA_NAME = "Super Admin"

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def create_sa_user():
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        
        # 1. Get or Create Super Admin Role
        print("Checking for Super Admin role...")
        cur.execute("""
            SELECT id FROM roles 
            WHERE role_name = 'Super Admin' AND tenant_id = %s
        """, (DEFAULT_TENANT_ID,))
        role_result = cur.fetchone()
        
        if role_result:
            role_id = role_result[0]
            print(f"Super Admin role found: {role_id}")
        else:
            print("Super Admin role not found. Creating...")
            role_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO roles (id, tenant_id, role_name, role_description, is_system_role, is_active, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                role_id,
                DEFAULT_TENANT_ID,
                'Super Admin',
                'Full access to all modules and operations',
                True,
                True,
                'system'
            ))
            print(f"Created Super Admin role: {role_id}")

        # 2. Check if user exists
        print(f"Checking for user {SA_EMAIL}...")
        cur.execute("SELECT id FROM users WHERE email = %s", (SA_EMAIL,))
        user_result = cur.fetchone()
        
        hashed_pw = hash_password(SA_PASSWORD)
        
        if user_result:
            user_id = user_result[0]
            print(f"User exists ({user_id}). Updating password and role...")
            cur.execute("""
                UPDATE users 
                SET password = %s, 
                    default_role_id = %s,
                    is_active = true,
                    full_name = %s,
                    tenant_id = %s,
                    updated_at = NOW()
                WHERE id = %s
            """, (hashed_pw, role_id, SA_NAME, DEFAULT_TENANT_ID, user_id))
        else:
            print("User does not exist. Creating...")
            user_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO users (
                    id, email, password, full_name, role, 
                    is_active, created_at, updated_at, 
                    tenant_id, default_role_id, sso_provider, login_count
                ) VALUES (
                    %s, %s, %s, %s, %s, 
                    %s, NOW(), NOW(), 
                    %s, %s, 'manual', 0
                )
            """, (
                user_id, SA_EMAIL, hashed_pw, SA_NAME, 'Super Admin',
                True,
                DEFAULT_TENANT_ID, role_id
            ))
            print(f"Created user: {user_id}")

        # 3. Assign role in user_roles table
        print("Assigning role in user_roles table...")
        # Check if mapping exists
        cur.execute("""
            SELECT id FROM user_roles 
            WHERE user_id = %s AND role_id = %s AND tenant_id = %s
        """, (user_id, role_id, DEFAULT_TENANT_ID))
        
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO user_roles (tenant_id, user_id, role_id, assigned_by)
                VALUES (%s, %s, %s, 'system')
            """, (DEFAULT_TENANT_ID, user_id, role_id))
            print("Role mapping added.")
        else:
            print("Role mapping already exists.")

        # 4. Ensure permissions (optional but good)
        # We can reuse the logic from assign_superadmin.py if needed, 
        # but the role existence check above should suffice if the role was already properly set up.
        # For a new role, we might want to add permissions.
        
        # Let's just make sure the role has permissions if we just created it.
        # Actually, let's just make sure it has permissions regardless.
        MODULES = [
            'security_controls', 'tasks', 'audits', 'users', 'bugs', 
            'transtrackers', 'roles', 'settings', 'certifications'
        ]
        
        print("Ensuring permissions...")
        for module in MODULES:
            # Check if permission exists for this role and module
            cur.execute("""
                SELECT id FROM permissions 
                WHERE role_id = %s AND module_name = %s AND tenant_id = %s
            """, (role_id, module, DEFAULT_TENANT_ID))
            
            if not cur.fetchone():
                perm_id = str(uuid.uuid4())
                cur.execute("""
                    INSERT INTO permissions (
                        id, tenant_id, role_id, module_name, 
                        can_create, can_read, can_update, can_delete, 
                        created_by
                    ) VALUES (%s, %s, %s, %s, true, true, true, true, 'system')
                """, (perm_id, DEFAULT_TENANT_ID, role_id, module))
                print(f"Added full permissions for {module}")

        conn.commit()
        print("Successfully completed.")
        
    except Exception as e:
        print(f"Error: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    create_sa_user()

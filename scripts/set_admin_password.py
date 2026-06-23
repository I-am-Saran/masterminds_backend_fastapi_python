import os
import sys
import uuid
import psycopg2
import bcrypt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_URL

def run():
    email = os.getenv("ADMIN_EMAIL", "admin@kaizen.local")
    password = os.getenv("ADMIN_PASSWORD", "Kaizengrc@123")
    tenant_id = os.getenv("ADMIN_TENANT_ID", "00000000-0000-0000-0000-000000000001")
    full_name = os.getenv("ADMIN_FULL_NAME", "Admin User")
    role = os.getenv("ADMIN_ROLE", "admin")

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    cur.execute("SELECT id FROM users WHERE LOWER(email)=LOWER(%s)", (email,))
    row = cur.fetchone()

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    if row:
        cur.execute(
            "UPDATE users SET password=%s, is_active=TRUE, updated_at=NOW() WHERE LOWER(email)=LOWER(%s)",
            (hashed, email),
        )
        print("updated")
    else:
        user_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO users (id,email,password,full_name,role,is_active,tenant_id,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,TRUE,%s,NOW(),NOW())",
            (user_id, email, hashed, full_name, role, tenant_id),
        )
        print("created")

    conn.commit()
    cur.close()
    conn.close()

if __name__ == "__main__":
    run()

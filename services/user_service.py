"""
User Service - Helper functions for user-related operations
"""

from typing import Optional, Dict, Any
import psycopg2
from config import DB_URL


def get_user_tenant_id(user_id: str) -> Optional[str]:
    """Get tenant_id for a user from the users table."""
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute("SELECT tenant_id FROM users WHERE id = %s LIMIT 1", (user_id,))
        row = cur.fetchone()
        conn.close()
        
        if row:
            return row[0]
        return None
    except Exception as e:
        print(f"Error getting user tenant_id: {e}")
        return None


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Get full user record by ID."""
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE id = %s LIMIT 1", (user_id,))
        row = cur.fetchone()
        
        if row:
            # Get column names
            colnames = [desc[0] for desc in cur.description]
            user_dict = dict(zip(colnames, row))
            conn.close()
            return user_dict
        conn.close()
        return None
    except Exception as e:
        print(f"Error getting user: {e}")
        return None


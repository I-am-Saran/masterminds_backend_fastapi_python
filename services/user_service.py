"""
User Service - Helper functions for user-related operations
"""

from typing import Optional, Dict, Any
from services.db_service import pooled_connection


def get_user_tenant_id(user_id: str) -> Optional[str]:
    """Get tenant_id for a user from the users table."""
    try:
        with pooled_connection() as conn:
            cur = conn.cursor()
            try:
                cur.execute("SELECT tenant_id FROM users WHERE id = %s LIMIT 1", (user_id,))
                row = cur.fetchone()
            finally:
                cur.close()
        
        if row:
            return row[0]
        return None
    except Exception as e:
        print(f"Error getting user tenant_id: {e}")
        return None


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Get full user record by ID."""
    try:
        with pooled_connection() as conn:
            cur = conn.cursor()
            try:
                cur.execute("SELECT * FROM users WHERE id = %s LIMIT 1", (user_id,))
                row = cur.fetchone()
                if row:
                    colnames = [desc[0] for desc in cur.description]
                    return dict(zip(colnames, row))
                return None
            finally:
                cur.close()
        
    except Exception as e:
        print(f"Error getting user: {e}")
        return None


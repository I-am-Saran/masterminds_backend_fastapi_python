# COMMENTED OUT FOR LOCAL DEVELOPMENT - Using local PostgreSQL instead
# import os
# from typing import Optional
# from dotenv import load_dotenv
# from supabase import create_client, Client

# # Load environment variables from .env file in the backend directory
# load_dotenv()

# SUPABASE_URL = os.getenv("SUPABASE_URL")
# SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# if not SUPABASE_URL or not SUPABASE_KEY:
#     raise Exception("Missing SUPABASE_URL or SUPABASE_KEY environment variables. Check your .env file.")

# supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# For local development, use local database service instead
from services.db_service import local_db as supabase
from services.auth_service import get_user_from_token
from typing import Optional


def verify_supabase_token(authorization_header: Optional[str] = None):
    """Lightweight token verification helper - now uses JWT instead of Supabase auth.

    Returns a dict with user info if a valid token exists; otherwise None.
    """
    try:
        if not authorization_header or not authorization_header.lower().startswith("bearer "):
            return None
        
        token = authorization_header.split(" ", 1)[1].strip()
        user = get_user_from_token(token)
        
        if user:
            return {
                "status": "success",
                "user": {
                    "id": user.get("user_id"),
                    "email": user.get("email"),
                },
                "user_id": user.get("user_id"),
                "email": user.get("email"),
            }
        return None
    except Exception:
        return None
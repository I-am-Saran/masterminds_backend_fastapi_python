"""
Authentication Service - JWT-based authentication
"""

import jwt  # PyJWT library
import bcrypt
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple, cast
import psycopg2
import time
from fastapi import HTTPException
from config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRATION_HOURS
from services.db_service import pooled_connection
from services.request_context import get_request_context, set_request_token, set_request_user, add_timing_ms


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(password: str, hashed: str | bytes) -> bool:
    """Verify a password against a bcrypt hash. Accepts hashed as str or bytes (e.g. from DB)."""
    try:
        plain_bytes = password.encode("utf-8")
        hashed_bytes = hashed.encode("utf-8") if isinstance(hashed, str) else hashed
        if not hashed_bytes or len(hashed_bytes) < 60:
            logging.warning("[auth] verify_password: invalid or too short hash")
            return False
        result = bcrypt.checkpw(plain_bytes, hashed_bytes)
        logging.info(f"[auth] bcrypt.checkpw result: {result}")
        return result
    except Exception as e:
        logging.warning(f"[auth] verify_password exception: {type(e).__name__}: {e}")
        return False


def validate_password_strength(password: str) -> Tuple[bool, str]:
    """Validate password strength requirements.
    
    Requirements:
    - Minimum 12 characters
    - At least 1 uppercase letter
    - At least 1 number
    - At least 1 special character
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(password) < 12:
        return False, "Password must be at least 12 characters long"
    
    has_upper = any(c.isupper() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?/~`" for c in password)
    
    errors = []
    if not has_upper:
        errors.append("1 uppercase letter")
    if not has_digit:
        errors.append("1 number")
    if not has_special:
        errors.append("1 special character")
    
    if errors:
        return False, f"Password must contain: {', '.join(errors)}"
    
    return True, ""


def create_jwt_token(user_id: str, email: str) -> str:
    """Create a JWT token for a user."""
    payload = {
        "user_id": user_id,
        "email": email,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_jwt_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify a JWT token and return the payload."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def authenticate_user(email: str, password: str) -> Optional[Dict[str, Any]]:
    """Authenticate a user with email and password.
    
    Email is normalized (strip + lower) before DB lookup. Password is verified with bcrypt
    (plain bytes vs stored hash only; no hashing of input before checkpw).
    
    Returns:
        Dict with user info and token if successful
        None if user not found or password incorrect
        Dict with error key if user is inactive or no_password
    """
    # Normalize email before any DB use (single source of truth for lookup)
    email = (email or "").strip().lower()
    if not email:
        logging.warning("[auth] authenticate_user: empty email after normalize")
        return None

    try:
        with pooled_connection() as conn:
            cur = conn.cursor()

            try:
                cur.execute(
                    """
                    SELECT id, email, full_name, password, tenant_id, is_active, first_login, last_login
                    FROM users
                    WHERE LOWER(TRIM(email)) = LOWER(%s)
                    ORDER BY is_active DESC, updated_at DESC NULLS LAST
                    LIMIT 1
                    """,
                    (email,),
                )
                user_row = cur.fetchone()

                logging.info(
                    f"[auth] authenticate_user: normalized_email={email!r}, user_found={user_row is not None}"
                )

                if not user_row:
                    logging.warning("[auth] authenticate_user: user not found for email (normalized)")
                    return None

                user_id, user_email, full_name, hashed_password, tenant_id, is_active, first_login, last_login = (
                    user_row
                )

                hashed_len = len(hashed_password) if hashed_password else 0
                hashed_type = type(hashed_password).__name__
                logging.info(
                    f"[auth] authenticate_user: hashed_password len={hashed_len}, type={hashed_type}"
                )

                if not is_active:
                    logging.warning("[auth] authenticate_user: user inactive")
                    return {
                        "error": "inactive",
                        "message": "Your account is inactive. Please contact your administrator.",
                    }

                if not hashed_password or hashed_len < 60:
                    logging.warning("[auth] authenticate_user: no or invalid password set")
                    return {
                        "error": "no_password",
                        "message": "No password set for this account. Please use SSO login or contact your administrator.",
                    }

                pw_ok = verify_password(password, hashed_password)
                logging.info(f"[auth] authenticate_user: bcrypt comparison result={pw_ok}")

                if not pw_ok:
                    logging.warning("[auth] authenticate_user: password verification failed")
                    return None

                is_default_password = verify_password("pass", hashed_password)
                is_first_time = is_default_password

                if first_login is None:
                    cur.execute(
                        "UPDATE users SET first_login = NOW(), last_login = NOW(), login_count = COALESCE(login_count, 0) + 1 WHERE id = %s",
                        (user_id,),
                    )
                else:
                    cur.execute(
                        "UPDATE users SET last_login = NOW(), login_count = COALESCE(login_count, 0) + 1 WHERE id = %s",
                        (user_id,),
                    )
                conn.commit()

                token = create_jwt_token(user_id, user_email)
                logging.info(f"[auth] authenticate_user: login successful, user_id={user_id}")

                return {
                    "user_id": user_id,
                    "email": user_email,
                    "full_name": full_name,
                    "tenant_id": tenant_id,
                    "token": token,
                    "requires_password_change": is_first_time,
                }
            finally:
                cur.close()
    except psycopg2.Error as e:
        logging.exception(f"[auth] authenticate_user: database error: {e}")
        return None
    except Exception as e:
        logging.exception(f"[auth] authenticate_user: unexpected error: {e}")
        return None


def get_user_from_token(token: str) -> Optional[Dict[str, Any]]:
    """Get user information from JWT token."""
    t0 = time.perf_counter()
    ctx = get_request_context()
    if ctx and ctx.get("token") == token and ctx.get("user") is not None:
        user = cast(Optional[Dict[str, Any]], ctx.get("user"))
        add_timing_ms("auth", (time.perf_counter() - t0) * 1000.0)
        return user

    payload = verify_jwt_token(token)
    if not payload:
        return None
    
    user_id = payload.get("user_id")
    if not user_id:
        return None
    
    try:
        with pooled_connection() as conn:
            cur = conn.cursor()
            try:
                cur.execute(
                    "SELECT id, email, full_name, tenant_id FROM users WHERE id = %s AND is_active = TRUE",
                    (user_id,),
                )
                user_row = cur.fetchone()
            finally:
                cur.close()

        if not user_row:
            return None

        user_id, email, full_name, tenant_id = user_row
        user = {
            "user_id": user_id,
            "id": user_id,
            "email": email,
            "full_name": full_name,
            "tenant_id": tenant_id,
        }
        if ctx is not None:
            set_request_token(token)
            set_request_user(user)
        return user
    except Exception:
        return None
    finally:
        add_timing_ms("auth", (time.perf_counter() - t0) * 1000.0)

def auth_guard(authorization: Optional[str]) -> Dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split(" ", 1)[1].strip()
    ctx = get_request_context()
    if ctx and ctx.get("token") == token and ctx.get("user") is not None:
        user = cast(Dict[str, Any], ctx.get("user"))
    else:
        user = get_user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = cast(Dict[str, Any], user)
    return {"token": token, "user": user, "user_id": user.get("user_id"), "tenant_id": user.get("tenant_id")}


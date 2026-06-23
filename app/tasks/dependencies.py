"""FastAPI dependencies for Kaizen Tasks."""

from typing import Any, Dict, Optional

from fastapi import Header

from services.auth_service import auth_guard


def get_auth_context(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    ctx = auth_guard(authorization)
    user = ctx.get("user") or {}
    return {
        "user": user,
        "user_id": ctx.get("user_id"),
        "tenant_id": ctx.get("tenant_id"),
        "email": (user.get("email") or "").strip().lower(),
    }

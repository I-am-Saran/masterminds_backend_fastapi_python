"""Data access for email configurations, notifications, and templates."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.db_service import execute_query, local_db as supabase


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mask_config(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not row:
        return row
    out = dict(row)
    out["has_password"] = bool(out.pop("password", None))
    return out


def list_configurations(tenant_id: str) -> List[Dict[str, Any]]:
    resp = (
        supabase.table("email_configurations")
        .select("*")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .execute()
    )
    return [_mask_config(r) for r in (resp.data or [])]


def get_configuration(config_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    resp = (
        supabase.table("email_configurations")
        .select("*")
        .eq("id", config_id)
        .eq("tenant_id", tenant_id)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    return rows[0] if rows else None


def get_active_configuration(tenant_id: str) -> Optional[Dict[str, Any]]:
    resp = (
        supabase.table("email_configurations")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    return rows[0] if rows else None


def deactivate_all_configurations(tenant_id: str, except_id: Optional[str] = None) -> None:
    query = (
        supabase.table("email_configurations")
        .update({"is_active": False, "updated_at": _now()})
        .eq("tenant_id", tenant_id)
        .eq("is_active", True)
    )
    if except_id:
        query = query.neq("id", except_id)
    query.execute()


def insert_configuration(data: Dict[str, Any]) -> Dict[str, Any]:
    resp = supabase.table("email_configurations").insert(data).execute()
    if getattr(resp, "error", None):
        raise RuntimeError(str(resp.error))
    return resp.data[0] if resp.data else data


def update_configuration(config_id: str, tenant_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    updates["updated_at"] = _now()
    resp = (
        supabase.table("email_configurations")
        .update(updates)
        .eq("id", config_id)
        .eq("tenant_id", tenant_id)
        .execute()
    )
    if getattr(resp, "error", None):
        raise RuntimeError(str(resp.error))
    return resp.data[0] if resp.data else None


def delete_configuration(config_id: str, tenant_id: str) -> None:
    resp = (
        supabase.table("email_configurations")
        .delete()
        .eq("id", config_id)
        .eq("tenant_id", tenant_id)
        .execute()
    )
    if getattr(resp, "error", None):
        raise RuntimeError(str(resp.error))


def list_notifications(tenant_id: str) -> List[Dict[str, Any]]:
    resp = (
        supabase.table("email_notifications")
        .select("*")
        .eq("tenant_id", tenant_id)
        .order("event_name")
        .execute()
    )
    return resp.data or []


def get_notification_by_event(tenant_id: str, event_code: str) -> Optional[Dict[str, Any]]:
    resp = (
        supabase.table("email_notifications")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("event_code", event_code)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    return rows[0] if rows else None


def update_notification(notification_id: str, tenant_id: str, email_enabled: bool) -> Optional[Dict[str, Any]]:
    resp = (
        supabase.table("email_notifications")
        .update({"email_enabled": email_enabled, "updated_at": _now()})
        .eq("id", notification_id)
        .eq("tenant_id", tenant_id)
        .execute()
    )
    if getattr(resp, "error", None):
        raise RuntimeError(str(resp.error))
    return resp.data[0] if resp.data else None


def list_templates(tenant_id: str) -> List[Dict[str, Any]]:
    resp = (
        supabase.table("email_templates")
        .select("*")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .execute()
    )
    return resp.data or []


def get_template(template_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    resp = (
        supabase.table("email_templates")
        .select("*")
        .eq("id", template_id)
        .eq("tenant_id", tenant_id)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    return rows[0] if rows else None


def get_active_template_for_event(tenant_id: str, event_code: str) -> Optional[Dict[str, Any]]:
    resp = (
        supabase.table("email_templates")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("event_code", event_code)
        .eq("is_active", True)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    return rows[0] if rows else None


def insert_template(data: Dict[str, Any]) -> Dict[str, Any]:
    resp = supabase.table("email_templates").insert(data).execute()
    if getattr(resp, "error", None):
        raise RuntimeError(str(resp.error))
    return resp.data[0] if resp.data else data


def update_template(template_id: str, tenant_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    updates["updated_at"] = _now()
    resp = (
        supabase.table("email_templates")
        .update(updates)
        .eq("id", template_id)
        .eq("tenant_id", tenant_id)
        .execute()
    )
    if getattr(resp, "error", None):
        raise RuntimeError(str(resp.error))
    return resp.data[0] if resp.data else None


def delete_template(template_id: str, tenant_id: str) -> None:
    resp = (
        supabase.table("email_templates")
        .delete()
        .eq("id", template_id)
        .eq("tenant_id", tenant_id)
        .execute()
    )
    if getattr(resp, "error", None):
        raise RuntimeError(str(resp.error))


def resolve_user_by_email(email: str, tenant_id: str) -> Dict[str, str]:
    normalized = (email or "").strip().lower()
    if not normalized:
        return {"email": "", "name": "User"}
    row = execute_query(
        """
        SELECT COALESCE(NULLIF(TRIM(full_name), ''), '') AS display_name,
               email
        FROM users
        WHERE LOWER(email) = LOWER(%s)
          AND (tenant_id::text = %s OR tenant_id IS NULL)
        ORDER BY is_active DESC NULLS LAST, updated_at DESC NULLS LAST
        LIMIT 1
        """,
        (normalized, str(tenant_id)),
        fetch_one=True,
    )
    if not row:
        local = normalized.split("@")[0].replace(".", " ").replace("_", " ").title()
        return {"email": normalized, "name": local or "User"}
    display = row.get("display_name") or row.get("email") or normalized
    return {"email": row.get("email") or normalized, "name": display}


def resolve_user_display(user_id: Optional[str]) -> str:
    if not user_id:
        return ""
    row = execute_query(
        """
        SELECT COALESCE(NULLIF(TRIM(full_name), ''), email, '') AS display_name,
               email
        FROM users
        WHERE uuid_id::text = %s OR id = %s
        LIMIT 1
        """,
        (str(user_id), str(user_id)),
        fetch_one=True,
    )
    if not row:
        return str(user_id)
    return row.get("display_name") or row.get("email") or str(user_id)

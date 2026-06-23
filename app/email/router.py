"""Email configuration, notifications, and templates API."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request

from app.email import repository as repo
from app.core.config import FRONTEND_PUBLIC_URL
from app.email.constants import EMAIL_PROVIDERS, EVENT_CODES, TEMPLATE_VARIABLES
from app.email.email_assets import INLINE_LOGO_CID
from app.email.email_service import EmailService
from app.email.html_templates import default_create_ticket_html_template
from services.auth_service import auth_guard
from services.rbac_service import is_global_superadmin, is_superadmin, require_permission

router = APIRouter(prefix="/email", tags=["email"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MASKED_PASSWORD = "********"


def _tenant_id(user: Dict[str, Any]) -> str:
    return user.get("tenant_id") or "00000000-0000-0000-0000-000000000001"


def require_admin(user: Dict[str, Any], tenant_id: str) -> None:
    user_id = user.get("user_id") or user.get("id")
    if not (is_global_superadmin(user_id) or is_superadmin(user_id, tenant_id)):
        raise HTTPException(status_code=403, detail="Admin privileges required")


def _validate_email(value: str, field: str) -> str:
    email = (value or "").strip()
    if not email or not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail=f"Valid {field} is required")
    return email


def _validate_smtp_payload(payload: Dict[str, Any], *, require_password: bool) -> Dict[str, Any]:
    name = (payload.get("configuration_name") or "").strip()
    host = (payload.get("smtp_host") or "").strip()
    provider = (payload.get("provider") or "generic_smtp").strip()
    from_email = _validate_email(payload.get("from_email"), "from email address")
    from_name = (payload.get("from_name") or "").strip() or None

    try:
        port = int(payload.get("smtp_port"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="SMTP port must be a number")
    if port < 1 or port > 65535:
        raise HTTPException(status_code=400, detail="SMTP port must be between 1 and 65535")

    if not name:
        raise HTTPException(status_code=400, detail="Configuration name is required")
    if not host:
        raise HTTPException(status_code=400, detail="SMTP host is required")

    auth_required = bool(payload.get("authentication_required", True))
    username = (payload.get("username") or "").strip() or None
    password = payload.get("password")
    if password == _MASKED_PASSWORD:
        password = None
    password = (password or "").strip() or None

    if auth_required:
        if not username:
            raise HTTPException(status_code=400, detail="SMTP username is required when authentication is enabled")
        if require_password and not password:
            raise HTTPException(status_code=400, detail="SMTP password is required when authentication is enabled")

    return {
        "configuration_name": name,
        "provider": provider,
        "smtp_host": host,
        "smtp_port": port,
        "authentication_required": auth_required,
        "username": username,
        "password": password,
        "from_email": from_email,
        "from_name": from_name,
        "is_active": bool(payload.get("is_active", False)),
    }


def _config_for_test(payload: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    validated = _validate_smtp_payload(payload, require_password=existing is None)
    if existing:
        if not validated.get("password"):
            validated["password"] = existing.get("password")
    return validated


# --- Metadata ---

@router.get("/events")
@require_permission("email_retrieve")
async def list_events(Authorization: Optional[str] = Header(None)):
    auth_guard(Authorization)
    return {
        "data": [{"event_code": k, "event_name": v} for k, v in EVENT_CODES.items()],
        "error": None,
    }


@router.get("/providers")
@require_permission("email_retrieve")
async def list_providers(Authorization: Optional[str] = Header(None)):
    auth_guard(Authorization)
    return {"data": EMAIL_PROVIDERS, "error": None}


@router.get("/template-variables")
@require_permission("email_retrieve")
async def list_template_variables(Authorization: Optional[str] = Header(None)):
    auth_guard(Authorization)
    return {"data": TEMPLATE_VARIABLES, "error": None}


@router.get("/branding")
@require_permission("email_retrieve")
async def get_email_branding(Authorization: Optional[str] = Header(None)):
    auth_guard(Authorization)
    return {
        "data": {
            "app_name": "Master Minds",
            "logo_cid": INLINE_LOGO_CID,
            "logo_embedded": True,
            "frontend_url": FRONTEND_PUBLIC_URL,
            "brand_color": "#D6FF1F",
        },
        "error": None,
    }


@router.get("/templates/default/create-ticket")
@require_permission("email_retrieve")
async def get_default_create_ticket_template(Authorization: Optional[str] = Header(None)):
    auth_guard(Authorization)
    return {
        "data": {
            "template_name": "Ticket Created Notification",
            "event_code": "CREATE_TICKET",
            "subject": "Ticket Created - {{ticket_id}}",
            "body": default_create_ticket_html_template(),
            "is_active": True,
        },
        "error": None,
    }


# --- SMTP configurations ---

@router.get("/configurations")
@require_permission("email_retrieve")
async def get_configurations(Authorization: Optional[str] = Header(None)):
    user = auth_guard(Authorization)
    tenant_id = _tenant_id(user)
    require_admin(user, tenant_id)
    return {"data": repo.list_configurations(tenant_id), "error": None}


@router.post("/configurations")
@require_permission("email_create")
async def create_configuration(request: Request, Authorization: Optional[str] = Header(None)):
    user = auth_guard(Authorization)
    tenant_id = _tenant_id(user)
    require_admin(user, tenant_id)

    payload = await request.json()
    auth_required = bool(payload.get("authentication_required", True))
    has_password = (payload.get("password") or "").strip() not in ("", _MASKED_PASSWORD)
    validated = _validate_smtp_payload(payload, require_password=auth_required and has_password)

    if validated["is_active"]:
        repo.deactivate_all_configurations(tenant_id)

    now = datetime.now(timezone.utc).isoformat()
    data = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        **validated,
        "created_at": now,
        "updated_at": now,
    }
    created = repo.insert_configuration(data)
    return {"data": repo._mask_config(created), "error": None}


@router.put("/configurations/{config_id}")
@require_permission("email_update")
async def update_configuration(config_id: str, request: Request, Authorization: Optional[str] = Header(None)):
    user = auth_guard(Authorization)
    tenant_id = _tenant_id(user)
    require_admin(user, tenant_id)

    existing = repo.get_configuration(config_id, tenant_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Configuration not found")

    payload = await request.json()
    validated = _validate_smtp_payload(payload, require_password=False)
    if not validated.get("password"):
        validated.pop("password", None)

    if validated.get("is_active"):
        repo.deactivate_all_configurations(tenant_id, except_id=config_id)

    updated = repo.update_configuration(config_id, tenant_id, validated)
    return {"data": repo._mask_config(updated), "error": None}


@router.delete("/configurations/{config_id}")
@require_permission("email_delete")
async def delete_configuration(config_id: str, Authorization: Optional[str] = Header(None)):
    user = auth_guard(Authorization)
    tenant_id = _tenant_id(user)
    require_admin(user, tenant_id)

    existing = repo.get_configuration(config_id, tenant_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Configuration not found")

    repo.delete_configuration(config_id, tenant_id)
    return {"data": {"id": config_id}, "error": None}


@router.post("/configurations/test")
@require_permission("email_update")
async def test_configuration_payload(request: Request, Authorization: Optional[str] = Header(None)):
    user = auth_guard(Authorization)
    tenant_id = _tenant_id(user)
    require_admin(user, tenant_id)

    payload = await request.json()
    config_id = payload.get("id")
    existing = repo.get_configuration(config_id, tenant_id) if config_id else None
    config = _config_for_test(payload, existing)

    ok, message = await EmailService.test_connection_async(config)
    return {"data": {"success": ok, "message": message}, "error": None}


@router.post("/configurations/{config_id}/test")
@require_permission("email_update")
async def test_saved_configuration(config_id: str, Authorization: Optional[str] = Header(None)):
    user = auth_guard(Authorization)
    tenant_id = _tenant_id(user)
    require_admin(user, tenant_id)

    existing = repo.get_configuration(config_id, tenant_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Configuration not found")

    ok, message = await EmailService.test_connection_async(existing)
    return {"data": {"success": ok, "message": message}, "error": None}


# --- Notifications ---

@router.get("/notifications")
@require_permission("email_retrieve")
async def get_notifications(Authorization: Optional[str] = Header(None)):
    user = auth_guard(Authorization)
    tenant_id = _tenant_id(user)
    require_admin(user, tenant_id)
    return {"data": repo.list_notifications(tenant_id), "error": None}


@router.put("/notifications")
@require_permission("email_update")
async def update_notifications(request: Request, Authorization: Optional[str] = Header(None)):
    user = auth_guard(Authorization)
    tenant_id = _tenant_id(user)
    require_admin(user, tenant_id)

    payload = await request.json()
    items = payload.get("notifications") or payload.get("data") or []
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="notifications array is required")

    updated_rows = []
    for item in items:
        notification_id = item.get("id")
        if not notification_id:
            continue
        email_enabled = bool(item.get("email_enabled"))
        row = repo.update_notification(notification_id, tenant_id, email_enabled)
        if row:
            updated_rows.append(row)

    return {"data": updated_rows, "error": None}


# --- Templates ---

@router.get("/templates")
@require_permission("email_retrieve")
async def get_templates(Authorization: Optional[str] = Header(None)):
    user = auth_guard(Authorization)
    tenant_id = _tenant_id(user)
    require_admin(user, tenant_id)
    return {"data": repo.list_templates(tenant_id), "error": None}


def _validate_template_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    name = (payload.get("template_name") or "").strip()
    event_code = (payload.get("event_code") or "").strip().upper()
    subject = (payload.get("subject") or "").strip()
    body = (payload.get("body") or "").strip()

    if not name:
        raise HTTPException(status_code=400, detail="Template name is required")
    if event_code not in EVENT_CODES:
        raise HTTPException(status_code=400, detail="Invalid event code")
    if not subject:
        raise HTTPException(status_code=400, detail="Subject is required")
    if not body:
        raise HTTPException(status_code=400, detail="Email body is required")

    return {
        "template_name": name,
        "event_code": event_code,
        "subject": subject,
        "body": body,
        "is_active": bool(payload.get("is_active", True)),
    }


@router.post("/templates")
@require_permission("email_create")
async def create_template(request: Request, Authorization: Optional[str] = Header(None)):
    user = auth_guard(Authorization)
    tenant_id = _tenant_id(user)
    require_admin(user, tenant_id)

    payload = await request.json()
    validated = _validate_template_payload(payload)
    now = datetime.now(timezone.utc).isoformat()
    data = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        **validated,
        "created_at": now,
        "updated_at": now,
    }
    created = repo.insert_template(data)
    return {"data": created, "error": None}


@router.put("/templates/{template_id}")
@require_permission("email_update")
async def update_template(template_id: str, request: Request, Authorization: Optional[str] = Header(None)):
    user = auth_guard(Authorization)
    tenant_id = _tenant_id(user)
    require_admin(user, tenant_id)

    existing = repo.get_template(template_id, tenant_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Template not found")

    payload = await request.json()
    validated = _validate_template_payload(payload)
    updated = repo.update_template(template_id, tenant_id, validated)
    return {"data": updated, "error": None}


@router.delete("/templates/{template_id}")
@require_permission("email_delete")
async def delete_template(template_id: str, Authorization: Optional[str] = Header(None)):
    user = auth_guard(Authorization)
    tenant_id = _tenant_id(user)
    require_admin(user, tenant_id)

    existing = repo.get_template(template_id, tenant_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Template not found")

    repo.delete_template(template_id, tenant_id)
    return {"data": {"id": template_id}, "error": None}

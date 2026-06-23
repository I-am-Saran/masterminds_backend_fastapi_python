"""Workflow configuration API auth — Super Admin or workflows module permission."""

from typing import Any, Dict, Optional

from fastapi import HTTPException, Header

from services.auth_service import auth_guard
from services.rbac_service import check_permission, is_global_superadmin, is_superadmin


def get_workflow_admin_context(
    Authorization: Optional[str] = Header(None),
    action: str = "retrieve",
) -> Dict[str, Any]:
    auth = auth_guard(Authorization)
    user_id = auth.get("user_id")
    tenant_id = auth.get("tenant_id") or "00000000-0000-0000-0000-000000000001"
    if user_id and (is_global_superadmin(user_id) or is_superadmin(user_id, tenant_id)):
        auth["tenant_id"] = tenant_id
        return auth
    if not user_id or not check_permission(user_id, tenant_id, "workflows", action):
        raise HTTPException(
            status_code=403,
            detail=f"You do not have permission to {action} workflow definitions",
        )
    auth["tenant_id"] = tenant_id
    return auth

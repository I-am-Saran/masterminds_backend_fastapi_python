from fastapi import APIRouter, HTTPException, Request, Header, Query
from typing import Optional, Dict, Any
from services.db_service import local_db as supabase
from services.rbac_service import (
    get_user_roles,
    check_permission,
    get_all_roles,
    create_role,
    update_role_permissions,
    assign_role_to_user,
    remove_role_from_user,
    get_role_permissions,
    is_superadmin,
    is_global_superadmin,
)
from services.rbac_service import require_permission
from utils.error_handler import handle_endpoint_error
from services.auth_service import get_user_from_token, auth_guard
from app.rbac.permission_modules import (
    ACTIVE_PERMISSION_MODULES,
    get_permission_module_catalog,
    normalize_module_permissions,
)

router = APIRouter()


@router.get("/roles")
@require_permission("roles_retrieve")
async def get_roles(tenant_id: str = Query(default="00000000-0000-0000-0000-000000000001"), Authorization: Optional[str] = Header(default=None)):
    endpoint = "/roles"
    try:
        auth_data = auth_guard(Authorization)
        user_id = auth_data.get("user_id")
        
        # Secure tenant_id logic
        user_tenant_id = auth_data.get("tenant_id")
        effective_tenant = user_tenant_id or tenant_id or "00000000-0000-0000-0000-000000000001"
        
        if tenant_id and tenant_id != user_tenant_id:
             if is_global_superadmin(user_id):
                 effective_tenant = tenant_id
             else:
                 # Force user's tenant if not superadmin
                 effective_tenant = user_tenant_id

        roles = get_all_roles(effective_tenant)
        return {"data": roles, "error": None}
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "get_roles", return_dict=True, tenant_id=tenant_id)

@router.get("/roles/{role_id}")
@require_permission("roles_retrieve")
async def get_role(role_id: str, tenant_id: str = Query(default="00000000-0000-0000-0000-000000000001"), Authorization: Optional[str] = Header(default=None)):
    endpoint = f"/roles/{role_id}"
    try:
        auth_data = auth_guard(Authorization)
        user = auth_data.get("user", {})
        current_user_id = user.get("user_id") or user.get("id")
        
        # Secure tenant logic
        token_tenant_id = auth_data.get("tenant_id")
        effective_tenant = token_tenant_id or tenant_id or "00000000-0000-0000-0000-000000000001"
        
        if tenant_id and tenant_id != token_tenant_id:
            if is_global_superadmin(current_user_id):
                effective_tenant = tenant_id
            else:
                effective_tenant = token_tenant_id
        
        user_tenant_id = effective_tenant

        if not is_global_superadmin(current_user_id):
            user_roles = get_user_roles(current_user_id, user_tenant_id)
            user_has_role = False
            for user_role in user_roles:
                role_id_from_user = user_role.get("role_id")
                if not role_id_from_user and user_role.get("roles"):
                    roles_data = user_role.get("roles")
                    if isinstance(roles_data, dict):
                        role_id_from_user = roles_data.get("id")
                    elif isinstance(roles_data, list) and len(roles_data) > 0:
                        role_id_from_user = roles_data[0].get("id")
                if role_id_from_user == role_id:
                    user_has_role = True
                    break
            if not user_has_role:
                has_permission = check_permission(current_user_id, user_tenant_id, "roles", "retrieve")
                if not has_permission:
                    raise HTTPException(status_code=403, detail="You do not have permission to retrieve this role")
        
        resp = supabase.table("roles").select("*").eq("id", role_id).eq("tenant_id", effective_tenant).limit(1).execute()
        role = resp.data[0] if resp.data else None
        if not role and is_global_superadmin(current_user_id):
            resp = supabase.table("roles").select("*").eq("id", role_id).limit(1).execute()
            role = resp.data[0] if resp.data else None
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
        permissions = get_role_permissions(role_id, role.get("tenant_id") or effective_tenant)
        role["permissions"] = [
            perm
            for perm in (permissions or [])
            if perm.get("module_name") in ACTIVE_PERMISSION_MODULES
        ]
        return {"data": role, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "get_role", return_dict=True, role_id=role_id, tenant_id=tenant_id)

@router.post("/roles")
@require_permission("roles_create")
async def create_role_endpoint(request: Request, Authorization: Optional[str] = Header(default=None)):
    endpoint = "/roles"
    payload: Dict[str, Any] = {}
    try:
        payload = await request.json()
        auth_data = auth_guard(Authorization)
        user = auth_data.get("user", {})
        user_id = user.get("user_id") or user.get("id") or user.get("user", {}).get("id")
        
        # Secure tenant logic
        token_tenant_id = auth_data.get("tenant_id")
        requested_tenant_id = payload.get("tenant_id")
        tenant_id = token_tenant_id or "00000000-0000-0000-0000-000000000001"
        
        if requested_tenant_id and requested_tenant_id != token_tenant_id:
            if is_global_superadmin(user_id):
                tenant_id = requested_tenant_id
            # Else ignore requested_tenant_id and use token_tenant_id
            
        role_name = payload.get("role_name")
        role_description = payload.get("role_description")
        if not role_name:
            raise HTTPException(status_code=400, detail="role_name is required")
        role = create_role(tenant_id, role_name, role_description, user_id)
        if not role:
            raise HTTPException(status_code=400, detail="Failed to create role")
        return {"data": role, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "create_role", return_dict=True, tenant_id=payload.get("tenant_id"), role_name=payload.get("role_name"))

@router.put("/roles/{role_id}")
@require_permission("roles_update")
async def update_role_endpoint(
    role_id: str,
    request: Request,
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = f"/roles/{role_id}"
    payload: Dict[str, Any] = {}
    try:
        payload = await request.json()
        auth_data = auth_guard(Authorization)
        user_id = auth_data.get("user_id") or auth_data.get("user", {}).get("id")
        
        # Secure tenant logic
        token_tenant_id = auth_data.get("tenant_id")
        requested_tenant_id = payload.get("tenant_id")
        tenant_id = token_tenant_id or "00000000-0000-0000-0000-000000000001"
        
        if requested_tenant_id and requested_tenant_id != token_tenant_id:
            if is_global_superadmin(user_id):
                tenant_id = requested_tenant_id

        role_name = payload.get("role_name")
        role_description = payload.get("role_description")
        is_active = payload.get("is_active", True)
        
        # Verify role exists in this tenant
        resp = supabase.table("roles").select("*").eq("id", role_id).eq("tenant_id", tenant_id).limit(1).execute()
        
        if not resp.data and is_global_superadmin(user_id):
            # Superadmin can update roles in other tenants if they know the ID
            # But we already set tenant_id above. If they provided a tenant_id, we use that.
            # If they didn't, we used their own. 
            # If the role is in another tenant, and they didn't provide that tenant_id, this fails.
            # Let's check if role exists globally for superadmin
            resp = supabase.table("roles").select("*").eq("id", role_id).limit(1).execute()
            if resp.data:
                tenant_id = resp.data[0].get("tenant_id") or tenant_id
        
        if not resp.data:
            raise HTTPException(status_code=404, detail="Role not found")
            
        update_data = {}
        if role_name is not None:
            update_data["role_name"] = role_name
        if role_description is not None:
            update_data["role_description"] = role_description
        if is_active is not None:
            update_data["is_active"] = is_active
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")
        resp = supabase.table("roles").eq("id", role_id).eq("tenant_id", tenant_id).update(update_data).execute()
        if resp.error:
            raise HTTPException(status_code=400, detail=f"Failed to update role: {resp.error}")
        updated_role = resp.data[0] if resp.data else None
        return {"data": updated_role, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "update_role", return_dict=True, role_id=role_id, tenant_id=payload.get("tenant_id"))

@router.put("/roles/{role_id}/permissions")
@require_permission("roles_update")
async def update_role_permissions_endpoint(
    role_id: str,
    request: Request,
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = f"/roles/{role_id}/permissions"
    payload: Dict[str, Any] = {}
    try:
        payload = await request.json()
        auth_data = auth_guard(Authorization)
        user_id = auth_data.get("user_id")
        
        # Secure tenant logic
        token_tenant_id = auth_data.get("tenant_id")
        requested_tenant_id = payload.get("tenant_id")
        tenant_id = token_tenant_id or "00000000-0000-0000-0000-000000000001"
        
        if requested_tenant_id and requested_tenant_id != token_tenant_id:
            if is_global_superadmin(user_id):
                tenant_id = requested_tenant_id
                
        module_name = (payload.get("module_name") or "").strip()
        permissions = payload.get("permissions", {})
        if not module_name:
            raise HTTPException(status_code=400, detail="module_name is required")
        if module_name not in ACTIVE_PERMISSION_MODULES:
            raise HTTPException(status_code=400, detail=f"Unknown or inactive permission module: {module_name}")
        permissions = normalize_module_permissions(module_name, permissions)
        success, error_msg = update_role_permissions(role_id, tenant_id, module_name, permissions)
        if not success:
            detail = error_msg or "Failed to update permissions. Check server logs for details."
            raise HTTPException(status_code=400, detail=detail)
        return {"data": {"success": True}, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "update_role_permissions", return_dict=True, role_id=role_id, module_name=payload.get("module_name"), tenant_id=payload.get("tenant_id"))

@router.get("/permissions/modules")
async def get_permission_modules(Authorization: Optional[str] = Header(default=None)):
    """Return curated Masterminds permission modules for the Roles matrix."""
    endpoint = "/permissions/modules"
    try:
        auth_guard(Authorization)
        return {"data": get_permission_module_catalog(), "error": None}
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "get_permission_modules", return_dict=True)

@router.get("/permissions/dashboards")
async def get_accessible_dashboards(Authorization: Optional[str] = Header(default=None)):
    """
    Returns a dynamic list of dashboards the current user can access, driven by RBAC.
    Each item contains: name, path, module, icon (key).
    Future dashboards can be added by updating this backend registry without frontend changes.
    """
    endpoint = "/permissions/dashboards"
    try:
        auth_data = auth_guard(Authorization)
        user = auth_data.get("user", {}) if isinstance(auth_data, dict) else {}
        user_id = user.get("user_id") or user.get("id") or (user.get("user") or {}).get("id")
        tenant_id = auth_data.get("tenant_id") if isinstance(auth_data, dict) else None
        if not tenant_id:
            tenant_id = "00000000-0000-0000-0000-000000000001"

        # Registry of available dashboards with their RBAC modules and routes
        registry = [
            {"name": "Compliance Dashboard", "path": "/dashboard", "module": "dashboard", "icon": "dashboard"},
            {"name": "QA Dashboard", "path": "/qa-dashboard", "module": "qa_dashboard", "icon": "dashboard"},
            {"name": "Portfolio Quality", "path": "/dashboard?tab=portfolio", "module": "qa_dashboard", "icon": "dashboard"},
            {"name": "ET Dashboard", "path": "/et-dashboard", "module": "builds", "icon": "dashboard"},
        ]

        # Super admins see all dashboards
        if user_id and is_global_superadmin(user_id):
            return {"data": registry, "error": None}
        if user_id and is_superadmin(user_id, tenant_id):
            return {"data": registry, "error": None}

        # Filter by permission
        accessible = []
        for item in registry:
            try:
                if user_id and check_permission(user_id, tenant_id, item["module"], "retrieve"):
                    accessible.append(item)
            except Exception:
                # If permission check raises, skip this item
                continue

        return {"data": accessible, "error": None}
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "get_accessible_dashboards", return_dict=True)

@router.get("/permissions/check")
async def check_permission_endpoint(
    module: str = Query(...),
    action: str = Query(...),
    tenant_id: str = Query(default="00000000-0000-0000-0000-000000000001"),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = "/permissions/check"
    try:
        auth_data = auth_guard(Authorization)
        user = auth_data.get("user", {})
        user_id = user.get("user_id") or user.get("id") or (user.get("user") or {}).get("id")
        if not user_id:
            return {"data": {"has_permission": False}, "error": "User ID not found"}
        effective_tenant = tenant_id or auth_data.get("tenant_id") or "00000000-0000-0000-0000-000000000001"
        has_permission = check_permission(user_id, effective_tenant, module, action)
        return {"data": {"has_permission": has_permission}, "error": None}
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "check_permission", return_dict=True, module=module, action=action, tenant_id=tenant_id)


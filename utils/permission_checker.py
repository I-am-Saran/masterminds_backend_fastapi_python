"""
Permission Checker Utility
Provides decorator and helper functions for permission validation
"""

from functools import wraps
from fastapi import HTTPException, Header, Request
from typing import Optional, Callable, Any
from services.auth_service import get_user_from_token
from services.rbac_service import check_permission, is_global_superadmin


def get_user_id_from_token(authorization: Optional[str]) -> Optional[str]:
    """Extract user ID from authorization token using the same method as auth_guard."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    
    token = authorization.split(" ", 1)[1].strip()
    user = get_user_from_token(token)
    if not user:
        return None
    
    # Extract user_id from the user dict (same structure as auth_guard uses)
    user_id = user.get("user_id")
    return user_id


def require_permission_legacy(module: str, action: str, tenant_id_param: str = "tenant_id"):
    """
    Legacy decorator to require permission for an endpoint (kept for backward compatibility).
    
    Usage:
        @require_permission_legacy("security_controls", "retrieve", "tenant_id")
        async def get_security_controls(tenant_id: str, ...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get authorization header
            authorization = kwargs.get("Authorization") or kwargs.get("authorization")
            if not authorization:
                raise HTTPException(status_code=401, detail="Missing Authorization header")
            
            # Get user ID
            user_id = get_user_id_from_token(authorization)
            if not user_id:
                raise HTTPException(status_code=401, detail="Invalid or expired token")
            
            # Get tenant_id from kwargs or request
            tenant_id = kwargs.get(tenant_id_param)
            if not tenant_id:
                # Try to get from request body if it's a POST/PUT
                if hasattr(kwargs.get("payload"), "get"):
                    tenant_id = kwargs.get("payload", {}).get(tenant_id_param)
                if not tenant_id:
                    raise HTTPException(status_code=400, detail=f"Missing {tenant_id_param}")
            
            # Check permission
            has_permission = check_permission(user_id, tenant_id, module, action)
            if not has_permission:
                raise HTTPException(
                    status_code=403,
                    detail=f"You do not have permission to {action} {module}"
                )
            
            # Call original function
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


def require_permission(permission_code: str):
    """
    Simplified decorator that takes permission_code in format "module_action".
    
    Usage:
        @require_permission("department_create")
        async def create_department(payload: DepartmentCreate, tenant_id: str = Query(...), ...):
            ...
    
    The decorator will:
    1. Parse permission_code to extract module and action (e.g., "department_create" -> module="department", action="create")
    2. Extract user_id from Authorization header
    3. Extract tenant_id from function parameters (looks for tenant_id in kwargs, Query, or request body)
    4. Check permission using check_permission(user_id, tenant_id, module, action)
    5. Return 403 if permission denied
    """
    # Parse permission_code to extract module and action
    parts = permission_code.rsplit("_", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid permission_code format: {permission_code}. Expected format: 'module_action'")
    
    module = parts[0]
    action = parts[1]
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get authorization header
            authorization = kwargs.get("Authorization") or kwargs.get("authorization")
            if not authorization:
                raise HTTPException(status_code=401, detail="Missing Authorization header")
            
            # Get user ID and tenant_id from token
            token = authorization.split(" ", 1)[1].strip() if authorization else None
            user = get_user_from_token(token) if token else None
            
            if not user:
                raise HTTPException(status_code=401, detail="Invalid or expired token")
            
            user_id = user.get("user_id")
            if not user_id:
                raise HTTPException(status_code=401, detail="User ID not found in token")
            
            # --- GLOBAL SUPER ADMIN CHECK (EARLY EXIT) ---
            # Bypass all tenant/role checks for Super Admin
            if is_global_superadmin(user_id):
                print(f"[require_permission] User {user_id} is Global Super Admin - bypassing all checks")
                return await func(*args, **kwargs)
            # ---------------------------------------------
            
            # Get tenant_id from various sources (in priority order)
            tenant_id = None
            tenant_id_source = None
            
            # 1. Try from kwargs (Query parameters or path parameters) - highest priority
            tenant_id = kwargs.get("tenant_id")
            if tenant_id:
                tenant_id_source = "query/kwargs"
            
            # 2. Try from user's token (from auth service)
            if not tenant_id and user:
                tenant_id = user.get("tenant_id")
                if tenant_id:
                    tenant_id_source = "user token"
            
            # 3. Try from payload if it's a dict
            if not tenant_id:
                payload = kwargs.get("payload")
                if payload and isinstance(payload, dict):
                    tenant_id = payload.get("tenant_id")
                    if tenant_id:
                        tenant_id_source = "payload"
            
            # 4. Default tenant_id if not found (for backward compatibility)
            if not tenant_id:
                tenant_id = "00000000-0000-0000-0000-000000000001"
                tenant_id_source = "default"
            
            print(f"[require_permission] Permission check for {module}.{action}")
            print(f"[require_permission] user_id={user_id}, tenant_id={tenant_id} (from {tenant_id_source})")
            print(f"[require_permission] user data: {user}")
            
            # Check permission from database
            # This queries: user_roles -> roles -> permissions tables
            has_permission = check_permission(user_id, tenant_id, module, action)
            print(f"[require_permission] Permission check result: {has_permission}")
            
            if not has_permission:
                print(f"[require_permission] PERMISSION DENIED: user_id={user_id} does not have {module}.{action} permission")
                raise HTTPException(
                    status_code=403,
                    detail=f"You do not have permission to {action} {module}"
                )
            
            # Call original function
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


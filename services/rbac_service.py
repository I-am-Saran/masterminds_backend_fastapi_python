"""
RBAC Service - Role-Based Access Control service layer
Handles roles, permissions, and user-role assignments
"""

from typing import Optional, List, Dict, Any, Tuple, Set, Callable
from datetime import datetime, timezone
from functools import wraps
import inspect
import time
from fastapi import HTTPException
# COMMENTED OUT FOR LOCAL DEVELOPMENT - Using local PostgreSQL instead
# from services.supabase_client import supabase
from services.db_service import local_db as supabase  # Use local DB service
from services.request_context import get_request_context, add_timing_ms
import uuid

# Global registry to dynamically track all modules and actions
REGISTERED_PERMISSIONS: Set[Tuple[str, str]] = set()

def require_permission(permission_code: str):
    """
    Simplified decorator that takes permission_code in format "module_action".  
    """
    # Parse permission_code to extract module and action
    parts = permission_code.rsplit("_", 1)
    if len(parts) == 2:
        REGISTERED_PERMISSIONS.add((parts[0], parts[1]))
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if len(parts) != 2:
                raise ValueError(f"Invalid permission_code format: {permission_code}. Expected format: 'module_action'")
            module = parts[0]
            action = parts[1]
            
            # Get authorization header
            authorization = kwargs.get("Authorization") or kwargs.get("authorization")
            if not authorization:
                raise HTTPException(status_code=401, detail="Missing Authorization header")

            # Get user ID and tenant_id from token
            from services.auth_service import auth_guard
            auth_ctx = auth_guard(authorization)
            user = auth_ctx.get("user")

            if not user:
                raise HTTPException(status_code=401, detail="Invalid or expired token")

            user_id = user.get("user_id")
            if not user_id:
                raise HTTPException(status_code=401, detail="User ID not found in token")

            # Bypass all tenant/role checks for Super Admin
            if is_global_superadmin(user_id):
                result = func(*args, **kwargs)
                if inspect.isawaitable(result):
                    return await result
                return result

            # Get tenant_id from various sources
            tenant_id = kwargs.get("tenant_id")
            if not tenant_id and user:
                tenant_id = user.get("tenant_id")
            if not tenant_id:
                payload = kwargs.get("payload")
                if payload and isinstance(payload, dict):
                    tenant_id = payload.get("tenant_id")
            if not tenant_id:
                tenant_id = "00000000-0000-0000-0000-000000000001"

            # Check permission from database
            has_permission = check_permission(user_id, tenant_id, module, action)
            if not has_permission:
                raise HTTPException(
                    status_code=403,
                    detail=f"You do not have permission to {action} {module}"   
                )

            # Call original function (sync or async)
            result = func(*args, **kwargs)
            if inspect.isawaitable(result):
                return await result
            return result

        return wrapper
    return decorator


def get_user_roles(user_id: str, tenant_id: str) -> List[Dict[str, Any]]:
    """Get all roles assigned to a user."""
    ctx = get_request_context()
    cache = (ctx or {}).get("cache")
    cache_key = f"{user_id}:{tenant_id}"
    if isinstance(cache, dict):
        user_roles_cache = cache.get("user_roles")
        if isinstance(user_roles_cache, dict) and cache_key in user_roles_cache:
            return user_roles_cache[cache_key]

    try:
        print(f"[get_user_roles] Fetching roles for user_id={user_id}, tenant_id={tenant_id}")
        resp = supabase.table("user_roles").select(
            "*"
        ).eq("user_id", user_id).eq("tenant_id", tenant_id).execute()
        user_roles_list = resp.data or []
        print(f"[get_user_roles] Found {len(user_roles_list)} user_role(s) with tenant_id filter")
        
        # If no roles found with tenant_id, try without tenant_id filter as fallback
        if not user_roles_list:
            print(f"[get_user_roles] No roles found with tenant_id={tenant_id}, trying without tenant_id filter...")
            resp_fallback = supabase.table("user_roles").select(
                "*"
            ).eq("user_id", user_id).execute()
            user_roles_list = resp_fallback.data or []
            print(f"[get_user_roles] Found {len(user_roles_list)} user_role(s) without tenant_id filter")
        
        if not user_roles_list:
            return []
        
        # Manually join roles data for each user_role
        enriched_roles = []
        for user_role in user_roles_list:
            role_id = user_role.get("role_id")
            if not role_id:
                continue
            
            # Fetch the role details
            try:
                role_resp = supabase.table("roles").select("*").eq("id", role_id).eq("tenant_id", tenant_id).limit(1).execute()
                role_data = role_resp.data[0] if role_resp.data and len(role_resp.data) > 0 else None
                
                if role_data:
                    # Add the role data to the user_role object
                    user_role["roles"] = role_data
                    enriched_roles.append(user_role)
                else:
                    # If role not found with tenant_id, try without tenant_id
                    role_resp_fallback = supabase.table("roles").select("*").eq("id", role_id).limit(1).execute()
                    role_data_fallback = role_resp_fallback.data[0] if role_resp_fallback.data and len(role_resp_fallback.data) > 0 else None
                    if role_data_fallback:
                        user_role["roles"] = role_data_fallback
                        enriched_roles.append(user_role)
            except Exception as role_err:
                print(f"[get_user_roles] Error fetching role {role_id}: {role_err}")
                # Include user_role even if role fetch fails
                enriched_roles.append(user_role)
        
        print(f"[get_user_roles] Returning {len(enriched_roles)} enriched role(s)")
        if isinstance(cache, dict):
            cache.setdefault("user_roles", {})[cache_key] = enriched_roles
        return enriched_roles
    except Exception as e:
        print(f"Error getting user roles: {e}")
        import traceback
        traceback.print_exc()
        return []


# Email that is always treated as global super admin (no tenant_id validation)
SUPERADMIN_EMAIL = "superadmin@cavininfotech.com"


def _is_superadmin_by_email(user_id: str) -> bool:
    """Return True if user's email is the designated super admin email (case-insensitive)."""
    try:
        resp = supabase.table("users").select("email").eq("id", user_id).limit(1).execute()
        if not resp.data or len(resp.data) == 0:
            return False
        email = (resp.data[0].get("email") or "").strip().lower()
        return email == SUPERADMIN_EMAIL.lower()
    except Exception:
        return False

def _get_user_accessible_projects_data(user_id: str, tenant_id: str, skip_team_restriction: bool = False) -> Optional[List[Dict[str, Any]]]:
    """
    Helper to get the list of project dicts a user has access to.
    Returns None if superadmin.
    """
    if is_global_superadmin(user_id) or is_superadmin(user_id, tenant_id):
        return None
    if skip_team_restriction:
        return None  # None = unrestricted, same as superadmin — used by Task Tracker
        
    try:
        from services.db_service import execute_query
        
        user_email_query = "SELECT email FROM users WHERE id = %s"
        user_row = execute_query(user_email_query, (user_id,), fetch_one=True)
        user_email = user_row.get("email") if user_row else None
        
        # 2. Get user's teams
        if user_email:
            user_teams_query = """
                SELECT team_id FROM team_users 
                WHERE (
                    TRIM(user_id) = %s OR TRIM(user_id) = %s OR
                    LOWER(TRIM(user_id)) = LOWER(TRIM(%s)) OR LOWER(TRIM(user_id)) = LOWER(TRIM(%s))
                )
                AND (tenant_id = %s OR tenant_id IS NULL)
            """
            user_teams = execute_query(user_teams_query, (user_id, user_email, user_id, user_email, tenant_id))
        else:
            user_teams_query = """
                SELECT team_id FROM team_users 
                WHERE (
                    TRIM(user_id) = %s OR LOWER(TRIM(user_id)) = LOWER(TRIM(%s))
                )
                AND (tenant_id = %s OR tenant_id IS NULL)
            """
            user_teams = execute_query(user_teams_query, (user_id, user_id, tenant_id))
        
        if not user_teams:
            return []
            
        team_ids = [str(t.get("team_id")) for t in user_teams if t.get("team_id")]
        
        if not team_ids:
            return []
            
        placeholders = ', '.join(['%s'] * len(team_ids))
        projects_query = f"""
            SELECT DISTINCT p.id, p.application_name 
            FROM projects p
            JOIN team_projects tp ON (tp.project_id = CAST(p.id AS TEXT) OR tp.project_id = p.application_name)
            WHERE tp.team_id IN ({placeholders}) 
            AND p.tenant_id = %s
            AND COALESCE(p.is_deleted, false) = false
        """
        params = tuple(team_ids) + (tenant_id,)
        projects = execute_query(projects_query, params)
        
        return projects or []
    except Exception as e:
        import logging
        logging.error(f"Error getting accessible projects: {e}")
        return []

def get_user_accessible_projects(user_id: str, tenant_id: str, skip_team_restriction: bool = False) -> Optional[List[str]]:
    """
    Get the list of project IDs a user has access to based on their team assignments.
    Returns None if the user is a superadmin (has access to all projects).
    """
    projects = _get_user_accessible_projects_data(user_id, tenant_id, skip_team_restriction=skip_team_restriction)
    if projects is None:
        return None
    return [str(p.get("id")) for p in projects if p.get("id")]

def get_user_accessible_project_names(user_id: str, tenant_id: str, skip_team_restriction: bool = False) -> Optional[List[str]]:
    """
    Get the list of project names a user has access to.
    Returns None if user is superadmin.
    """
    projects = _get_user_accessible_projects_data(user_id, tenant_id, skip_team_restriction=skip_team_restriction)
    if projects is None:
        return None
    return [p.get("application_name") for p in projects if p.get("application_name")]


def is_global_superadmin(user_id: str) -> bool:
    """
    Check if user is a Global Super Admin.
    Global Super Admin is ABSOLUTE and bypasses all tenant/role checks.
    1) Designated email superadmin@cavininfotech.com is always super admin.
    2) Otherwise checks all roles across all tenants for super admin role name.
    """
    ctx = get_request_context()
    cache = (ctx or {}).get("cache")
    if isinstance(cache, dict) and cache.get("is_global_superadmin") is not None:
        return bool(cache.get("is_global_superadmin"))

    try:
        if _is_superadmin_by_email(user_id):
            print(f"[is_global_superadmin] User {user_id} is Super Admin by email ({SUPERADMIN_EMAIL})")
            if isinstance(cache, dict):
                cache["is_global_superadmin"] = True
            return True
        
        super_admin_variants = ["super admin", "superadmin", "super_admin", "global super admin"]
        
        # Get all roles for the user across all tenants
        resp = supabase.table("user_roles").select("*").eq("user_id", user_id).execute()
        all_user_roles = resp.data or []
        
        for ur in all_user_roles:
            role_id = ur.get("role_id")
            if not role_id:
                continue
                
            # Check role name
            role_resp = supabase.table("roles").select("role_name").eq("id", role_id).limit(1).execute()
            if role_resp.data:
                role_name = role_resp.data[0].get("role_name", "")
                if role_name and str(role_name).lower() in super_admin_variants:
                    print(f"[is_global_superadmin] User {user_id} is Global Super Admin ({role_name})")
                    if isinstance(cache, dict):
                        cache["is_global_superadmin"] = True
                    return True
                    
        if isinstance(cache, dict):
            cache["is_global_superadmin"] = False
        return False
    except Exception as e:
        print(f"Error checking global superadmin status: {e}")
        return False


def is_superadmin(
    user_id: str,
    tenant_id: str,
    global_superadmin: Optional[bool] = None,
    user_roles: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """
    Check if user has Super Admin role.
    Super Admin users have full access including viewing soft-deleted items.
    Checks both tenant-specific roles and global roles.
    """
    try:
        # 1. Global Super Admin Check (Absolute Priority)
        if global_superadmin is None:
            global_superadmin = is_global_superadmin(user_id)
        if global_superadmin:
            return True
            
        super_admin_variants = ["super admin", "superadmin", "super_admin", "global super admin"]
        
        # 2. Check specific tenant roles (Legacy fallback)
        roles = user_roles if user_roles is not None else get_user_roles(user_id, tenant_id)
        for user_role in roles:
            role = user_role.get("roles", {})
            if isinstance(role, dict):
                role_name = role.get("role_name", "")
                if role_name and str(role_name).lower() in super_admin_variants:
                    print(f"[is_superadmin] User {user_id} is Tenant Super Admin ({role_name})")
                    return True
        
        return False
    except Exception as e:
        print(f"Error checking superadmin status: {e}")
        return False


def get_role_permissions(role_id: str, tenant_id: str) -> List[Dict[str, Any]]:
    """Get all permissions for a role."""
    ctx = get_request_context()
    cache = (ctx or {}).get("cache")
    if isinstance(cache, dict):
        rp_cache = cache.get("role_permissions")
        if isinstance(rp_cache, dict) and role_id in rp_cache:
            return rp_cache[role_id]

    try:
        print(f"[get_role_permissions] Fetching permissions for role_id={role_id}. Ignoring tenant_id filter to prevent mismatches.")
        resp = supabase.table("permissions").select("*").eq(
            "role_id", role_id
        ).execute()
        permissions = resp.data or []
        print(f"[get_role_permissions] Found {len(permissions)} permissions")
        if permissions:
            print(f"[get_role_permissions] Sample permission: {permissions[0]}")
        if isinstance(cache, dict):
            cache.setdefault("role_permissions", {})[role_id] = permissions
        return permissions
    except Exception as e:
        print(f"Error getting role permissions: {e}")
        import traceback
        traceback.print_exc()
        return []


def check_permission(
    user_id: str,
    tenant_id: str,
    module_name: str,
    action: str
) -> bool:
    """
    Check if user has permission for a specific action on a module.
    Actions: create, retrieve, update, delete, comment, create_task
    
    This function queries the database:
    1. Queries user_roles table to get user's roles
    2. Queries permissions table to get role permissions
    3. Checks if the specific module+action permission exists
    """
    t0 = time.perf_counter()
    ctx = get_request_context()
    cache = (ctx or {}).get("cache")
    perm_key = f"{user_id}:{tenant_id}:{module_name.lower()}:{action.lower()}"
    if isinstance(cache, dict):
        pc = cache.get("permission_checks")
        if isinstance(pc, dict) and perm_key in pc:
            return bool(pc[perm_key])

    try:
        global_sa = is_global_superadmin(user_id)
        if global_sa:
            print(f"[check_permission] User {user_id} is Global Super Admin - bypassing checks")
            if isinstance(cache, dict):
                cache.setdefault("permission_checks", {})[perm_key] = True
            return True

        user_roles = get_user_roles(user_id, tenant_id)

        if is_superadmin(user_id, tenant_id, global_superadmin=global_sa, user_roles=user_roles):
            print(f"[check_permission] User {user_id} is superadmin - granting permission: {module_name}.{action}")
            if isinstance(cache, dict):
                cache.setdefault("permission_checks", {})[perm_key] = True
            return True

        if not user_roles:
            print(f"[check_permission] No roles found for user_id={user_id}, tenant_id={tenant_id}")
            if isinstance(cache, dict):
                cache.setdefault("permission_checks", {})[perm_key] = False
            return False

        print(f"[check_permission] Found {len(user_roles)} role(s) for user_id={user_id}, tenant_id={tenant_id}")
        print(f"[check_permission] User roles data: {user_roles}")

        # Check each role for the permission
        for user_role in user_roles:
            # Handle both direct role_id and nested roles.role_id structure
            role_id = user_role.get("role_id")
            if not role_id and user_role.get("roles"):
                # Handle nested structure from Supabase join
                roles_data = user_role.get("roles")
                if isinstance(roles_data, dict):
                    role_id = roles_data.get("id")
                elif isinstance(roles_data, list) and len(roles_data) > 0:
                    role_id = roles_data[0].get("id")
            
            if not role_id:
                print(f"[check_permission] No role_id found in user_role: {user_role}")
                continue

            print(f"[check_permission] Checking role_id={role_id} for permission {module_name}.{action}")

            # Get permissions for this role from database
            permissions = get_role_permissions(role_id, tenant_id)
            print(f"[check_permission] Role {role_id} has {len(permissions)} permission(s)")
            print(f"[check_permission] Permissions for role {role_id}: {[p.get('module_name') for p in permissions]}")
            
            for perm in permissions:
                # Case-insensitive module name comparison
                perm_module = perm.get("module_name", "").lower()
                check_module = module_name.lower()
                
                if perm_module == check_module:
                    # Map action to permission field
                    action_map = {
                        "create": "can_create",
                        "retrieve": "can_retrieve",
                        "update": "can_update",
                        "delete": "can_delete",
                        "comment": "can_comment",
                        "create_task": "can_create_task",
                    }
                    perm_field = action_map.get(action.lower())
                    if perm_field:
                        perm_value = perm.get(perm_field)
                        print(f"[check_permission] Checking {perm_field} for {module_name}: {perm_value} (type: {type(perm_value)})")
                        # Check if permission is explicitly True (handle both boolean and string "true")
                        if perm_value is True or (isinstance(perm_value, str) and perm_value.lower() == "true"):
                            print(f"[check_permission] Permission GRANTED: {module_name}.{action} via role {role_id}")
                            if isinstance(cache, dict):
                                cache.setdefault("permission_checks", {})[perm_key] = True
                            return True
                        else:
                            print(f"[check_permission] Permission field {perm_field} is False or not set for {module_name}")

        print(f"[check_permission] Permission DENIED: {module_name}.{action} not found in any role")
        if isinstance(cache, dict):
            cache.setdefault("permission_checks", {})[perm_key] = False
        return False
    except Exception as e:
        print(f"[check_permission] Error checking permission: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        add_timing_ms("rbac", (time.perf_counter() - t0) * 1000.0)


def get_all_roles(tenant_id: str) -> List[Dict[str, Any]]:
    """Get all roles for a tenant."""
    try:
        resp = supabase.table("roles").select("*").eq(
            "tenant_id", tenant_id
        ).eq("is_active", True).execute()
        return resp.data or []
    except Exception as e:
        print(f"Error getting roles: {e}")
        return []


def create_role(
    tenant_id: str,
    role_name: str,
    role_description: Optional[str] = None,
    created_by: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Create a new role."""
    try:
        role_data = {
            "tenant_id": tenant_id,
            "role_name": role_name,
            "role_description": role_description,
            "is_system_role": False,
            "is_active": True,
            "created_by": created_by,
        }
        resp = supabase.table("roles").insert(role_data).execute()
        return resp.data[0] if resp.data else None
    except Exception as e:
        print(f"Error creating role: {e}")
        return None


def update_role_permissions(
    role_id: str,
    tenant_id: str,
    module_name: str,
    permissions: Dict[str, bool]
) -> Tuple[bool, Optional[str]]:
    """Update permissions for a role and module. Returns (success, error_message)."""
    try:
        # Check if permission exists
        existing = supabase.table("permissions").select("id").eq(
            "role_id", role_id
        ).eq("module_name", module_name).eq("tenant_id", tenant_id).execute()

        # Check for errors in existing query
        if getattr(existing, "error", None):
            error_msg = f"Error checking existing permissions: {existing.error}"
            print(error_msg)
            return False, error_msg

        # Ensure all boolean values are properly converted
        perm_data = {
            "tenant_id": tenant_id,
            "role_id": role_id,
            "module_name": module_name,
            "can_create": bool(permissions.get("can_create", False)),
            "can_retrieve": bool(permissions.get("can_retrieve", False)),
            "can_update": bool(permissions.get("can_update", False)),
            "can_delete": bool(permissions.get("can_delete", False)),
            "can_comment": bool(permissions.get("can_comment", False)),
            "can_create_task": bool(permissions.get("can_create_task", False)),
        }

        if existing.data and len(existing.data) > 0:
            # Update existing - only update the permission flags, not the key fields
            update_data = {
                "can_create": bool(permissions.get("can_create", False)),
                "can_retrieve": bool(permissions.get("can_retrieve", False)),
                "can_update": bool(permissions.get("can_update", False)),
                "can_delete": bool(permissions.get("can_delete", False)),
                "can_comment": bool(permissions.get("can_comment", False)),
                "can_create_task": bool(permissions.get("can_create_task", False)),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            print(f"Updating permission with id={existing.data[0]['id']}, data={update_data}")
            # Use explicit chaining to avoid issues
            try:
                table = supabase.table("permissions")
                if not hasattr(table, 'eq'):
                    raise ValueError(f"table() returned {type(table)}, expected TableProxy")
                table = table.eq("id", existing.data[0]["id"])
                if not hasattr(table, 'update'):
                    raise ValueError(f"eq() returned {type(table)}, expected TableProxy")
                table = table.update(update_data)
                if not hasattr(table, 'execute'):
                    raise ValueError(f"update() returned {type(table)}, expected TableProxy")
                resp = table.execute()
            except AttributeError as e:
                error_msg = f"Chaining error: {str(e)}. Table type: {type(table) if 'table' in locals() else 'unknown'}"
                print(error_msg)
                raise ValueError(error_msg) from e
        else:
            # Create new - include all fields
            print(f"Creating new permission with data={perm_data}")
            resp = supabase.table("permissions").insert(perm_data).execute()

        # Check for errors in response
        if getattr(resp, "error", None):
            error_msg = str(resp.error) if hasattr(resp.error, '__str__') else repr(resp.error)
            print(f"Error updating permissions: {error_msg}")
            print(f"Response object: {resp}")
            return False, error_msg

        # For updates, even if data is empty, if there's no error, consider it success
        # (UPDATE queries might return empty if no rows matched, but we check existence first)
        # For inserts, we should have data
        if existing.data and len(existing.data) > 0:
            # This was an update - if no error, consider it success
            # Even if data is empty, the update might have succeeded
            print(f"Update completed. Response data: {resp.data if hasattr(resp, 'data') else 'N/A'}")
            return True, None
        else:
            # This was an insert - we should have data
            if not resp.data or len(resp.data) == 0:
                error_msg = "No data returned from permissions insert - operation may have failed"
                print(f"Warning: {error_msg}")
                return False, error_msg
            print(f"Successfully inserted permissions. Response data: {resp.data}")
            return True, None
    except Exception as e:
        import traceback
        error_msg = f"Exception updating permissions: {str(e)}"
        print(error_msg)
        print(f"Traceback: {traceback.format_exc()}")
        return False, error_msg


def get_role_id_by_name(role_name: str, tenant_id: str) -> Optional[str]:
    """Get role ID by role name."""
    try:
        resp = supabase.table("roles").select("id").eq("role_name", role_name).eq("tenant_id", tenant_id).limit(1).execute()
        if resp.data and len(resp.data) > 0:
            return resp.data[0].get("id")
        return None
    except Exception as e:
        print(f"Error getting role ID by name: {e}")
        return None


def assign_role_to_user(
    user_id: str,
    role_id: str,
    tenant_id: str,
    assigned_by: Optional[str] = None
) -> bool:
    """Assign a role to a user."""
    try:
        # Check if role assignment already exists
        existing = supabase.table("user_roles").select("id").eq("user_id", user_id).eq("role_id", role_id).eq("tenant_id", tenant_id).execute()
        if existing.data and len(existing.data) > 0:
            print(f"Role {role_id} already assigned to user {user_id}")
            return True
        
        user_role_data = {
            "user_id": user_id,
            "role_id": role_id,
            "tenant_id": tenant_id,
            "assigned_by": assigned_by,
        }
        resp = supabase.table("user_roles").insert(user_role_data).execute()
        if getattr(resp, "error", None):
            print(f"Error assigning role: {resp.error}")
            return False
        return True
    except Exception as e:
        print(f"Error assigning role: {e}")
        import traceback
        traceback.print_exc()
        return False


def remove_role_from_user(
    user_id: str,
    role_id: str,
    tenant_id: str
) -> Tuple[bool, str]:
    """Remove a role from a user.
    
    Returns:
        Tuple of (success: bool, error_message: str)
    """
    try:
        # First verify the role assignment exists
        existing = supabase.table("user_roles").select("id").eq(
            "user_id", user_id
        ).eq("role_id", role_id).eq("tenant_id", tenant_id).limit(1).execute()
        
        if not existing.data or len(existing.data) == 0:
            error_msg = f"Role assignment not found for user_id={user_id}, role_id={role_id}, tenant_id={tenant_id}"
            print(error_msg)
            return (False, error_msg)
        
        # Perform the deletion
        resp = supabase.table("user_roles").eq(
            "user_id", user_id
        ).eq("role_id", role_id).eq("tenant_id", tenant_id).delete().execute()
        
        # Check for errors in the response
        resp_error = getattr(resp, "error", None)
        if resp_error:
            error_msg = f"Delete operation failed: {resp_error}"
            print(error_msg)
            return (False, error_msg)
        
        # Check rowcount if available
        rowcount = getattr(resp, "rowcount", None)
        if rowcount is not None and rowcount == 0:
            error_msg = f"No rows were deleted. Role assignment may not exist or filters may not match."
            print(error_msg)
            return (False, error_msg)
        
        # Double-check that the role assignment is gone
        verify = supabase.table("user_roles").select("id").eq(
            "user_id", user_id
        ).eq("role_id", role_id).eq("tenant_id", tenant_id).limit(1).execute()
        
        if verify.data and len(verify.data) > 0:
            error_msg = f"Role assignment still exists after deletion attempt for user_id={user_id}, role_id={role_id}, tenant_id={tenant_id}"
            print(error_msg)
            return (False, error_msg)
        
        return (True, "Role removed successfully")
    except Exception as e:
        error_msg = f"Exception during role removal: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        return (False, error_msg)


def remove_role_from_user_any_tenant(user_id: str, role_id: str) -> Tuple[bool, str]:
    """Remove a role assignment by user_id and role_id only (any tenant). Used for super admin."""
    try:
        existing = supabase.table("user_roles").select("id").eq(
            "user_id", user_id
        ).eq("role_id", role_id).limit(1).execute()
        if not existing.data or len(existing.data) == 0:
            return (False, f"Role assignment not found for user_id={user_id}, role_id={role_id}")
        row_id = existing.data[0].get("id")
        resp = supabase.table("user_roles").delete().eq("id", row_id).execute()
        if getattr(resp, "error", None):
            return (False, str(resp.error))
        return (True, "Role removed successfully")
    except Exception as e:
        return (False, str(e))


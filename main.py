# backend/main.py
# Import config first to ensure environment variables are loaded
import config  # noqa: F401 - Ensures config is loaded before other imports
from config import ENVIRONMENT
from fastapi import FastAPI, HTTPException, Request, Header, Query, File, UploadFile, Path, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
# COMMENTED OUT FOR LOCAL DEVELOPMENT - Using local PostgreSQL instead
# from services.supabase_client import supabase
from services.auth_service import auth_guard
from services.db_service import local_db as supabase  # Use local DB service
from services.db_service import execute_query, pooled_connection
from services.formatters import normalize_control, normalize_control_list, normalize_action
from services.auth_service import authenticate_user, verify_jwt_token, get_user_from_token, verify_password, validate_password_strength
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
    get_role_id_by_name,
)
from services.auth_service import hash_password
from services.qa_bug_snapshot_service import ensure_daily_bug_snapshot_async
from services.user_service import get_user_tenant_id
from services.certification_validator import validate_certification_payload, get_field_options
from utils.error_handler import handle_api_error, log_error, format_error_response, handle_endpoint_error
from services.rbac_service import require_permission
import json
import os
import logging

# Helper function to get user department by email
def get_user_department_by_email(email: str) -> Optional[str]:
    try:
        if not email or not email.strip():
            return None
        resp = supabase.table("users").select("department").eq("email", email.strip().lower()).limit(1).execute()
        rows = resp.data or []
        if rows and isinstance(rows[0], dict):
            return rows[0].get("department")
        return None
    except Exception:
        return None

# Helper function to get user department and department_owner by email
def get_user_department_info_by_email(email: str) -> Dict[str, Optional[str]]:
    try:
        if not email or not email.strip():
            return {"department": None, "department_owner": None}
        resp = supabase.table("users").select("department, department_owner").eq("email", email.strip().lower()).limit(1).execute()
        rows = resp.data or []
        if rows and isinstance(rows[0], dict):
            user_data = rows[0]
            return {
                "department": user_data.get("department"),
                "department_owner": user_data.get("department_owner")
            }
        return {"department": None, "department_owner": None}
    except Exception:
        return {"department": None, "department_owner": None}
import smtplib
from email.message import EmailMessage
from datetime import datetime, timezone
import time
import uuid
from services.request_context import init_request_context, get_request_context, set_request_token, set_request_user



app = FastAPI()
FRONTEND_PKG_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "kaizen_frontend_reactjs", "package.json"))
def _get_version() -> str:
    try:
        with open(FRONTEND_PKG_PATH, "r", encoding="utf-8") as f:
            v = str(json.load(f).get("version", "0.0.0"))
        parts = v.split(".")
        v = f"{parts[0]}.{parts[1]}.0" if len(parts) == 2 else v
        return v if v.startswith("v") else f"v{v}"
    except Exception:
        return "v0.0.0"
APP_VERSION = _get_version()
logging.info(f"Starting Kaizen Backend {APP_VERSION}")

# Allow your frontend origin
# In development, allow all origins. In production, specify exact origins.
_allowed_origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
)

@app.middleware("http")
async def version_header(request, call_next):
    response = await call_next(request)
    response.headers["X-App-Version"] = APP_VERSION
    return response

@app.middleware("http")
async def fix_double_api_path(request: Request, call_next):
    """Normalize /api/api/ to /api/ so malformed client URLs still work (e.g. prod double /api)."""
    path = request.scope.get("path") or ""
    if "/api/api/" not in path:
        return await call_next(request)
    new_path = path
    while "/api/api/" in new_path:
        new_path = new_path.replace("/api/api/", "/api/", 1)
    new_scope = {**request.scope, "path": new_path}
    new_request = Request(new_scope)
    return await call_next(new_request)

@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    t0 = time.perf_counter()
    init_request_context()
    authorization = request.headers.get("authorization")
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    set_request_token(token)

    user = None
    if token:
        user = get_user_from_token(token)
    set_request_user(user)
    request.state.user = user

    response = await call_next(request)

    total_ms = (time.perf_counter() - t0) * 1000.0
    ctx = get_request_context()
    timings = (ctx or {}).get("timings_ms") or {}
    timings["total"] = total_ms
    sql_calls = (ctx or {}).get("sql_calls", 0)
    logging.info(
        f"[perf] {request.method} {request.url.path} total_ms={total_ms:.1f} "
        f"auth_ms={float(timings.get('auth', 0.0)):.1f} "
        f"rbac_ms={float(timings.get('rbac', 0.0)):.1f} "
        f"sql_ms={float(timings.get('sql', 0.0)):.1f} sql_calls={sql_calls}"
    )
    return response

@app.on_event("startup")
async def on_startup():
    from app.rbac.permission_modules import register_app_permission_modules

    register_app_permission_modules()
    print("Kaizen backend started on port 8000")

@app.get("/health")
async def health():
    return {"status": "ok"}


# ----- TEMPORARY: Remove after debugging auth. Hard-verify bcrypt in container. -----
@app.get("/dev/test-bcrypt")
def dev_test_bcrypt():
    """Temporary: verify bcrypt.checkpw(plain, hashed) works. Replace DB_HASH with actual hash from users.password."""
    import bcrypt
    plain = "Netflix@1234"
    # Replace with actual hash from: SELECT password FROM users WHERE email = 'superadmin@cavininfotech.com';
    DB_HASH = os.getenv("DEV_BCRYPT_HASH", "$2b$12$PLACEHOLDER_REPLACE_WITH_ACTUAL_DB_HASH")
    if "PLACEHOLDER" in DB_HASH:
        return {"ok": False, "message": "Set DEV_BCRYPT_HASH env to the actual users.password value for superadmin, then retry."}
    try:
        result = bcrypt.checkpw(plain.encode("utf-8"), DB_HASH.encode("utf-8"))
        return {"ok": result, "bcrypt_checkpw": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}
# ----- END TEMPORARY -----
from app.router_registry import register_routers

register_routers(app)


# app.include_router(controls_router.router)
# app.include_router(tasks_router.router)
# app.include_router(audits_router.router)
# app.include_router(users_router.router)
# app.include_router(roles_router.router)
# app.include_router(dashboard_router.router)
# app.include_router(qa_dashboard_router.router)
# app.include_router(bug_router.router)
# app.include_router(qa_master_router.router)
# app.include_router(convex_router.router)
# app.include_router(projects_router.router)  # Before build_tracker so GET/POST /projects are project CRUD
# app.include_router(build_tracker_router.router)
# app.include_router(buildtracker_dashboard_router.router)
# app.include_router(organizations_router.router)
# app.include_router(risk_register_router.router)
# app.include_router(mrm_router.router)
# app.include_router(incident_router.router)
# app.include_router(certifications_router.router)
# ===========================
# Existing Controls API
# ===========================
    



def _count_table(table_name: str, select_col: str = '"id"'):
    """
    Counts records in a Supabase table.

    - select_col: the column to select/count (use quotes for columns with spaces, e.g. '"Bug ID"').
    - Returns: (count: int, error_msg: Optional[str])
    """
    import logging

    try:
        logging.info(f"📊 Querying table: {table_name} using column {select_col!r}")

        # Try the requested column first
        resp = supabase.table(table_name).select(select_col, count="exact").execute()

        # If selection returned an error, try a sensible fallback
        if hasattr(resp, "error") and resp.error:
            logging.warning(f"⚠️ Column {select_col!r} failed on {table_name}: {resp.error}")

            # Choose fallback column depending on table type
            if "bug" in table_name.lower() or table_name.lower().startswith("bugs"):
                fallback_col = '"Bug ID"'
            else:
                fallback_col = '"id"'

            logging.info(f"Trying fallback column {fallback_col!r} for table {table_name}")
            resp = supabase.table(table_name).select(fallback_col, count="exact").execute()

            if hasattr(resp, "error") and resp.error:
                error_msg = f"Both {select_col!r} and fallback {fallback_col!r} failed: {resp.error}"
                logging.error(error_msg)
                return 0, error_msg

        # Extract exact count if available
        count_attr = getattr(resp, "count", None)
        if count_attr is not None:
            count = int(count_attr)
            logging.info(f"✅ {table_name}: count={count} (from resp.count)")
            return count, None

        # Some supabase clients return a dict
        if isinstance(resp, dict) and resp.get("count") is not None:
            count = int(resp["count"])
            logging.info(f"✅ {table_name}: count={count} (from dict count)")
            return count, None

        # Fallback: try to get data list and count
        data = getattr(resp, "data", None)
        if data is None and isinstance(resp, dict):
            data = resp.get("data", [])
        if data is None:
            data = []

        count = len(data or [])
        logging.info(f"✅ {table_name}: count={count} (from data length fallback)")
        return count, None

    except Exception as e:
        error_msg = f"Exception while counting {table_name}: {str(e)}"
        logging.exception(f"❌ Error counting table {table_name}: {e}")
        return 0, error_msg








# ============================
# 🎯 ACTIONS MODULE ENDPOINTS
# ============================
@app.get("/actions")
@require_permission("actions_retrieve")
async def get_actions(
    control_id: Optional[str] = Query(None),
    tenant_id: str = Query('00000000-0000-0000-0000-000000000001'),
    Authorization: Optional[str] = Header(default=None)
):
    """Get all actions, optionally filtered by control_id. Soft deleted items only visible to Super Admin."""
    endpoint = "/actions"
    try:
        # Get user info to check if superadmin
        auth_data = auth_guard(Authorization)
        user = auth_data.get("user", {})
        user_id = user.get("id") or user.get("user", {}).get("id")
        is_admin = is_superadmin(user_id, tenant_id) if user_id else False
        
        query = supabase.table("actions").select("*").eq("tenant_id", tenant_id)
        if control_id:
            query = query.eq("control_id", control_id)
        
        # Filter out soft deleted items unless user is superadmin
        if not is_admin:
            query = query.eq("is_deleted", False)
        
        resp = query.execute()
        if getattr(resp, "error", None):
            error_str = str(resp.error)
            # If error is about missing column, skip the filter (backward compatibility)
            if "is_deleted" in error_str.lower() and ("column" in error_str.lower() or "does not exist" in error_str.lower()):
                # Retry without is_deleted filter
                query = supabase.table("actions").select("*").eq("tenant_id", tenant_id)
                if control_id:
                    query = query.eq("control_id", control_id)
                resp = query.execute()
            else:
                raise HTTPException(status_code=400, detail=str(resp.error))
        
        actions = resp.data or []
        formatted = [normalize_action(row) for row in actions]
        return {"status": "success", "data": formatted}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "get_actions", return_dict=True, control_id=control_id, tenant_id=tenant_id)


@app.get("/actions/{action_id}")
@require_permission("actions_retrieve")
async def get_action(
    action_id: str,
    tenant_id: str = Query('00000000-0000-0000-0000-000000000001'),
    Authorization: Optional[str] = Header(default=None)
):
    """Get a single action by ID. Soft deleted items only visible to Super Admin."""
    endpoint = f"/actions/{action_id}"
    try:
        # Get user info to check if superadmin
        auth_data = auth_guard(Authorization)
        user = auth_data.get("user", {})
        user_id = user.get("id") or user.get("user", {}).get("id")
        is_admin = is_superadmin(user_id, tenant_id) if user_id else False
        
        query = supabase.table("actions").select("*").eq("id", action_id).eq("tenant_id", tenant_id)
        
        # Filter out soft deleted items unless user is superadmin
        if not is_admin:
            query = query.eq("is_deleted", False)
        
        resp = query.execute()
        if getattr(resp, "error", None):
            error_str = str(resp.error)
            # If error is about missing column, skip the filter (backward compatibility)
            if "is_deleted" in error_str.lower() and ("column" in error_str.lower() or "does not exist" in error_str.lower()):
                query = supabase.table("actions").select("*").eq("id", action_id).eq("tenant_id", tenant_id)
                resp = query.execute()
            else:
                raise HTTPException(status_code=400, detail=str(resp.error))
        
        if not resp.data or len(resp.data) == 0:
            raise HTTPException(status_code=404, detail="Action not found")
        
        action = normalize_action(resp.data[0])
        return {"status": "success", "data": action}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "get_action", return_dict=True, action_id=action_id, tenant_id=tenant_id)


@app.post("/actions")
@require_permission("actions_create")
async def create_action(
    request: Request,
    Authorization: Optional[str] = Header(default=None)
):
    """Create a new action."""
    endpoint = "/actions"
    payload: Dict[str, Any] = {}
    try:
        payload = await request.json()
        tenant_id = payload.get("tenant_id", "00000000-0000-0000-0000-000000000001")
        
        # Add tenant_id and timestamps
        payload["tenant_id"] = tenant_id
        # Generate UUID for action ID if not provided
        if "id" not in payload or not payload["id"]:
            payload["id"] = str(uuid.uuid4())
        if "created_at" not in payload:
            payload["created_at"] = datetime.now(timezone.utc).isoformat()
        if "updated_at" not in payload:
            payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        # Ensure is_deleted is False for new actions
        payload["is_deleted"] = False
        
        # Ensure required fields
        if not payload.get("action_name"):
            raise HTTPException(status_code=400, detail="action_name is required")
        
        resp = supabase.table("actions").insert(payload).execute()
        if getattr(resp, "error", None):
            raise HTTPException(status_code=400, detail=str(resp.error))
        
        created_action = resp.data[0] if resp.data else None
        if not created_action:
            raise HTTPException(status_code=400, detail="Failed to create action")
        
        action = normalize_action(created_action)
        return {"status": "success", "data": action}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "create_action", return_dict=True, tenant_id=payload.get("tenant_id"))


@app.put("/actions/{action_id}")
@require_permission("actions_update")
async def update_action(
    action_id: str,
    request: Request,
    tenant_id: str = Query('00000000-0000-0000-0000-000000000001'),
    Authorization: Optional[str] = Header(default=None)
):
    """Update an existing action. Soft deleted actions cannot be updated (except by Super Admin)."""
    endpoint = f"/actions/{action_id}"
    payload: Dict[str, Any] = {}
    try:
        payload = await request.json()
        # Use tenant_id from query param (for permission check) or from payload
        tenant_id = payload.get("tenant_id", tenant_id)
        
        # Get user info to check if superadmin
        auth_data = auth_guard(Authorization)
        user = auth_data.get("user", {})
        user_id = user.get("id") or user.get("user", {}).get("id")
        is_admin = is_superadmin(user_id, tenant_id) if user_id else False
        
        # Verify action exists and belongs to tenant
        existing = supabase.table("actions").select("id, is_deleted").eq("id", action_id).eq("tenant_id", tenant_id).limit(1).execute()
        if not existing.data or len(existing.data) == 0:
            raise HTTPException(status_code=404, detail="Action not found")
        
        # Prevent updating soft deleted actions (unless superadmin)
        if existing.data[0].get("is_deleted") and not is_admin:
            raise HTTPException(status_code=404, detail="Action not found")
        
        # Update updated_at
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        # Don't allow changing tenant_id or id
        payload.pop("tenant_id", None)
        payload.pop("id", None)
        
        resp = supabase.table("actions").eq("id", action_id).eq("tenant_id", tenant_id).update(payload).execute()
        if getattr(resp, "error", None):
            raise HTTPException(status_code=400, detail=str(resp.error))
        
        action = normalize_action(resp.data[0]) if resp.data else None
        return {"status": "success", "data": action}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "update_action", return_dict=True, action_id=action_id, tenant_id=payload.get("tenant_id"))


@app.delete("/actions/{action_id}")
@require_permission("actions_delete")
async def delete_action(
    action_id: str,
    tenant_id: str = Query('00000000-0000-0000-0000-000000000001'),
    Authorization: Optional[str] = Header(default=None)
):
    """Soft delete an action (sets is_deleted=True). Only Super Admin can see soft deleted items."""
    endpoint = f"/actions/{action_id}"
    try:
        # Get user info
        auth_data = auth_guard(Authorization)
        user = auth_data.get("user", {})
        user_id = user.get("id") or user.get("user", {}).get("id")
        
        # Verify action exists and belongs to tenant (including soft deleted)
        existing = supabase.table("actions").select("id, is_deleted").eq("id", action_id).eq("tenant_id", tenant_id).limit(1).execute()
        if not existing.data or len(existing.data) == 0:
            raise HTTPException(status_code=404, detail="Action not found")
        
        # Check if already soft deleted
        if existing.data[0].get("is_deleted"):
            raise HTTPException(status_code=400, detail="Action is already deleted")
        
        # Soft delete: set is_deleted=True, deleted_at=now, deleted_by=user_id
        update_data = {
            "is_deleted": True,
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "deleted_by": user_id,
        }
        
        resp = supabase.table("actions").eq("id", action_id).eq("tenant_id", tenant_id).update(update_data).execute()
        if getattr(resp, "error", None):
            raise HTTPException(status_code=400, detail=str(resp.error))
        
        return {"status": "success", "data": {"success": True, "message": "Action deleted successfully"}}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "delete_action", return_dict=True, action_id=action_id, tenant_id=tenant_id)


# ============================
# 🏆 CERTIFICATIONS MODULE ENDPOINTS
# ============================
@app.get("/certifications")
@require_permission("certifications_retrieve")
async def get_certifications(
    tenant_id: str = Query('00000000-0000-0000-0000-000000000001'),
    Authorization: Optional[str] = Header(default=None)
):
    """Get all unique certifications from security_controls table. Soft deleted items only visible to Super Admin."""
    endpoint = "/certifications"
    try:
        # Get user info to check if superadmin
        auth_data = auth_guard(Authorization)
        user = auth_data.get("user", {})
        user_id = auth_data.get("user_id") or user.get("user_id")
        is_admin = is_superadmin(user_id, tenant_id) if user_id else False
        
        # Get unique certification values from security_controls
        query = (
            supabase.table("security_controls")
            .select("certification")
            .eq("tenant_id", tenant_id)
        )
        
        # Try to filter out soft deleted items unless user is superadmin
        resp = None
        if not is_admin:
            try:
                query_with_filter = query.eq("is_deleted", False)
                resp = query_with_filter.execute()
                if getattr(resp, "error", None):
                    error_str = str(resp.error).lower()
                    error_dict = resp.error if isinstance(resp.error, dict) else {}
                    error_type = error_dict.get("type", "").lower() if isinstance(error_dict, dict) else ""
                    
                    is_deleted_error = (
                        "is_deleted" in error_str and (
                            "column" in error_str or 
                            "does not exist" in error_str or 
                            "undefinedcolumn" in error_str or
                            error_type == "undefinedcolumn"
                        )
                    )
                    
                    if is_deleted_error:
                        resp = None
                    else:
                        error_detail = str(resp.error) if isinstance(resp.error, (str, dict)) else repr(resp.error)
                        raise HTTPException(status_code=400, detail=error_detail)
            except HTTPException:
                raise
            except Exception as e:
                error_str = str(e).lower()
                is_deleted_error = (
                    "is_deleted" in error_str and (
                        "column" in error_str or 
                        "does not exist" in error_str or 
                        "undefinedcolumn" in error_str or
                        "undefined column" in error_str
                    )
                )
                if is_deleted_error:
                    resp = None
                else:
                    raise
        
        # Execute query without is_deleted filter if previous attempt failed or wasn't tried
        if resp is None:
            query = (
                supabase.table("security_controls")
                .select("certification")
                .eq("tenant_id", tenant_id)
            )
            resp = query.execute()
            if getattr(resp, "error", None):
                error_detail = str(resp.error) if isinstance(resp.error, (str, dict)) else repr(resp.error)
                raise HTTPException(status_code=400, detail=error_detail)
        
        # Extract unique certification values
        certifications = set()
        if resp.data:
            for row in resp.data:
                cert_value = row.get("certification")
                if cert_value and str(cert_value).strip():
                    certifications.add(str(cert_value).strip())
        
        # Return as sorted list
        return {"data": sorted(list(certifications)), "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "get_certifications", return_dict=True, tenant_id=tenant_id)


@app.get("/certifications/from-controls")
@require_permission("security_controls_retrieve")
async def get_certifications_from_controls(
    tenant_id: str = Query('00000000-0000-0000-0000-000000000001'),
    Authorization: Optional[str] = Header(default=None)
):
    """Get unique certification values from security_controls table.
    
    This endpoint returns all unique certification values that exist in security_controls,
    which may include certifications (like CADP) that don't exist in the certifications table.
    """
    endpoint = "/certifications/from-controls"
    try:
        auth_data = auth_guard(Authorization)
        user = auth_data.get("user", {})
        user_id = auth_data.get("user_id") or user.get("user_id")
        is_admin = is_superadmin(user_id, tenant_id) if user_id else False
        
        # Get unique certification values from security_controls
        # Note: security_controls table may not have is_deleted column, so we handle that gracefully
        query = (
            supabase.table("security_controls")
            .select("certification")
            .eq("tenant_id", tenant_id)
        )
        
        # Try to filter out soft deleted items unless user is superadmin
        # If is_deleted column doesn't exist, we'll catch the error and retry without the filter
        resp = None
        if not is_admin:
            try:
                query_with_filter = query.eq("is_deleted", False)
                resp = query_with_filter.execute()
                # Check if error is about missing is_deleted column
                if getattr(resp, "error", None):
                    error_str = str(resp.error).lower()
                    error_dict = resp.error if isinstance(resp.error, dict) else {}
                    error_type = error_dict.get("type", "").lower() if isinstance(error_dict, dict) else ""
                    
                    # Check if error is about missing is_deleted column (backward compatibility)
                    is_deleted_error = (
                        "is_deleted" in error_str and (
                            "column" in error_str or 
                            "does not exist" in error_str or 
                            "undefinedcolumn" in error_str or
                            error_type == "undefinedcolumn"
                        )
                    )
                    
                    if is_deleted_error:
                        # Column doesn't exist, retry without filter
                        resp = None
                    else:
                        error_detail = str(resp.error) if isinstance(resp.error, (str, dict)) else repr(resp.error)
                        raise HTTPException(status_code=400, detail=error_detail)
            except HTTPException:
                raise
            except Exception as e:
                # Catch database exceptions about missing columns
                error_str = str(e).lower()
                error_message = str(e)
                
                # Check if this is a database error about missing is_deleted column
                is_deleted_error = (
                    "is_deleted" in error_str and (
                        "column" in error_str or 
                        "does not exist" in error_str or 
                        "undefinedcolumn" in error_str or
                        "undefined column" in error_str
                    )
                )
                
                if is_deleted_error:
                    # Column doesn't exist, we'll retry without filter below
                    resp = None
                    print(f"[get_certifications_from_controls] is_deleted column not found, querying without filter")
                else:
                    # Re-raise if it's a different error
                    raise
        
        # Execute query without is_deleted filter if previous attempt failed or wasn't tried
        if resp is None:
            # Rebuild query without is_deleted filter
            query = (
                supabase.table("security_controls")
                .select("certification")
                .eq("tenant_id", tenant_id)
            )
            resp = query.execute()
            if getattr(resp, "error", None):
                error_detail = str(resp.error) if isinstance(resp.error, (str, dict)) else repr(resp.error)
                raise HTTPException(status_code=400, detail=error_detail)
        
        # Extract unique certification values
        certifications = set()
        if resp.data:
            for row in resp.data:
                cert_value = row.get("certification")
                if cert_value and str(cert_value).strip():
                    certifications.add(str(cert_value).strip())
        
        # Return as sorted list
        return {"data": sorted(list(certifications)), "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "get_certifications_from_controls", return_dict=True, tenant_id=tenant_id)


@app.get("/certifications/dropdowns")
async def get_certification_dropdowns():
    """Get all dropdown options for certifications."""
    try:
        from services.certification_validator import get_dropdown_values
        return {"data": get_dropdown_values(), "error": None}
    except Exception as e:
        return {"data": {}, "error": str(e)}


@app.get("/certifications/dropdowns/{field_name}")
async def get_certification_field_options(field_name: str):
    """Get dropdown options for a specific certification field."""
    try:
        from services.certification_validator import get_field_options
        options = get_field_options(field_name)
        return {"data": options, "error": None}
    except Exception as e:
        return {"data": [], "error": str(e)}


@app.get("/certifications/{certification_name}")
@require_permission("certifications_retrieve")
async def get_certification(
    certification_name: str,
    tenant_id: str = Query('00000000-0000-0000-0000-000000000001'),
    Authorization: Optional[str] = Header(default=None)
):
    """Get security controls for a specific certification name from security_controls table. Soft deleted items only visible to Super Admin."""
    endpoint = f"/certifications/{certification_name}"
    try:
        # Get user info to check if superadmin
        auth_data = auth_guard(Authorization)
        user = auth_data.get("user", {})
        user_id = auth_data.get("user_id") or user.get("user_id")
        is_admin = is_superadmin(user_id, tenant_id) if user_id else False
        
        # Query security_controls table filtering by certification column
        query = (
            supabase.table("security_controls")
            .select("*")
            .eq("tenant_id", tenant_id)
            .ilike("certification", certification_name.strip())
        )
        
        # Try to filter out soft deleted items unless user is superadmin
        resp = None
        if not is_admin:
            try:
                query_with_filter = query.eq("is_deleted", False)
                resp = query_with_filter.execute()
                if getattr(resp, "error", None):
                    error_str = str(resp.error).lower()
                    error_dict = resp.error if isinstance(resp.error, dict) else {}
                    error_type = error_dict.get("type", "").lower() if isinstance(error_dict, dict) else ""
                    
                    is_deleted_error = (
                        "is_deleted" in error_str and (
                            "column" in error_str or 
                            "does not exist" in error_str or 
                            "undefinedcolumn" in error_str or
                            error_type == "undefinedcolumn"
                        )
                    )
                    
                    if is_deleted_error:
                        resp = None
                    else:
                        error_detail = str(resp.error) if isinstance(resp.error, (str, dict)) else repr(resp.error)
                        raise HTTPException(status_code=400, detail=error_detail)
            except HTTPException:
                raise
            except Exception as e:
                error_str = str(e).lower()
                is_deleted_error = (
                    "is_deleted" in error_str and (
                        "column" in error_str or 
                        "does not exist" in error_str or 
                        "undefinedcolumn" in error_str or
                        "undefined column" in error_str
                    )
                )
                if is_deleted_error:
                    resp = None
                else:
                    raise
        
        # Execute query without is_deleted filter if previous attempt failed or wasn't tried
        if resp is None:
            query = (
                supabase.table("security_controls")
                .select("*")
                .eq("tenant_id", tenant_id)
                .ilike("certification", certification_name.strip())
            )
            resp = query.execute()
            if getattr(resp, "error", None):
                error_detail = str(resp.error) if isinstance(resp.error, (str, dict)) else repr(resp.error)
                raise HTTPException(status_code=400, detail=error_detail)
        
        if not resp.data or len(resp.data) == 0:
            raise HTTPException(status_code=404, detail=f"No security controls found for certification: {certification_name}")
        
        return {"data": resp.data, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "get_certification", return_dict=True, certification_id=certification_name, tenant_id=tenant_id)


@app.post("/certifications")
@require_permission("certifications_create")
async def create_certification(
    request: Request,
    Authorization: Optional[str] = Header(default=None)
):
    """Create certification - Not implemented. Certifications are stored in security_controls table."""
    endpoint = "/certifications"
    raise HTTPException(
        status_code=501, 
        detail="Create operation not supported. Certifications are read-only values from security_controls table."
    )


@app.put("/certifications/{certification_id}")
@require_permission("certifications_update")
async def update_certification(
    certification_id: str,
    request: Request,
    tenant_id: str = Query('00000000-0000-0000-0000-000000000001'),
    Authorization: Optional[str] = Header(default=None)
):
    """Update certification - Not implemented. Certifications are stored in security_controls table."""
    endpoint = f"/certifications/{certification_id}"
    raise HTTPException(
        status_code=501, 
        detail="Update operation not supported. Certifications are read-only values from security_controls table."
    )


@app.delete("/certifications/{certification_id}")
@require_permission("certifications_delete")
async def delete_certification(
    certification_id: str,
    tenant_id: str = Query('00000000-0000-0000-0000-000000000001'),
    Authorization: Optional[str] = Header(default=None)
):
    """Delete certification - Not implemented. Certifications are stored in security_controls table."""
    endpoint = f"/certifications/{certification_id}"
    raise HTTPException(
        status_code=501, 
        detail="Delete operation not supported. Certifications are read-only values from security_controls table."
    )
async def get_certification_field_options_internal(field_name: str):
    try:
        from services.certification_validator import get_field_options
        options = get_field_options(field_name)
        return {"data": options, "error": None}
    except Exception as e:
        return {"data": [], "error": str(e)}


# ============================
# 📊 DASHBOARD ENDPOINTS
# ============================







 


 


 


# ============================
# 🔐 AUTHENTICATION ENDPOINTS
# ============================

class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/api/auth/login")
async def login(payload: LoginRequest):
    """Login with email and password. Returns JWT token.
    
    Blocks inactive users from logging in. Email is normalized (strip + lower) before lookup.
    """
    endpoint = "/api/auth/login"
    try:
        email = (payload.email or "").strip().lower()
        if not email:
            raise HTTPException(status_code=400, detail="Email is required")
        result = authenticate_user(email, payload.password)
        
        # Check if result indicates inactive user
        if result and result.get("error") == "inactive":
            raise HTTPException(
                status_code=403,
                detail=result.get("message", "Your account is inactive. Please contact your administrator.")
            )
        
        # Check if user has no password set
        if result and result.get("error") == "no_password":
            raise HTTPException(
                status_code=400,
                detail=result.get("message", "No password set for this account. Please use SSO login or contact your administrator.")
            )
        
        # Check if authentication failed (user not found or wrong password)
        if not result:
            raise HTTPException(status_code=401, detail="Invalid email or password")

        await ensure_daily_bug_snapshot_async()
        
        return {
            "data": {
                "token": result["token"],
                "user": {
                    "id": result["user_id"],
                    "email": result["email"],
                    "full_name": result["full_name"],
                    "tenant_id": result["tenant_id"],
                },
                "requires_password_change": result.get("requires_password_change", False),
            },
            "error": None
        }
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "login", return_dict=True, email=getattr(payload, "email", ""))


@app.post("/api/auth/logout")
async def logout(Authorization: Optional[str] = Header(default=None)):
    """Logout (client-side token removal)."""
    # JWT tokens are stateless, so logout is handled client-side
    return {"data": {"message": "Logged out successfully"}, "error": None}


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@app.post("/api/auth/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    Authorization: Optional[str] = Header(default=None)
):
    """Allow authenticated users to change their own password.
    
    Validates current password and updates to new password.
    Requires valid JWT token in Authorization header.
    """
    endpoint = "/api/auth/change-password"
    try:
        # Get user from token
        if not Authorization or not Authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid authorization token")
        
        token = Authorization.replace("Bearer ", "")
        user_info = get_user_from_token(token)
        
        if not user_info:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        user_id = user_info["user_id"]
        
        # Validate new password strength
        is_valid, error_msg = validate_password_strength(payload.new_password)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
        
        # Verify current password and update to new password
        with pooled_connection() as conn:
            cur = conn.cursor()
            try:
                cur.execute("SELECT password FROM users WHERE id = %s", (user_id,))
                row = cur.fetchone()

                if not row:
                    raise HTTPException(status_code=404, detail="User not found")

                current_hashed_password = row[0]

                if not verify_password(payload.current_password, current_hashed_password):
                    raise HTTPException(status_code=400, detail="Current password is incorrect")

                if verify_password(payload.new_password, current_hashed_password):
                    raise HTTPException(
                        status_code=400, detail="New password must be different from current password"
                    )

                new_hashed_password = hash_password(payload.new_password)
                cur.execute(
                    "UPDATE users SET password = %s, updated_at = NOW() WHERE id = %s",
                    (new_hashed_password, user_id),
                )
                conn.commit()
            finally:
                cur.close()
        
        return {
            "data": {
                "message": "Password changed successfully",
                "password_changed": True
            },
            "error": None
        }
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "change_password", return_dict=True)


@app.get("/api/auth/check-password-change")
async def check_password_change(
    Authorization: Optional[str] = Header(default=None)
):
    """Check if the authenticated user needs to change their password.
    
    Returns requires_password_change flag.
    """
    endpoint = "/api/auth/check-password-change"
    try:
        # Get user from token
        if not Authorization or not Authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid authorization token")
        
        token = Authorization.replace("Bearer ", "")
        user_info = get_user_from_token(token)
        
        if not user_info:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        user_id = user_info["user_id"]
        
        # Check if password is default or first login
        with pooled_connection() as conn:
            cur = conn.cursor()
            try:
                cur.execute(
                    "SELECT password, first_login, last_login FROM users WHERE id = %s",
                    (user_id,),
                )
                row = cur.fetchone()
            finally:
                cur.close()

        if not row:
            raise HTTPException(status_code=404, detail="User not found")

        hashed_password, first_login, last_login = row
        
        # Require password change only when password is still the default "pass"
        is_default_password = verify_password("pass", hashed_password)
        is_first_time = is_default_password
        
        return {
            "data": {
                "requires_password_change": is_first_time
            },
            "error": None
        }
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "check_password_change", return_dict=True)


class SSOLoginRequest(BaseModel):
    access_token: str


@app.post("/api/auth/sso/login")
async def sso_login(payload: SSOLoginRequest):
    """Login with Microsoft Entra ID SSO (OIDC Authorization Code + PKCE on the client).

    Validates the Microsoft ID token (JWKS, tenant, audience, issuer, expiry),
    checks allowed email domains, and authenticates existing Master Minds users only.
    """
    endpoint = "/api/auth/sso/login"
    try:
        from services.sso_service import authenticate_sso_user

        result = authenticate_sso_user(payload.access_token)

        if result and result.get("error"):
            error_type = result.get("error")
            message = result.get("message", "Microsoft sign-in failed.")
            token_errors = {
                "missing_token",
                "invalid_token",
                "invalid_signature",
                "invalid_audience",
                "invalid_issuer",
                "invalid_tenant",
                "token_expired",
                "missing_email",
                "missing_subject",
            }
            if error_type in token_errors:
                raise HTTPException(status_code=401, detail=message)
            if error_type == "sso_not_configured":
                raise HTTPException(status_code=503, detail=message)
            if error_type in ("inactive", "domain_not_allowed", "user_not_found"):
                raise HTTPException(status_code=403, detail=message)
            if error_type == "auth_failed":
                raise HTTPException(status_code=500, detail=message)
            raise HTTPException(status_code=401, detail=message)

        if not result:
            raise HTTPException(status_code=401, detail="Invalid SSO token or authentication failed")

        await ensure_daily_bug_snapshot_async()
        
        return {
            "data": {
                "token": result["token"],
                "user": {
                    "id": result["user_id"],
                    "email": result["email"],
                    "full_name": result["full_name"],
                    "tenant_id": result["tenant_id"],
                }
            },
            "error": None
        }
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "sso_login", return_dict=True)


class DevBootstrapUserRequest(BaseModel):
    email: str
    password: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[str] = "Contributor"


@app.post("/api/dev/bootstrap-user")
async def dev_bootstrap_user(payload: DevBootstrapUserRequest):
    if getattr(config, "ENVIRONMENT", "development") != "development":
        raise HTTPException(status_code=403, detail="Not allowed")
    email = (payload.email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    existing = supabase.table("users").select("id").eq("email", email).execute()
    if getattr(existing, "data", None):
        return {"status": "exists", "message": "User already exists"}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    hashed_password = hash_password(payload.password or "pass")
    to_insert = {
        "id": str(uuid.uuid4()),
        "email": email,
        "full_name": (payload.full_name or email.split("@")[0]),
        "role": payload.role or "Contributor",
        "password": hashed_password,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
        "sso_provider": "manual",
        "sso_user_id": None,
        "login_count": 0,
        "tenant_id": "00000000-0000-0000-0000-000000000001",
    }
    resp = supabase.table("users").insert(to_insert, returning="representation").execute()
    if getattr(resp, "error", None):
        raise HTTPException(status_code=500, detail=str(resp.error))
    return {"status": "success", "data": (resp.data or [None])[0]}

# --- Admin endpoint to update all user passwords ---
@app.post("/api/admin/update-all-passwords")
@require_permission("users_update")  # Requires user update permission
async def update_all_passwords(
    force: bool = Query(False, description="Force update even if password is already bcrypted"),
    Authorization: Optional[str] = Header(default=None)
):
    """
    Admin endpoint to update all users in the database with bcrypted password "pass".
    This ensures all users have a password set for login.
    """
    endpoint = "/api/admin/update-all-passwords"
    try:
        from scripts.update_user_passwords import update_all_user_passwords
        
        result = update_all_user_passwords(force=force)
        
        if result["success"]:
            return {
                "data": {
                    "updated": result["updated"],
                    "skipped": result["skipped"],
                    "total": result["total"],
                    "message": f"Successfully updated {result['updated']} user passwords"
                },
                "error": None
            }
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to update passwords"))
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "update_all_passwords", return_dict=True)

# --- Admin endpoint to backfill user roles ---
@app.post("/api/admin/backfill-user-roles")
@require_permission("users_update")  # Requires user update permission
async def backfill_user_roles_endpoint(
    force: bool = Query(False, description="Force update even if role is already assigned"),
    Authorization: Optional[str] = Header(default=None)
):
    """
    Admin endpoint to backfill user_roles table for all existing users.
    Maps the 'role' field in users table to actual role assignments.
    """
    endpoint = "/api/admin/backfill-user-roles"
    try:
        from scripts.backfill_user_roles import backfill_user_roles
        
        result = backfill_user_roles(force=force)
        
        if result["success"]:
            return {
                "data": {
                    "updated": result["updated"],
                    "skipped": result["skipped"],
                    "errors": result.get("errors", 0),
                    "total": result["total"],
                    "message": f"Successfully processed {result['updated']} user role assignments"
                },
                "error": None
            }
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to backfill user roles"))
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "backfill_user_roles", return_dict=True)

# --- debug endpoint to inspect raw supabase response quickly ---
@app.get("/raw-probe")
def raw_probe() -> Dict[str, Any]:
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase client not configured")

    try:
        try:
            r = supabase.table("Bugs_file").select("*").limit(5).execute()
        except:
            r = supabase.from_("Bugs_file").select("*").limit(5).execute()

        if isinstance(r, dict):
            return {"repr": repr(r), "keys": list(r.keys()), "data_len": len(r.get("data") or []), "data_sample": (r.get("data") or [])[:3], "error": r.get("error")}
        else:
            return {"repr": repr(r), "data_len": len(getattr(r, "data", []) or []), "data_sample": getattr(r, "data", None)[:3] if getattr(r, "data", None) else [], "error": getattr(r, "error", None)}
    except Exception:
        logging.exception("raw-probe failed")
        raise HTTPException(status_code=500, detail="raw-probe failed; see server logs")

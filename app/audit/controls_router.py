from fastapi import APIRouter, HTTPException, Request, Header, Query
from typing import Optional, Dict, Any, List, cast
import json
import uuid
from datetime import datetime, timezone
from services.db_service import local_db as supabase, execute_query, table_exists
from services.formatters import normalize_control, normalize_control_list
from services.rbac_service import is_superadmin, get_user_roles, check_permission
from services.rbac_service import require_permission
from utils.error_handler import handle_api_error, handle_endpoint_error
from services.auth_service import get_user_from_token, auth_guard

router = APIRouter()

# Ensure new columns exist
# Call init after function definitions
def ensure_columns_init():
    if not table_exists("security_controls"):
        return
    try:
        ensure_column_exists("security_controls", "code", "TEXT")
        ensure_column_exists("security_controls", "summary", "TEXT")
        ensure_column_exists("security_controls", "description", "TEXT")
        ensure_column_exists("security_controls", "guidance", "TEXT")
        ensure_column_exists("security_controls", "organization", "TEXT")
        ensure_column_exists("security_controls", "organization_id", "UUID")
        ensure_column_exists("security_controls", "review_date", "DATE")
    except Exception as e:
        print(f"Warning: Failed to ensure columns exist: {e}")


def get_existing_columns(table_name: str) -> List[str]:
    try:
        rows = execute_query(
            "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s",
            (table_name,),
            fetch_all=True
        ) or []
        return [r.get("column_name") for r in rows if isinstance(r, dict)]
    except Exception:
        return []

def check_deferred_status_permission(user_id: str, tenant_id: str, status: Optional[str], current_status: Optional[str] = None):
    if not status or str(status).strip().lower() != "deferred":
        return
    
    # If status is not changing, skip check
    if current_status and str(current_status).strip().lower() == "deferred":
        return
    
    # Check permissions
    if is_superadmin(user_id, tenant_id):
        return
        
    allowed_roles = {"internal auditor", "external auditor", "admin"}
    user_roles = get_user_roles(user_id, tenant_id)
    
    has_permission = False
    for ur in user_roles:
        role_data = ur.get("roles")
        if isinstance(role_data, dict):
            role_name = str(role_data.get("role_name", "")).lower()
            if role_name in allowed_roles:
                has_permission = True
                break
    
    if not has_permission:
        raise HTTPException(status_code=403, detail="You do not have permission to set status to Deferred")

def ensure_column_exists(table_name: str, column_name: str, column_type_sql: str) -> None:
    try:
        if not table_exists(table_name):
            return
        cols = get_existing_columns(table_name)
        if column_name not in cols:
            execute_query(
                f'ALTER TABLE "{table_name}" ADD COLUMN IF NOT EXISTS "{column_name}" {column_type_sql}',
                fetch_all=False,
            )
    except Exception:
        pass

# Call ensure columns init
ensure_columns_init()

# @router.get("/controls")
# async def get_controls():
#     endpoint = "/controls"
#     try:
#         resp = supabase.table("controls").select("*").execute()
#         data = resp.data or []
#         formatted = [normalize_control(row) for row in data if isinstance(row, dict)]
#         return {"status": "success", "data": formatted}
#     except HTTPException:
#         raise
#     except Exception as e:
#         error_response, status_code = handle_api_error(
#             e,
#             endpoint,
#             context={"operation": "get_controls", "table": "controls"},
#             include_traceback=False,
#             user_message="Failed to fetch controls"
#         )
#         er = cast(Dict[str, Any], error_response)
#         raise HTTPException(status_code=int(status_code), detail=str(er.get("error")))

@router.get("/security-controls/certifications/unique")
@require_permission("security_controls_retrieve")
async def get_unique_certifications(Authorization: Optional[str] = Header(default=None)):
    try:
        auth_data = auth_guard(Authorization)
        tenant_id = auth_data.get("tenant_id")
        col_check_sql = """
            SELECT 1 
            FROM information_schema.columns 
            WHERE table_schema = 'public' 
              AND table_name = 'security_controls' 
              AND column_name = 'is_deleted'
            LIMIT 1
        """
        col_exists_row = execute_query(col_check_sql, (), fetch_one=True)
        has_is_deleted = bool(col_exists_row)
        
        if has_is_deleted:
            query = (
                "SELECT DISTINCT TRIM(certification) AS certification "
                "FROM security_controls "
                "WHERE (tenant_id = %s OR tenant_id IS NULL) "
                "AND certification IS NOT NULL "
                "AND TRIM(certification) <> '' "
                "AND (is_deleted IS NULL OR is_deleted = FALSE OR CAST(is_deleted AS TEXT) ILIKE 'n') "
                "ORDER BY LOWER(TRIM(certification))"
            )
            rows = execute_query(query, (tenant_id,), fetch_all=True)
        else:
            query = (
                "SELECT DISTINCT TRIM(certification) AS certification "
                "FROM security_controls "
                "WHERE (tenant_id = %s OR tenant_id IS NULL) "
                "AND certification IS NOT NULL "
                "AND TRIM(certification) <> '' "
                "ORDER BY LOWER(TRIM(certification))"
            )
            rows = execute_query(query, (tenant_id,), fetch_all=True)
        
        if not rows:
            return {"status": "success", "data": []}
        seen = set()
        certs = []
        for r in rows:
            cert = r.get('certification')
            if not cert:
                continue
            key = cert.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            certs.append(cert.strip())
        return {"status": "success", "data": certs}
    except Exception as e:
        print(f"Error fetching unique certifications: {e}")
        return {"status": "error", "data": [], "error": str(e)}

@router.get("/security-controls")
@require_permission("security_controls_retrieve")
async def get_security_controls(
    tenant_id: Optional[str] = Query(None), # Kept for backward compatibility but ignored in favor of token
    certification: Optional[str] = Query(None),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = "/security-controls"
    try:
        auth_data = auth_guard(Authorization)
        user = auth_data.get("user", {}) or {}
        nested_user = user.get("user") or {}
        user_id = user.get("id") or nested_user.get("id")
        
        # Enforce tenant isolation based on the logged-in user's token
        # We ignore the query param tenant_id to ensure users can only see their own tenant's data
        effective_tenant_id = auth_data.get("tenant_id")
        
        is_admin = is_superadmin(user_id, effective_tenant_id) if user_id else False
        if not certification:
            return {"data": [], "error": None}
        cert_trimmed = certification.strip()
        col_check_sql = """
            SELECT 1 
            FROM information_schema.columns 
            WHERE table_schema = 'public' 
              AND table_name = 'security_controls' 
              AND column_name = 'is_deleted'
            LIMIT 1
        """
        col_exists_row = execute_query(col_check_sql, (), fetch_one=True)
        has_is_deleted = bool(col_exists_row)
        
        if has_is_deleted and not is_admin:
            sql = (
                "SELECT * FROM security_controls "
                "WHERE (tenant_id = %s OR tenant_id IS NULL) "
                "AND TRIM(certification) ILIKE %s "
                "AND (is_deleted IS NULL OR is_deleted = FALSE OR CAST(is_deleted AS TEXT) ILIKE 'n')"
            )
            params = (effective_tenant_id, cert_trimmed)
        else:
            sql = (
                "SELECT * FROM security_controls "
                "WHERE (tenant_id = %s OR tenant_id IS NULL) "
                "AND TRIM(certification) ILIKE %s"
            )
            params = (effective_tenant_id, cert_trimmed)
        
        data = execute_query(sql, params, fetch_all=True) or []
        data = [row for row in data if isinstance(row, dict)]
        owner_emails = set()
        for row in data:
            owner = row.get("owner")
            if owner and owner.strip():
                owner_emails.add(owner.strip().lower())
        department_map = {}
        if owner_emails:
            try:
                users_resp = supabase.table("users").select("email, department").execute()
                if users_resp.data:
                    for user_row in users_resp.data:
                        email = user_row.get("email")
                        if email:
                            email_lower = email.strip().lower()
                            if email_lower in owner_emails:
                                department_map[email_lower] = user_row.get("department")
            except Exception:
                pass
        formatted = []
        for row in data:
            normalized = normalize_control_list(row)
            if not normalized.get("department") and normalized.get("owner"):
                owner_email = normalized.get("owner")
                if owner_email:
                    owner_department = department_map.get(owner_email.strip().lower())
                    if owner_department:
                        normalized["department"] = owner_department
            formatted.append(normalized)
        return {"data": formatted, "error": None}
    except Exception as e:
        error_response, status_code = handle_api_error(
            e,
            endpoint,
            context={"operation": "get_security_controls", "table": "security_controls"},
            include_traceback=False,
            user_message="Failed to fetch security controls"
        )
        return cast(Dict[str, Any], error_response)

@router.get("/security-controls/{record_id}")
@require_permission("security_controls_retrieve")
async def get_security_control_by_id(
    record_id: str,
    tenant_id: Optional[str] = Query(None),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = f"/security-controls/{record_id}"
    try:
        auth_data = auth_guard(Authorization)
        user = auth_data.get("user", {}) or {}
        nested_user = user.get("user") or {}
        user_id = user.get("id") or nested_user.get("id")
        
        # Enforce tenant isolation based on the logged-in user's token
        effective_tenant_id = auth_data.get("tenant_id")

        is_admin = is_superadmin(user_id, effective_tenant_id) if user_id else False
        
        # Check if user is Super Admin of the System Tenant (default tenant)
        # System Admins can access records from any tenant
        is_system_admin = (effective_tenant_id == '00000000-0000-0000-0000-000000000001' and is_admin)
        
        # Primary query: Try to find by ID first
        query = supabase.table("security_controls").select("*")
        # print(f"seccon Query 1: {query}")
        
        query = query.eq("id", record_id)
        # print(f"seccon Query 2: {query}")
            
        # Only enforce tenant_id if not System Super Admin
        if not is_system_admin:
            query = query.eq("tenant_id", effective_tenant_id)
            
        # print(f"seccon Query 3: {query}")
        
        if not is_admin:
            query = query.eq("is_deleted", False)
            
        resp = query.limit(1).execute()

        # Handle potential schema errors (is_deleted column missing)
        if getattr(resp, "error", None):
            error_str = str(resp.error).lower()
            if "is_deleted" in error_str and ("column" in error_str or "does not exist" in error_str or "undefinedcolumn" in error_str):
                # Retry without is_deleted check
                query = supabase.table("security_controls").select("*")
                query = query.eq("id", record_id)
                
                if not is_system_admin:
                    query = query.eq("tenant_id", effective_tenant_id)
                    
                resp = query.limit(1).execute()
                
            if getattr(resp, "error", None):
                raise HTTPException(status_code=400, detail=str(resp.error))

        rows = resp.data or []
        
        # If not found by ID, try finding by Code
        if not rows:
            query = supabase.table("security_controls").select("*")
            query = query.eq("code", record_id)
            
            if not is_system_admin:
                query = query.eq("tenant_id", effective_tenant_id)
            
            if not is_admin:
                query = query.eq("is_deleted", False)
                
            resp = query.limit(1).execute()
            rows = resp.data or []

        if not rows:
             raise HTTPException(status_code=404, detail="Record not found")

        return {"data": normalize_control(rows[0]), "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "get_security_control_by_id", return_dict=True, record_id=record_id, tenant_id=effective_tenant_id)

@router.post("/security-controls")
@require_permission("security_controls_create")
async def create_security_control(
    request: Request,
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = "/security-controls"
    payload: Dict[str, Any] = {}
    try:
        payload = await request.json()
        auth_data = auth_guard(Authorization)
        
        # Use tenant_id from token, strictly enforcing tenant isolation
        effective_tenant_id = auth_data.get("tenant_id")
        user_id = auth_data.get("user_id")

        if "Review_Date" in payload:
             payload["review_date"] = payload.pop("Review_Date")
        if "Review Date" in payload:
             payload["review_date"] = payload.pop("Review Date")
        
        check_deferred_status_permission(user_id, effective_tenant_id, payload.get("Status"))
        
        if "id" not in payload or not payload["id"]:
            payload["id"] = str(uuid.uuid4())
        
            
        # Overwrite tenant_id in payload with the authenticated user's tenant_id
        payload["tenant_id"] = effective_tenant_id
        payload["organization_id"] = payload.get("organization_id") or effective_tenant_id
        
        # Check Code uniqueness if provided
        if "code" in payload and payload["code"]:
            code_val = str(payload["code"]).strip()
            try: 
                check_code = (
                    supabase.table("security_controls")
                    .select("id")
                    .eq("code", code_val)
                    .eq("tenant_id", effective_tenant_id)
                    .eq("is_deleted", False)
                    .limit(1)
                    .execute()
                )
                if check_code.data and len(check_code.data) > 0:
                    raise HTTPException(status_code=400, detail="Control Code already exists")
            except HTTPException:
                raise
            except Exception:
                # Ignore schema errors if code column doesn't exist yet (though ensured above)
                pass

        try:
            check_query = (
                supabase
                .table("security_controls")
                .select("id, is_deleted")
                .eq("id", payload["id"])
                .eq("tenant_id", effective_tenant_id)
            )
            try:
                check_query = check_query.eq("is_deleted", False)
                check = check_query.limit(1).execute()
                if getattr(check, "error", None):
                    raise Exception(str(check.error))
            except Exception:
                check = (
                    supabase
                    .table("security_controls")
                    .select("id")
                    .eq("id", payload["id"])
                    .eq("tenant_id", effective_tenant_id)
                    .limit(1)
                    .execute()
                )
            if check.data and len(check.data) > 0:
                raise HTTPException(status_code=400, detail="Control ID already exists")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to validate control ID: {str(e)}")
        if "owner" in payload and payload.get("owner"):
            owner_email = payload.get("owner")
            try:
                resp_dept = supabase.table("users").select("department").eq("email", owner_email).limit(1).execute()
                if resp_dept.data and len(resp_dept.data) > 0:
                    dept = resp_dept.data[0].get("department")
                    if dept:
                        payload["department"] = dept
            except Exception:
                pass
        if "responsible_team" in payload:
            payload["reponsible_team"] = payload.pop("responsible_team")
        if "comments" not in payload and "Comments" not in payload:
            payload["comments"] = json.dumps([])
        elif "Comments" in payload:
            payload["comments"] = payload.get("Comments")
            payload.pop("Comments", None)
        if "task" not in payload:
            payload["task"] = json.dumps([])
        payload["is_deleted"] = False
        # Remove audit fields from payload to ensure single source of truth
        for key in ("created_at", "updated_at", "created_by", "updated_by", "deleted_at", "deleted_by"):
             payload.pop(key, None)
        for legacy_key in ("Comments_1", "Comments2", "Comments 2"):
            payload.pop(legacy_key, None)

        # Set audit fields
        user = auth_data.get("user", {})
        user_id = user.get("id") or user.get("user", {}).get("id") or auth_data.get("user_id")
        
        now = datetime.now(timezone.utc).isoformat()
        payload["created_at"] = now
        payload["updated_at"] = now
        payload["created_by"] = user_id
        payload["updated_by"] = user_id
        resp = (
            supabase
            .table("security_controls")
            .insert(payload)
            .execute()
        )
        if getattr(resp, "error", None):
            error_str = str(resp.error)
            if "is_deleted" in error_str.lower() and ("column" in error_str.lower() or "does not exist" in error_str.lower()):
                payload.pop("is_deleted", None)
                resp = (
                    supabase
                    .table("security_controls")
                    .insert(payload)
                    .execute()
                )
                if getattr(resp, "error", None):
                    raise HTTPException(status_code=400, detail=str(resp.error))
            else:
                raise HTTPException(status_code=400, detail=error_str)
        created_record = resp.data[0] if resp.data else None
        if not created_record:
            raise HTTPException(status_code=400, detail="Failed to create security control")
        return {"data": created_record, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "create_security_control", return_dict=True, tenant_id=payload.get("tenant_id"))

@router.put("/security-controls/{record_id}")
@require_permission("security_controls_retrieve")
async def update_security_control_put(
    record_id: str,
    request: Request,
    tenant_id: Optional[str] = Query(None),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = f"/security-controls/{record_id}"
    try:
        auth_data = auth_guard(Authorization)
        user = auth_data.get("user", {})
        user_id = user.get("id") or user.get("user", {}).get("id")
        
        # Use tenant_id from token
        effective_tenant_id = auth_data.get("tenant_id")
            
        is_admin = is_superadmin(user_id, effective_tenant_id) if user_id else False
        payload: Dict[str, Any] = await request.json()

        # Check permissions
        # Allow if user has update permission OR is an Auditor (who can update Review Date/Status)
        has_update_permission = is_admin or check_permission(user_id, effective_tenant_id, "security_controls", "update")
        
        if not has_update_permission:
            # Check if user is Internal or External Auditor
            user_roles = get_user_roles(user_id, effective_tenant_id) or []
            is_auditor = False
            for ur in user_roles:
                role_data = ur.get("roles") or {}
                role_name = str(role_data.get("role_name", "")).strip().lower()
                if role_name in ["internal auditor", "external auditor"]:
                    is_auditor = True
                    break
            
            if not is_auditor:
                raise HTTPException(status_code=403, detail="You do not have permission to update security_controls")

        # Find existing record
        query = supabase.table("security_controls").select("*")
        query = query.eq("id", record_id)
        
        query = query.eq("tenant_id", effective_tenant_id)
        if not is_admin:
            query = query.eq("is_deleted", False)
            
        exist = query.limit(1).execute()
        
        # Handle schema error for is_deleted
        if getattr(exist, "error", None):
             error_str = str(exist.error).lower()
             if "is_deleted" in error_str:
                  query = supabase.table("security_controls").select("*") # is_deleted might not exist
                  query = query.eq("id", record_id)
                  query = query.eq("tenant_id", effective_tenant_id)
                  exist = query.limit(1).execute()

        if not exist.data:
              raise HTTPException(status_code=404, detail="Record not found")

        current_record = exist.data[0]
        current_id = current_record.get("id")

        if current_record.get("is_deleted") and not is_admin:
             raise HTTPException(status_code=400, detail="Cannot update a deleted security control")

        # Filter out immutable or system-managed fields
        ignored_keys = {"is_deleted", "deleted_at", "deleted_by", "created_at", "created_by", "updated_at", "updated_by"}
        update_payload = {k: v for k, v in payload.items() if k not in ignored_keys}

        if "Review_Date" in update_payload:
             update_payload["review_date"] = update_payload.pop("Review_Date")
        if "Review Date" in update_payload:
             update_payload["review_date"] = update_payload.pop("Review Date")
        
        check_deferred_status_permission(user_id, effective_tenant_id, update_payload.get("Status"), current_record.get("Status") or current_record.get("status"))
        
        # Check Code uniqueness if changing
        if "code" in update_payload:
            new_code = str(update_payload["code"]).strip()
            current_code = str(current_record.get("code") or "").strip()
            if new_code and new_code != current_code:
                 try:
                     check_code = (
                         supabase.table("security_controls")
                         .select("id")
                         .eq("code", new_code)
                         .eq("tenant_id", effective_tenant_id)
                         .eq("is_deleted", False)
                         .neq("id", current_id) # Exclude self
                         .limit(1)
                         .execute()
                     )
                     if check_code.data and len(check_code.data) > 0:
                         raise HTTPException(status_code=400, detail="Control Code already exists")
                 except HTTPException:
                     raise
                 except Exception:
                     pass

        if "owner" in update_payload and update_payload.get("owner"):
            owner_email = update_payload.get("owner")
            try:
                resp_dept = supabase.table("users").select("department").eq("email", owner_email).limit(1).execute()
                rows_dept = resp_dept.data or []
                if rows_dept and isinstance(rows_dept[0], dict):
                    dept = rows_dept[0].get("department")
                    if dept:
                        update_payload["department"] = dept
            except Exception:
                pass
        if "responsible_team" in update_payload:
            update_payload["reponsible_team"] = update_payload.pop("responsible_team")
        if "Comments" in payload or "comments" in payload:
            comments_value = payload.get("Comments") or payload.get("comments")
            if isinstance(comments_value, (dict, list)):
                update_payload["comments"] = json.dumps(comments_value)
            elif isinstance(comments_value, str):
                update_payload["comments"] = comments_value
            else:
                update_payload["comments"] = json.dumps([])
            update_payload.pop("Comments", None)
        if "task" in payload:
            task_value = payload.get("task")
            if isinstance(task_value, (dict, list)):
                update_payload["task"] = json.dumps(task_value)
            elif isinstance(task_value, str):
                update_payload["task"] = task_value
        for legacy_key in ("Comments_1", "Comments2", "Comments 2", "updated_at"):
            update_payload.pop(legacy_key, None)

        # Set audit fields
        update_payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        update_payload["updated_by"] = user_id
            
        new_id = payload.get("id")
        # Update logic: use UUID if available for stability
        update_match_column = "id"
        update_match_value = current_id

        if new_id and isinstance(new_id, str) and new_id.strip() and new_id.strip() != current_id:
            check = (
                supabase
                .table("security_controls")
                .select("id")
                .eq("id", new_id.strip())
                .eq("tenant_id", effective_tenant_id)
                .limit(1)
                .execute()
            )
            if check.data:
                raise HTTPException(status_code=400, detail="New control ID already exists")
            update_payload["id"] = new_id.strip()
        else:
            update_payload.pop("uuid", None)
            
        resp = (
            supabase
            .table("security_controls")
            .update(update_payload)
            .eq(update_match_column, update_match_value)
            .eq("tenant_id", effective_tenant_id)
            .select()
            .execute()
        )
        if getattr(resp, "error", None):
            raise HTTPException(status_code=400, detail=str(resp.error))
        updated = resp.data[0] if resp.data else None
        
        if new_id and new_id.strip() != current_id:
            try:
                _ = (
                    supabase
                    .table("tasks")
                    .update({"control_id": new_id.strip()})
                    .eq("control_id", current_id)
                    .eq("tenant_id", effective_tenant_id)
                    .execute()
                )
            except Exception:
                pass
        return {"data": updated, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "update_security_control_put", return_dict=True, record_id=record_id, tenant_id=effective_tenant_id)

@router.delete("/security-controls/{record_id}")
@require_permission("security_controls_delete")
async def delete_security_control(
    record_id: str,
    tenant_id: Optional[str] = Query(None),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = f"/security-controls/{record_id}"
    try:
        auth_data = auth_guard(Authorization)
        user = auth_data.get("user", {})
        user_id = user.get("id") or user.get("user", {}).get("id")
        
        # Use tenant_id from token
        effective_tenant_id = auth_data.get("tenant_id")

        # Primary query: Always use ID
        query = supabase.table("security_controls").select("id")
        query = query.eq("id", record_id)
        
        query = query.eq("tenant_id", effective_tenant_id).eq("is_deleted", False)
        
        existing = query.limit(1).execute()
        
        # Handle schema error for is_deleted
        if getattr(existing, "error", None):
             error_str = str(existing.error).lower()
             if "is_deleted" in error_str:
                  # If is_deleted column missing, just query without it (fallback, though unlikely in prod)
                  query = supabase.table("security_controls").select("id")
                  query = query.eq("id", record_id)
                  query = query.eq("tenant_id", effective_tenant_id)
                  existing = query.limit(1).execute()

        if not existing.data:
            raise HTTPException(status_code=404, detail="Record not found")

        row = existing.data[0]
        # Determine best identifier for update
        update_match_column = "id"
        update_match_value = row.get("id")

        # Soft delete
        now = datetime.now(timezone.utc).isoformat()
        update_payload = {
            "is_deleted": True,
            "deleted_at": now,
            "deleted_by": user_id,
            "updated_at": now,
            "updated_by": user_id
        }
        
        resp = (
            supabase
            .table("security_controls")
            .update(update_payload)
            .eq(update_match_column, update_match_value)
            .eq("tenant_id", effective_tenant_id)
            .execute()
        )
        
        if getattr(resp, "error", None):
             raise HTTPException(status_code=400, detail=str(resp.error))
             
        return {"data": {"success": True, "message": "Security control deleted successfully"}, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "delete_security_control", return_dict=True, record_id=record_id, tenant_id=effective_tenant_id)

@router.patch("/security-controls/{record_id}/status")
async def update_security_control_status(
    record_id: str,
    request: Request,
    tenant_id: Optional[str] = Query(None),
    Authorization: Optional[str] = Header(default=None)
    ):
    endpoint = f"/security-controls/{record_id}/status"
    try:
        auth_data = auth_guard(Authorization)
        user = auth_data.get("user", {})
        user_id = user.get("id") or user.get("user", {}).get("id")
        effective_tenant_id = auth_data.get("tenant_id")

        if not user_id:
            raise HTTPException(status_code=401, detail="User ID not found in token")
        if not effective_tenant_id:
            effective_tenant_id = "00000000-0000-0000-0000-000000000001"

        privileged_role_names = {
            "admin",
            "super admin",
            "superadmin",
            "super_admin",
            "global super admin",
            "internal auditor",
            "external auditor",
            "contributor",
        }

        user_roles = get_user_roles(user_id, effective_tenant_id) or []
        normalized_roles = set()
        for ur in user_roles:
            role_data = ur.get("roles") or {}
            if isinstance(role_data, dict):
                role_name = role_data.get("role_name")
            else:
                role_name = ur.get("role_name")
            if role_name:
                normalized_roles.add(str(role_name).strip().lower())

        has_privileged_role = any(name in privileged_role_names for name in normalized_roles)

        if not has_privileged_role:
            if not check_permission(user_id, effective_tenant_id, "security_controls", "update"):
                raise HTTPException(status_code=403, detail="You do not have permission to update security_controls")

        payload: Dict[str, Any] = await request.json()
        if "Status" not in payload and "status" not in payload:
            raise HTTPException(status_code=400, detail="Status field is required")
        new_status = payload.get("Status") or payload.get("status")
        if not new_status or not str(new_status).strip():
            raise HTTPException(status_code=400, detail="Status cannot be empty")
        match_column = "id"
        exist = (
            supabase
            .table("security_controls")
            .select("*")
            .eq("id", record_id)
            .eq("tenant_id", effective_tenant_id)
            .limit(1)
            .execute()
        )
        if not exist.data:
             raise HTTPException(status_code=404, detail="Security control not found")

        def _is_soft_deleted(v) -> bool:
            if v is None:
                return False
            if isinstance(v, bool):
                return v
            s = str(v).strip().lower()
            if s in {"y", "yes", "true", "1", "t"}:
                return True
            if s in {"n", "no", "false", "0", "f", ""}:
                return False
            return False

        if _is_soft_deleted(exist.data[0].get("is_deleted")):
            raise HTTPException(status_code=400, detail="Cannot update status of a deleted security control")
        
        # Check permissions for Deferred status
        current_status = exist.data[0].get("Status") or exist.data[0].get("status")
        check_deferred_status_permission(user_id, effective_tenant_id, new_status, current_status)

        update_payload = {
            "Status": str(new_status).strip(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": user_id
        }
        resp = (
            supabase
            .table("security_controls")
            .update(update_payload)
            .eq(match_column, record_id)
            .eq("tenant_id", effective_tenant_id)
            .execute()
        )
        if getattr(resp, "error", None):
            raise HTTPException(status_code=400, detail=str(resp.error))
        return {
            "data": {
                "id": record_id,
                "Status": new_status,
                "message": "Status updated successfully"
            },
            "error": None
        }
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "update_security_control_status", return_dict=True, record_id=record_id, tenant_id=effective_tenant_id)

@router.post("/security-controls/{record_id}/comments")
@require_permission("security_controls_comment")
async def add_comment(
    record_id: str,
    request: Request,
    tenant_id: Optional[str] = Query(None),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = f"/security-controls/{record_id}/comments"
    try:
        auth_data = auth_guard(Authorization)
        user = auth_data.get("user", {})
        user_id = user.get("id") or user.get("user", {}).get("id")
        
        # Use tenant_id from token
        effective_tenant_id = auth_data.get("tenant_id")
            
        payload: Dict[str, Any] = await request.json()
        if "comment" not in payload:
            raise HTTPException(status_code=400, detail="Comment field is required")
        
        raw_comment = payload.get("comment")
        if isinstance(raw_comment, (dict, list)):
            comment_text = json.dumps(raw_comment)
        else:
            comment_text = str(raw_comment or "").strip()
            
        if not comment_text:
            raise HTTPException(status_code=400, detail="Comment cannot be empty")

        # Fetch existing comments
        query = supabase.table("security_controls").select("id, comments").eq("tenant_id", effective_tenant_id)
        query = query.eq("id", record_id)
        
        resp = query.limit(1).execute()
        if not resp.data:
             raise HTTPException(status_code=404, detail="Security control not found")

        row = resp.data[0]
        existing_raw = row.get("comments")
        
        try:
            comments = json.loads(existing_raw) if isinstance(existing_raw, str) else (existing_raw or [])
            if not isinstance(comments, list):
                comments = []
        except Exception:
            comments = []
            
        # Get user details for the comment
        user_name = "Unknown User"
        try:
            if user:
                # Try to get user details from the auth_data
                if user.get("email"):
                    user_name = user.get("email")
                
                # Check metadata
                meta = user.get("user_metadata", {})
                if meta.get("full_name"):
                    user_name = meta.get("full_name")
        except Exception:
            pass

        new_comment = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "text": comment_text, # Using 'text' to store the actual comment content
            "comment": comment_text, # duplicative but safe if frontend expects 'comment'
            "author": user_name,
            "time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        comments.append(new_comment)
        
        # Update the record
        update_payload = {
            "comments": json.dumps(comments),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": user_id
        }
        
        update_resp = supabase.table("security_controls").update(update_payload).eq("id", record_id).execute()
        
        if getattr(update_resp, "error", None):
             raise HTTPException(status_code=400, detail=str(update_resp.error))

        return {"data": new_comment, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "add_comment", return_dict=True, record_id=record_id, tenant_id=effective_tenant_id)

@router.get("/security-controls/{record_id}/comments")
@require_permission("security_controls_retrieve")
async def get_comments(
    record_id: str,
    tenant_id: Optional[str] = Query(None),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = f"/security-controls/{record_id}/comments"
    try:
        auth_data = auth_guard(Authorization)
        # Use tenant_id from token
        effective_tenant_id = auth_data.get("tenant_id")
        
        query = supabase.table("security_controls").select("*")
        query = query.eq("id", record_id)
            
        resp = query.eq("tenant_id", effective_tenant_id).limit(1).execute()
        
        rows = resp.data or []
             
        if not rows:
            raise HTTPException(status_code=404, detail="Record not found")
        row = rows[0]
        raw = row.get("comments")
        try:
            comments = json.loads(raw) if isinstance(raw, str) else (raw or [])
            if not isinstance(comments, list):
                comments = []
        except Exception:
            comments = []
        return {"data": comments, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "get_comments", return_dict=True, record_id=record_id, tenant_id=effective_tenant_id)

@router.post("/security-controls/{record_id}/tasks")
@require_permission("security_controls_create_task")
async def add_task(
    record_id: str,
    request: Request,
    tenant_id: Optional[str] = Query(None),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = f"/security-controls/{record_id}/tasks"
    try:
        auth_data = auth_guard(Authorization)
        user = auth_data.get("user", {})
        user_id = user.get("id") or user.get("user", {}).get("id") or auth_data.get("user_id")
        
        # Use tenant_id from token
        effective_tenant_id = auth_data.get("tenant_id")
            
        payload: Dict[str, Any] = await request.json()
        new_task = payload.get("task")
        if not new_task or not isinstance(new_task, dict):
            raise HTTPException(status_code=400, detail="Missing or invalid 'task' in payload")
            
        query = supabase.table("security_controls").select("id, task")
        query = query.eq("id", record_id)
        
        query = query.eq("tenant_id", effective_tenant_id)
        resp = query.limit(1).execute()
        rows = resp.data or []
        
        if not rows:
            raise HTTPException(status_code=404, detail="Record not found")
        row = rows[0]
        
        update_match_column = "id"
        update_match_value = row.get("id")

        raw = row.get("task")
        try:
            existing = json.loads(raw) if isinstance(raw, str) else (raw or [])
            if not isinstance(existing, list):
                existing = []
        except Exception:
            existing = []
        existing.append(new_task)
        update_payload = {
            "task": json.dumps(existing),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": user_id
        }
        update_resp = (
            supabase
            .table("security_controls")
            .update(update_payload)
            .eq(update_match_column, update_match_value)
            .eq("tenant_id", effective_tenant_id)
            .execute()
        )
        if getattr(update_resp, "error", None):
            raise HTTPException(status_code=400, detail=str(update_resp.error))
        return {"data": update_resp.data or [], "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "add_task", return_dict=True, record_id=record_id, tenant_id=effective_tenant_id)

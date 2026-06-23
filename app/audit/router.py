from fastapi import APIRouter, HTTPException, Request, Header, Query
from typing import Optional, Dict, Any, List, cast
import json
import uuid
from datetime import datetime, timezone
from services.db_service import local_db as supabase, execute_query
from services.rbac_service import is_superadmin
from services.rbac_service import require_permission
from utils.error_handler import handle_endpoint_error
from services.auth_service import get_user_from_token, auth_guard

router = APIRouter()


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

def ensure_column_exists(table_name: str, column_name: str, column_type_sql: str) -> None:
    try:
        cols = get_existing_columns(table_name)
        if column_name not in cols:
            execute_query(f'ALTER TABLE "{table_name}" ADD COLUMN IF NOT EXISTS "{column_name}" {column_type_sql}', fetch_all=False)
    except Exception:
        pass

def ensure_audits_table_exists() -> None:
    try:
        row = execute_query(
            "SELECT COUNT(*) AS cnt FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
            ("audits",),
            fetch_one=True
        ) or {}
        if (row.get("cnt") or 0) == 0:
            ddl = """
            CREATE TABLE IF NOT EXISTS "audits" (
              "id" UUID PRIMARY KEY,
              "tenant_id" UUID NOT NULL,
              "audit_name" TEXT,
              "audit_note" TEXT,
              "audit_priority" TEXT,
              "audit_type" TEXT,
              "audit_status" TEXT,
              "control_stage" TEXT,
              "audit_owner" TEXT,
              "attachment" TEXT,
              "comments" JSONB,
              "organization" TEXT,
              "audit_date" TIMESTAMPTZ,
              "is_deleted" BOOLEAN DEFAULT FALSE,
              "deleted_at" TIMESTAMPTZ,
              "deleted_by" TEXT,
              "created_at" TIMESTAMPTZ,
              "updated_at" TIMESTAMPTZ
            )
            """
            execute_query(ddl, fetch_all=False)
    except Exception:
        pass

@router.get("/audits")
@require_permission("audits_retrieve")
async def get_audits(
    tenant_id: str = Query('00000000-0000-0000-0000-000000000001'), # Kept for signature compatibility but ignored
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = "/audits"
    try:
        auth_data = auth_guard(Authorization)
        user = auth_data.get("user", {}) or {}
        nested_user = user.get("user") or {}
        user_id = user.get("id") or nested_user.get("id")
        
        # Enforce tenant isolation from token
        effective_tenant_id = auth_data.get("tenant_id")
        
        is_admin = is_superadmin(user_id, effective_tenant_id) if user_id else False
        
        # Optimize query: select only necessary fields for the list view
        # We need: id, audit_name, audit_priority, audit_type, audit_status, control_stage, audit_owner, department, organization, created_at, audit_date, tenant_id, is_deleted
        # audit_note is used for search, so include it too.
        # Exclude potentially large fields like attachment and comments if not needed for list.
        columns = "id, audit_name, audit_priority, audit_type, audit_status, control_stage, audit_owner, organization, created_at, audit_date, tenant_id, is_deleted, audit_note"
        query = supabase.table("audits").select(columns).eq("tenant_id", effective_tenant_id)
        
        if not is_admin:
            query = query.eq("is_deleted", False)
        # Always filter out deleted records for list view, even for admins, unless specifically requested otherwise
        # (Assuming standard behavior is to hide soft-deleted items from main list)
        else:
             query = query.eq("is_deleted", False)

        resp = query.execute()
        if getattr(resp, "error", None):
            error_str = str(resp.error)
            if "does not exist" in error_str.lower() and "relation" in error_str.lower():
                return {"data": [], "error": None}
            if "is_deleted" in error_str.lower() and ("column" in error_str.lower() or "does not exist" in error_str.lower()):
                query = supabase.table("audits").select("*").eq("tenant_id", effective_tenant_id)
                resp = query.execute()
                if getattr(resp, "error", None):
                    error_str_retry = str(resp.error)
                    if "does not exist" in error_str_retry.lower() and "relation" in error_str_retry.lower():
                        return {"data": [], "error": None}
                    error_detail = str(resp.error) if isinstance(resp.error, (str, dict)) else repr(resp.error)
                    raise HTTPException(status_code=400, detail=error_detail)
            else:
                error_detail = str(resp.error) if isinstance(resp.error, (str, dict)) else repr(resp.error)
                raise HTTPException(status_code=400, detail=error_detail)
        return {"data": resp.data or [], "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "get_audits", return_dict=True, tenant_id=effective_tenant_id)

@router.get("/audits/{audit_id}")
@require_permission("audits_retrieve")
async def get_audit(
    audit_id: str,
    tenant_id: str = Query('00000000-0000-0000-0000-000000000001'),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = f"/audits/{audit_id}"
    try:
        auth_data = auth_guard(Authorization)
        user = auth_data.get("user", {})
        user_id = user.get("id") or user.get("user", {}).get("id")
        
        effective_tenant_id = auth_data.get("tenant_id")
        
        is_admin = is_superadmin(user_id, effective_tenant_id) if user_id else False
        query = supabase.table("audits").select("*").eq("id", audit_id).eq("tenant_id", effective_tenant_id)
        if not is_admin:
            query = query.eq("is_deleted", False)
        resp = query.limit(1).execute()
        if getattr(resp, "error", None):
            error_str = str(resp.error)
            if "is_deleted" in error_str.lower() and ("column" in error_str.lower() or "does not exist" in error_str.lower()):
                query = supabase.table("audits").select("*").eq("id", audit_id).eq("tenant_id", effective_tenant_id)
                resp = query.limit(1).execute()
                if getattr(resp, "error", None):
                    error_detail = str(resp.error) if isinstance(resp.error, (str, dict)) else repr(resp.error)
                    raise HTTPException(status_code=400, detail=error_detail)
            else:
                error_detail = str(resp.error) if isinstance(resp.error, (str, dict)) else repr(resp.error)
                raise HTTPException(status_code=400, detail=error_detail)
        if not resp.data or len(resp.data) == 0:
            raise HTTPException(status_code=404, detail="Audit not found")
        return {"data": resp.data[0], "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "get_audit", return_dict=True, audit_id=audit_id, tenant_id=effective_tenant_id)

@router.post("/audits")
@require_permission("audits_create")
async def create_audit(
    request: Request,
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = "/audits"
    payload: Dict[str, Any] = {}
    try:
        ensure_audits_table_exists()
        auth_data = auth_guard(Authorization)
        effective_tenant_id = auth_data.get("tenant_id")
        
        payload = await request.json()
        
        # Enforce tenant isolation
        payload["tenant_id"] = effective_tenant_id
        
        if "id" not in payload or not payload["id"]:
            payload["id"] = str(uuid.uuid4())
        if "created_at" not in payload:
            payload["created_at"] = datetime.now(timezone.utc).isoformat()
        if "updated_at" not in payload:
            payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        payload["is_deleted"] = False
        try:
            if isinstance(payload.get("comments"), (list, dict)):
                payload["comments"] = json.dumps(payload["comments"])
        except Exception:
            pass
        ensure_column_exists("audits", "organization", "TEXT")
        ensure_column_exists("audits", "audit_date", "TIMESTAMPTZ")
        resp = supabase.table("audits").insert(payload).execute()
        if getattr(resp, "error", None):
            error_str = str(resp.error)
            if "does not exist" in error_str.lower() or "relation" in error_str.lower():
                try:
                    ensure_audits_table_exists()
                    resp_retry = supabase.table("audits").insert(payload).execute()
                    if getattr(resp_retry, "error", None):
                        raise HTTPException(
                            status_code=503,
                            detail="The audits table does not exist in the database. Please run the database migration to create the audits table."
                        )
                    created_audit = resp_retry.data[0] if resp_retry.data else None
                    if not created_audit:
                        raise HTTPException(status_code=400, detail="Failed to create audit")
                    return {"data": created_audit, "error": None}
                except HTTPException:
                    raise
                except Exception as _:
                    raise HTTPException(
                        status_code=503,
                        detail="The audits table does not exist in the database. Please run the database migration to create the audits table."
                    )
            raise HTTPException(status_code=400, detail=error_str)
        created_audit = resp.data[0] if resp.data else None
        if not created_audit:
            raise HTTPException(status_code=400, detail="Failed to create audit")
        return {"data": created_audit, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "create_audit", return_dict=True, tenant_id=payload.get("tenant_id"))

@router.put("/audits/{audit_id}")
@require_permission("audits_update")
async def update_audit(
    audit_id: str,
    request: Request,
    tenant_id: str = Query('00000000-0000-0000-0000-000000000001'),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = f"/audits/{audit_id}"
    payload: Dict[str, Any] = {}
    try:
        auth_data = auth_guard(Authorization)
        user = auth_data.get("user", {})
        user_id = user.get("id") or user.get("user", {}).get("id")
        
        effective_tenant_id = auth_data.get("tenant_id")
        
        payload = await request.json()
        
        is_admin = is_superadmin(user_id, effective_tenant_id) if user_id else False
        existing = supabase.table("audits").select("id, is_deleted").eq("id", audit_id).eq("tenant_id", effective_tenant_id).limit(1).execute()
        if not existing.data or len(existing.data) == 0:
            raise HTTPException(status_code=404, detail="Audit not found")
        rows_exist = existing.data or []
        if rows_exist and isinstance(rows_exist[0], dict) and rows_exist[0].get("is_deleted") and not is_admin:
            raise HTTPException(status_code=404, detail="Audit not found")
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        payload.pop("tenant_id", None)
        payload.pop("id", None)
        ensure_column_exists("audits", "organization", "TEXT")
        ensure_column_exists("audits", "audit_date", "TIMESTAMPTZ")
        resp = supabase.table("audits").eq("id", audit_id).eq("tenant_id", effective_tenant_id).update(payload).execute()
        if getattr(resp, "error", None):
            raise HTTPException(status_code=400, detail=str(resp.error))
        return {"data": resp.data[0] if resp.data else None, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "update_audit", return_dict=True, audit_id=audit_id, tenant_id=payload.get("tenant_id"))

@router.delete("/audits/{audit_id}")
@require_permission("audits_delete")
async def delete_audit(
    audit_id: str,
    tenant_id: str = Query('00000000-0000-0000-0000-000000000001'),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = f"/audits/{audit_id}"
    try:
        auth_data = auth_guard(Authorization)
        user = auth_data.get("user", {}) or {}
        nested_user = user.get("user") or {}
        user_id = user.get("id") or nested_user.get("id")
        
        effective_tenant_id = auth_data.get("tenant_id")
        
        existing = supabase.table("audits").select("id, is_deleted").eq("id", audit_id).eq("tenant_id", effective_tenant_id).limit(1).execute()
        if not existing.data or len(existing.data) == 0:
            raise HTTPException(status_code=404, detail="Audit not found")
        rows_exist = existing.data or []
        if rows_exist and isinstance(rows_exist[0], dict) and rows_exist[0].get("is_deleted"):
            return {"data": {"success": True, "message": "Audit deleted successfully"}, "error": None}
        update_data = {
            "is_deleted": True,
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "deleted_by": user_id,
        }
        resp = supabase.table("audits").eq("id", audit_id).eq("tenant_id", effective_tenant_id).update(update_data).execute()
        if getattr(resp, "error", None):
            raise HTTPException(status_code=400, detail=str(resp.error))
        return {"data": {"success": True, "message": "Audit deleted successfully"}, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "delete_audit", return_dict=True, audit_id=audit_id, tenant_id=tenant_id)

@router.post("/audits/{audit_id}/comments")
@require_permission("audits_comment")
async def add_audit_comment(
    audit_id: str,
    request: Request,
    tenant_id: str = Query('00000000-0000-0000-0000-000000000001'),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = f"/audits/{audit_id}/comments"
    try:
        auth_data = auth_guard(Authorization)
        effective_tenant_id = auth_data.get("tenant_id")
        
        payload = await request.json()
        new_comment = payload.get("comment")
        if not new_comment or not isinstance(new_comment, dict):
            raise HTTPException(status_code=400, detail="Missing or invalid 'comment' in payload")
        resp = (
            supabase
            .table("audits")
            .select("*")
            .eq("id", audit_id)
            .eq("tenant_id", effective_tenant_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise HTTPException(status_code=404, detail="Audit not found")
        row = rows[0]
        raw = row.get("comments")
        try:
            existing = json.loads(raw) if isinstance(raw, str) and raw.strip() else (raw if isinstance(raw, list) else [])
            if not isinstance(existing, list):
                existing = []
        except Exception:
            existing = []
        existing.append(new_comment)
        update_payload = {
            "comments": json.dumps(existing),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        update_resp = (
            supabase
            .table("audits")
            .update(update_payload)
            .eq("id", audit_id)
            .eq("tenant_id", effective_tenant_id)
            .execute()
        )
        if getattr(update_resp, "error", None):
            raise HTTPException(status_code=400, detail=str(update_resp.error))
        return {"data": update_resp.data or [], "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "add_audit_comment", return_dict=True, audit_id=audit_id, tenant_id=tenant_id)

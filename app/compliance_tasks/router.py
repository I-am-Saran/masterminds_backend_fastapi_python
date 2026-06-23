from fastapi import APIRouter, HTTPException, Request, Header, Query
from typing import Optional, Dict, Any, List
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

@router.get("/compliance-tasks")
@require_permission("tasks_retrieve")
async def get_tasks(
    control_id: Optional[str] = Query(None),
    tenant_id: str = Query('00000000-0000-0000-0000-000000000001'),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = "/compliance-tasks"
    try:
        auth_data = auth_guard(Authorization)
        user_id = auth_data.get("user_id")
        effective_tenant_id = auth_data.get("tenant_id")
        
        # Build raw SQL so we can include system-level tasks (tenant_id IS NULL)
        # and handle soft-delete even if the column doesn't exist.
        col_check_sql = """
            SELECT 1 
            FROM information_schema.columns 
            WHERE table_schema = 'public' 
              AND table_name = 'tasks' 
              AND column_name = 'is_deleted'
            LIMIT 1
        """
        has_is_deleted = bool(execute_query(col_check_sql, (), fetch_one=True))
        
        base_sql = (
            "SELECT * FROM tasks "
            "WHERE (tenant_id = %s OR tenant_id IS NULL) "
        )
        params: list[Any] = [effective_tenant_id]
        
        if control_id:
            base_sql += "AND control_id = %s "
            params.append(control_id)
        
        if has_is_deleted:
            base_sql += (
                "AND ("
                "is_deleted IS NULL "
                "OR is_deleted = FALSE "
                "OR TRIM(LOWER(CAST(is_deleted AS TEXT))) IN ('n','no','false','0','f')"
                ") "
            )
        
        base_sql += "ORDER BY created_at DESC NULLS LAST"
        
        rows = execute_query(base_sql, tuple(params), fetch_all=True) or []
        return {"data": rows, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "get_tasks", return_dict=True, control_id=control_id, tenant_id=locals().get("effective_tenant_id"))

@router.get("/compliance-tasks/control/{control_id}")
@require_permission("tasks_retrieve")
async def get_tasks_by_control(
    control_id: str,
    tenant_id: str = Query('00000000-0000-0000-0000-000000000001'),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = f"/compliance-tasks/control/{control_id}"
    try:
        auth_data = auth_guard(Authorization)
        user_id = auth_data.get("user_id")
        effective_tenant_id = auth_data.get("tenant_id")
        
        col_check_sql = """
            SELECT 1 
            FROM information_schema.columns 
            WHERE table_schema = 'public' 
              AND table_name = 'tasks' 
              AND column_name = 'is_deleted'
            LIMIT 1
        """
        has_is_deleted = bool(execute_query(col_check_sql, (), fetch_one=True))
        
        sql = (
            "SELECT * FROM tasks "
            "WHERE control_id = %s "
            "AND (tenant_id = %s OR tenant_id IS NULL) "
        )
        params: list[Any] = [control_id, effective_tenant_id]
        if has_is_deleted:
            sql += (
                "AND ("
                "is_deleted IS NULL "
                "OR is_deleted = FALSE "
                "OR TRIM(LOWER(CAST(is_deleted AS TEXT))) IN ('n','no','false','0','f')"
                ") "
            )
        sql += "ORDER BY created_at DESC NULLS LAST"
        
        rows = execute_query(sql, tuple(params), fetch_all=True) or []
        return {"data": rows, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "get_tasks_by_control", return_dict=True, control_id=control_id, tenant_id=locals().get("effective_tenant_id"))

@router.get("/compliance-tasks/{task_id}")
@require_permission("tasks_retrieve")
async def get_task(
    task_id: str,
    tenant_id: str = Query('00000000-0000-0000-0000-000000000001'),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = f"/compliance-tasks/{task_id}"
    try:
        auth_data = auth_guard(Authorization)
        user_id = auth_data.get("user_id")
        
        # Enforce tenant_id from token
        effective_tenant_id = auth_data.get("tenant_id")
        
        col_check_sql = """
            SELECT 1 
            FROM information_schema.columns 
            WHERE table_schema = 'public' 
              AND table_name = 'tasks' 
              AND column_name = 'is_deleted'
            LIMIT 1
        """
        has_is_deleted = bool(execute_query(col_check_sql, (), fetch_one=True))
        
        sql = (
            "SELECT * FROM tasks "
            "WHERE id = %s "
            "AND (tenant_id = %s OR tenant_id IS NULL) "
        )
        params: list[Any] = [task_id, effective_tenant_id]
        if has_is_deleted:
            sql += (
                "AND ("
                "is_deleted IS NULL "
                "OR is_deleted = FALSE "
                "OR TRIM(LOWER(CAST(is_deleted AS TEXT))) IN ('n','no','false','0','f')"
                ") "
            )
        sql += "LIMIT 1"
        
        row = execute_query(sql, tuple(params), fetch_one=True)
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"data": row, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "get_task", return_dict=True, task_id=task_id, tenant_id=locals().get("effective_tenant_id"))

@router.post("/compliance-tasks")
@require_permission("tasks_create")
async def create_task(
    request: Request,
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = "/compliance-tasks"
    payload: Dict[str, Any] = {}
    try:
        auth_data = auth_guard(Authorization)
        user_id = auth_data.get("user_id")
        # Enforce tenant_id from token
        tenant_id = auth_data.get("tenant_id")
        
        payload = await request.json()
        control_id = payload.get("control_id")
        control_uuid = payload.get("control_uuid")
        
        # Overwrite tenant_id with the secure one
        payload["tenant_id"] = tenant_id
        if "id" not in payload or not payload["id"]:
            payload["id"] = str(uuid.uuid4())
        if "created_at" not in payload:
            payload["created_at"] = datetime.now(timezone.utc).isoformat()
        if "updated_at" not in payload:
            payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        if control_id:
            payload["control_id"] = control_id
        if control_uuid:
            payload["control_uuid"] = control_uuid
        elif control_id:
            try:
                control_resp = (
                    supabase
                    .table("security_controls")
                    .select("uuid")
                    .eq("id", control_id)
                    .limit(1)
                    .execute()
                )
                if control_resp.data and len(control_resp.data) > 0 and isinstance(control_resp.data[0], dict):
                    control_uuid_value = control_resp.data[0].get("uuid")
                    if control_uuid_value:
                        payload["control_uuid"] = str(control_uuid_value)
            except Exception as e:
                pass
        ensure_column_exists("tasks", "organization", "TEXT")
        valid_task_columns = {
            "id", "control_id", "control_uuid", "task_name", "task_note",
            "task_priority", "task_type", "task_status", "attachment",
            "assigned_to", "created_at", "updated_at", "comments", "tenant_id",
            "organization"
        }
        existing_cols = set(get_existing_columns("tasks"))
        allowed_cols = {c for c in valid_task_columns if c in existing_cols}
        filtered_payload = {k: v for k, v in payload.items() if k in allowed_cols}
        resp = supabase.table("tasks").insert(filtered_payload).execute()
        if getattr(resp, "error", None):
            raise HTTPException(status_code=400, detail=str(resp.error))
        created_task = resp.data[0] if resp.data else None
        if not created_task:
            raise HTTPException(status_code=400, detail="Failed to create task")
        task_id = created_task.get("id")
        if control_id and task_id:
            try:
                control_resp = (
                    supabase
                    .table("security_controls")
                    .select("*")
                    .eq("id", control_id)
                    .limit(1)
                    .execute()
                )
                if control_resp.data and len(control_resp.data) > 0:
                    raw_tasks = control_resp.data[0].get("task")
                    try:
                        existing_tasks = json.loads(raw_tasks) if isinstance(raw_tasks, str) else (raw_tasks or [])
                        if not isinstance(existing_tasks, list):
                            existing_tasks = []
                    except Exception:
                        existing_tasks = []
                    task_ref = {
                        "id": task_id,
                        "task_name": created_task.get("task_name", ""),
                        "task_status": created_task.get("task_status", ""),
                        "created_at": created_task.get("created_at", ""),
                    }
                    if not any(t.get("id") == task_id for t in existing_tasks if isinstance(t, dict)):
                        existing_tasks.append(task_ref)
                    update_resp = (
                        supabase
                        .table("security_controls")
                        .update({
                            "task": json.dumps(existing_tasks),
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                            "updated_by": user_id
                        })
                        .eq("id", control_id)
                        .execute()
                    )
                    if getattr(update_resp, "error", None):
                        pass
            except Exception as e:
                pass
        return {"data": created_task, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "create_task", return_dict=True, tenant_id=payload.get("tenant_id"))

@router.put("/compliance-tasks/{task_id}")
@require_permission("tasks_update")
async def update_task(
    task_id: str,
    request: Request,
    tenant_id: str = Query('00000000-0000-0000-0000-000000000001'),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = f"/compliance-tasks/{task_id}"
    payload: Dict[str, Any] = {}
    try:
        auth_data = auth_guard(Authorization)
        user_id = auth_data.get("user_id")
        # Enforce tenant_id from token, ignoring query param
        tenant_id = auth_data.get("tenant_id")
        
        payload = await request.json()
        is_admin = is_superadmin(user_id, tenant_id) if user_id else False
        existing = supabase.table("tasks").select("id, is_deleted").eq("id", task_id).eq("tenant_id", tenant_id).limit(1).execute()
        if not existing.data or len(existing.data) == 0:
            raise HTTPException(status_code=404, detail="Task not found")
        first = existing.data[0] if existing.data and len(existing.data) > 0 else None
        if isinstance(first, dict) and first.get("is_deleted") and not is_admin:
            raise HTTPException(status_code=404, detail="Task not found")
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        payload.pop("tenant_id", None)
        payload.pop("id", None)
        ensure_column_exists("tasks", "organization", "TEXT")
        valid_task_columns = {
            "id", "control_id", "control_uuid", "task_name", "task_note",
            "task_priority", "task_type", "task_status", "attachment",
            "assigned_to", "created_at", "updated_at", "comments", "tenant_id",
            "organization"
        }
        existing_cols = set(get_existing_columns("tasks"))
        allowed_cols = {c for c in valid_task_columns if c in existing_cols}
        filtered_payload = {k: v for k, v in payload.items() if k in allowed_cols}
        resp = supabase.table("tasks").eq("id", task_id).eq("tenant_id", tenant_id).update(filtered_payload).execute()
        if getattr(resp, "error", None):
            raise HTTPException(status_code=400, detail=str(resp.error))
        return {"data": resp.data[0] if resp.data else None, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "update_task", return_dict=True, task_id=task_id, tenant_id=payload.get("tenant_id"))

@router.delete("/compliance-tasks/{task_id}")
@require_permission("tasks_delete")
async def delete_task(
    task_id: str,
    tenant_id: str = Query('00000000-0000-0000-0000-000000000001'),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = f"/compliance-tasks/{task_id}"
    try:
        auth_data = auth_guard(Authorization)
        user_id = auth_data.get("user_id")
        # Enforce tenant_id from token
        tenant_id = auth_data.get("tenant_id")
        
        existing = supabase.table("tasks").select("id, is_deleted").eq("id", task_id).eq("tenant_id", tenant_id).limit(1).execute()
        if not existing.data or len(existing.data) == 0:
            raise HTTPException(status_code=404, detail="Task not found")
        first = existing.data[0] if existing.data and len(existing.data) > 0 else None
        if isinstance(first, dict) and first.get("is_deleted"):
            raise HTTPException(status_code=400, detail="Task is already deleted")
        update_data = {
            "is_deleted": True,
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "deleted_by": user_id,
        }
        resp = supabase.table("tasks").eq("id", task_id).eq("tenant_id", tenant_id).update(update_data).execute()
        if getattr(resp, "error", None):
            raise HTTPException(status_code=400, detail=str(resp.error))
        return {"data": {"success": True, "message": "Task deleted successfully"}, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "delete_task", return_dict=True, task_id=task_id, tenant_id=tenant_id)

@router.post("/compliance-tasks/{task_id}/comments")
@require_permission("tasks_comment")
async def add_task_comment(
    task_id: str,
    request: Request,
    tenant_id: str = Query('00000000-0000-0000-0000-000000000001'),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = f"/compliance-tasks/{task_id}/comments"
    try:
        auth_data = auth_guard(Authorization)
        # Enforce tenant_id from token
        tenant_id = auth_data.get("tenant_id")
        
        payload = await request.json()
        new_comment = payload.get("comment")
        if not new_comment or not isinstance(new_comment, dict):
            raise HTTPException(status_code=400, detail="Missing or invalid 'comment' in payload")
        resp = (
            supabase
            .table("tasks")
            .select("*")
            .eq("id", task_id)
            .eq("tenant_id", tenant_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise HTTPException(status_code=404, detail="Task not found")
        row = rows[0]
        if not isinstance(row, dict):
            raise HTTPException(status_code=400, detail="Invalid task record format")
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
            .table("tasks")
            .update(update_payload)
            .eq("id", task_id)
            .eq("tenant_id", tenant_id)
            .execute()
        )
        if getattr(update_resp, "error", None):
            raise HTTPException(status_code=400, detail=str(update_resp.error))
        return {"data": update_resp.data or [], "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "add_task_comment", return_dict=True, task_id=task_id, tenant_id=tenant_id)

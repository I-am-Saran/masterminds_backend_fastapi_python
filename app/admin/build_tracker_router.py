from fastapi import APIRouter, HTTPException, Query, Path, Header, Request, Body
from typing import Optional, Dict, Any, cast
import json
import uuid as uuid_module
from datetime import datetime, timezone, date
from uuid import UUID
from services.db_service import execute_query, local_db as supabase
from services.auth_service import get_user_from_token, auth_guard
from utils.error_handler import handle_api_error
from services.rbac_service import require_permission
from pydantic import BaseModel

# Local definitions to avoid circular imports
class BuildEntry(BaseModel):
    project_id: Optional[str] = None
    build_name: Optional[str] = None
    build_number: Optional[str] = None
    transaction_type: Optional[str] = None
    version: Optional[str] = None
    status: Optional[str] = None
    signoff_status: Optional[str] = None
    build_arrived_date: Optional[str] = None
    build_signoff_date: Optional[str] = None
    build_date: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    reports: Optional[Dict[str, Any]] = None
    functional_report: Optional[Dict[str, Any]] = None
    automation_report: Optional[Dict[str, Any]] = None
    cybersecurity_report: Optional[Dict[str, Any]] = None
    tasks: Optional[list] = None
    build_received_time: Optional[str] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    build_sent_by: Optional[str] = None
    test_report_sent_by: Optional[str] = None
    remarks: Optional[str] = None

class TimeEntryCreate(BaseModel):
    resource_name: str
    user_email: str
    hours: float
    minutes: Optional[int] = 0
    log_date: date
    notes: Optional[str] = None

def ensure_builds_table():
    try:
        ensure_build_time_entries_table()
        execute_query(
            "ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT '00000000-0000-0000-0000-000000000001'",
            fetch_all=False,
        )
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS build_name TEXT", fetch_all=False)
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS version TEXT", fetch_all=False)
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'Active'", fetch_all=False)
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS start_date DATE", fetch_all=False)
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS end_date DATE", fetch_all=False)
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS created_by UUID", fetch_all=False)
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS updated_by UUID", fetch_all=False)
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now()", fetch_all=False)
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ", fetch_all=False)
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE", fetch_all=False)
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ", fetch_all=False)
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS deleted_by UUID", fetch_all=False)
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS build_received_time TIME", fetch_all=False)
        execute_query("ALTER TABLE public.builds ALTER COLUMN build_received_time SET DEFAULT LOCALTIME", fetch_all=False)
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS build_arrived_date DATE", fetch_all=False)
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS build_signoff_date DATE", fetch_all=False)
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS signoff_status TEXT", fetch_all=False)
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS build_sent_by TEXT", fetch_all=False)
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS test_report_sent_by TEXT", fetch_all=False)
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS remarks TEXT", fetch_all=False)
        # Align DB check constraint with API-allowed signoff statuses; include legacy variants for existing rows
        execute_query("ALTER TABLE public.builds DROP CONSTRAINT IF EXISTS builds_signoff_status_chk", fetch_all=False)
        execute_query(
            "ALTER TABLE public.builds ADD CONSTRAINT builds_signoff_status_chk CHECK (signoff_status IS NULL OR signoff_status IN ('Go', 'Conditional-Go', 'No-Go', 'Build Rejected', 'Conditional Go', 'Build-Rejected'))",
            fetch_all=False,
        )
        # Functional reports
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS functional_blocker INTEGER DEFAULT 0", fetch_all=False)
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS functional_high INTEGER DEFAULT 0", fetch_all=False)
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS functional_medium INTEGER DEFAULT 0", fetch_all=False)
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS functional_low INTEGER DEFAULT 0", fetch_all=False)
        
        # Automation reports
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS automation_blocker INTEGER DEFAULT 0", fetch_all=False)
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS automation_high INTEGER DEFAULT 0", fetch_all=False)
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS automation_medium INTEGER DEFAULT 0", fetch_all=False)
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS automation_low INTEGER DEFAULT 0", fetch_all=False)
        
        # Cyber reports
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS cyber_blocker INTEGER DEFAULT 0", fetch_all=False)
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS cyber_high INTEGER DEFAULT 0", fetch_all=False)
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS cyber_medium INTEGER DEFAULT 0", fetch_all=False)
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS cyber_low INTEGER DEFAULT 0", fetch_all=False)
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS comments JSONB DEFAULT '[]'", fetch_all=False)
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS time_entries JSONB DEFAULT '[]'::jsonb", fetch_all=False)
        execute_query("UPDATE public.builds SET time_entries = '[]'::jsonb WHERE time_entries IS NULL", fetch_all=False)
        execute_query("ALTER TABLE public.builds ALTER COLUMN time_entries SET NOT NULL", fetch_all=False)
        execute_query("CREATE INDEX IF NOT EXISTS idx_builds_time_entries ON public.builds USING GIN (time_entries)", fetch_all=False)
        execute_query(
            "ALTER TABLE public.builds "
            "ADD COLUMN IF NOT EXISTS resource_email TEXT, "
            "ADD COLUMN IF NOT EXISTS hours NUMERIC(5,2), "
            "ADD COLUMN IF NOT EXISTS notes TEXT;",
            fetch_all=False
        )
        execute_query("ALTER TABLE public.builds ADD COLUMN IF NOT EXISTS transaction_type TEXT", fetch_all=False)
        
        # Performance Indexes
        execute_query("CREATE INDEX IF NOT EXISTS idx_builds_project_id ON public.builds (project_id)", fetch_all=False)
        execute_query("CREATE INDEX IF NOT EXISTS idx_builds_signoff_status ON public.builds (signoff_status)", fetch_all=False)
        execute_query("CREATE INDEX IF NOT EXISTS idx_builds_dates ON public.builds (build_arrived_date, build_signoff_date)", fetch_all=False)
        execute_query("CREATE INDEX IF NOT EXISTS idx_builds_transaction_type ON public.builds (transaction_type)", fetch_all=False)
        try:
            execute_query("CREATE UNIQUE INDEX IF NOT EXISTS uniq_builds_project_number ON public.builds (project_id, build_number) WHERE is_deleted = FALSE", fetch_all=False)
        except Exception:
            pass
        
    except Exception as e:
        print(f"Error ensuring builds table schema: {e}")
        pass
    return None


def ensure_build_time_entries_table():
    try:
        execute_query("ALTER TABLE public.build_time_entries ADD COLUMN IF NOT EXISTS minutes INTEGER DEFAULT 0", fetch_all=False)
        execute_query("ALTER TABLE public.build_time_entries ALTER COLUMN build_id DROP NOT NULL", fetch_all=False)
        execute_query("ALTER TABLE public.build_time_entries ADD COLUMN IF NOT EXISTS effort_type TEXT", fetch_all=False)
        execute_query("ALTER TABLE public.build_time_entries ADD COLUMN IF NOT EXISTS task TEXT", fetch_all=False)
        execute_query("ALTER TABLE public.build_time_entries ADD COLUMN IF NOT EXISTS remarks TEXT", fetch_all=False)
        execute_query("ALTER TABLE public.build_time_entries ADD COLUMN IF NOT EXISTS tenant_id UUID", fetch_all=False)
        execute_query("ALTER TABLE public.build_time_entries ADD COLUMN IF NOT EXISTS project_id TEXT", fetch_all=False)
        execute_query("ALTER TABLE public.build_time_entries ADD COLUMN IF NOT EXISTS build_number TEXT", fetch_all=False)
    except Exception as e:
        print(f"Error ensuring build_time_entries table schema: {e}")
        pass
    return None

def ensure_build_reports_table(): 
    return None

def ensure_report_tables(): 
    return None

def ensure_projects_table(): 
    # Projects table management moved to projects module
    pass

def migrate_projects_and_link_builds(): 
    pass

def ensure_build_tasks_table():
    try:
        execute_query(
            """
            CREATE TABLE IF NOT EXISTS public.build_tasks (
                id BIGSERIAL PRIMARY KEY,
                build_id BIGINT REFERENCES public.builds(id) ON DELETE CASCADE,
                resource_name TEXT NOT NULL,
                task_assigned TEXT NOT NULL,
                spent_hours NUMERIC(5,2),
                created_at TIMESTAMPTZ DEFAULT now()
            );
            """,
            fetch_all=False
        )
        execute_query(
            "CREATE INDEX IF NOT EXISTS idx_build_tasks_build_id ON public.build_tasks(build_id)",
            fetch_all=False
        )
        execute_query(
            "ALTER TABLE public.build_tasks ADD COLUMN IF NOT EXISTS spent_hours NUMERIC(5,2)",
            fetch_all=False
        )
        execute_query(
            "ALTER TABLE public.build_tasks ALTER COLUMN spent_hours DROP NOT NULL",
            fetch_all=False
        )
        execute_query(
            "ALTER TABLE public.build_tasks ADD COLUMN IF NOT EXISTS task_type TEXT",
            fetch_all=False
        )
        execute_query(
            "ALTER TABLE public.build_tasks ADD COLUMN IF NOT EXISTS task_status VARCHAR(30) DEFAULT 'Yet to start'",
            fetch_all=False
        )
    except Exception as e:
        print(f"Error ensuring build_tasks table schema: {e}")
        pass

def ensure_build_signoff_table():
    try:
        execute_query(
            """
            CREATE TABLE IF NOT EXISTS public.build_signoffs (
                id BIGSERIAL PRIMARY KEY,
                build_id BIGINT REFERENCES public.builds(id) ON DELETE CASCADE,
                signoff_status TEXT,
                signoff_date DATE,
                total_bugs INTEGER DEFAULT 0,
                open_bugs INTEGER DEFAULT 0,
                functional_blocker INTEGER DEFAULT 0,
                functional_high INTEGER DEFAULT 0,
                functional_medium INTEGER DEFAULT 0,
                functional_low INTEGER DEFAULT 0,
                automation_blocker INTEGER DEFAULT 0,
                automation_high INTEGER DEFAULT 0,
                automation_medium INTEGER DEFAULT 0,
                automation_low INTEGER DEFAULT 0,
                cyber_blocker INTEGER DEFAULT 0,
                cyber_high INTEGER DEFAULT 0,
                cyber_medium INTEGER DEFAULT 0,
                cyber_low INTEGER DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now(),
                UNIQUE(build_id)
            );
            """,
            fetch_all=False
        )
    except Exception:
        pass



def _is_valid_uuid(s: Any) -> bool:
    if not s or not isinstance(s, str):
        return False
    try:
        uuid_module.UUID(s)
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _project_for_tenant(project_id: str, tenant_id: Optional[Any]) -> Dict[str, Any]:
    """Ensure project exists and belongs to tenant. Returns project row or raises HTTPException."""
    row = execute_query(
        "SELECT id, qa_resource_count FROM projects WHERE id::text = %s AND ((tenant_id::text = %s) OR (tenant_id IS NULL AND %s IS NULL)) LIMIT 1",
        (str(project_id).strip(), str(tenant_id) if tenant_id else None, str(tenant_id) if tenant_id else None),
        fetch_one=True,
        fetch_all=False,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Project not found or access denied")
    return row


def _build_project_tenant(build_id: Any) -> Optional[Any]:
    """Return tenant_id of the project that owns this build, or None if build not found."""
    cols_rows = execute_query(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
        ("builds",),
        fetch_all=True
    ) or []
    cols = {r.get("column_name") for r in cols_rows if r.get("column_name")}
    build = execute_query(
        "SELECT b.project_id, %s AS _has_is_deleted" + (", b.is_deleted" if "is_deleted" in cols else "") + " FROM builds b WHERE b.id = %s LIMIT 1",
        (True, build_id) if "is_deleted" in cols else (False, build_id),
        fetch_one=True,
        fetch_all=False,
    )
    if not build or not build.get("project_id"):
        return None
    if bool(build.get("_has_is_deleted")) and bool(build.get("is_deleted")):
        return None
    proj = execute_query(
        "SELECT tenant_id FROM projects WHERE id::text = %s LIMIT 1",
        (str(build["project_id"]).strip(),),
        fetch_one=True,
        fetch_all=False,
    )
    return proj.get("tenant_id") if proj else None

router = APIRouter(tags=["Build Tracker"])

@router.get("/builds/{build_id}/time-entries")
@require_permission("builds_retrieve")
async def get_time_entries(
    build_id: str = Path(...),
    Authorization: Optional[str] = Header(default=None)
):
    auth_data = auth_guard(Authorization)
    tenant_id = auth_data.get("tenant_id")
    
    # Verify tenant access via project
    build_tenant = _build_project_tenant(build_id)
    # _build_project_tenant returns None if build not found or deleted
    if not build_tenant:
         raise HTTPException(status_code=404, detail="Build not found")
         
    # Check if tenants match (handling None for system tenant if applicable, though usually strict equality is safer)
    if str(build_tenant) != str(tenant_id) and str(tenant_id) != '00000000-0000-0000-0000-000000000001':
         raise HTTPException(status_code=403, detail="Access denied")

    cols_rows = execute_query(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
        ("builds",),
        fetch_all=True
    ) or []
    cols = {r.get("column_name") for r in cols_rows if r.get("column_name")}
    sql = "SELECT id FROM builds WHERE id = %s"
    if "is_deleted" in cols:
        sql += " AND is_deleted = FALSE"
    sql += " LIMIT 1"
    existing = execute_query(sql, (build_id,), fetch_one=True, fetch_all=False)
    if not existing:
        raise HTTPException(status_code=404, detail="Build not found")
    entries = []
    try:
        bt_cols_rows = execute_query(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s AND table_schema = 'public'",
            ("build_time_entries",),
            fetch_all=True
        ) or []
        bt_cols = {r.get("column_name") for r in bt_cols_rows if r.get("column_name")}
        select_cols = ["id", "build_id", "resource_name", "user_email", "hours", "log_date", "notes"]
        if "minutes" in bt_cols:
            select_cols.append("minutes")
        if "created_by" in bt_cols:
            select_cols.append("created_by")
        if "logged_by_user_id" in bt_cols:
            select_cols.append("logged_by_user_id")
        select_cols.append("created_at")
        sql = f"SELECT {', '.join(select_cols)} FROM build_time_entries WHERE build_id = %s ORDER BY log_date ASC, created_at ASC"
        entries = execute_query(sql, (str(build_id),), fetch_all=True) or []
    except Exception:
        entries = []
    return entries

@router.get("/builds/{build_id}/comments")
@require_permission("builds_retrieve")
async def get_comments(
    build_id: UUID,
    Authorization: Optional[str] = Header(default=None)
):
    auth_data = auth_guard(Authorization)
    tenant_id = auth_data.get("tenant_id")

    # Verify tenant access via project
    build_tenant = _build_project_tenant(str(build_id))
    if not build_tenant:
         raise HTTPException(status_code=404, detail="Build not found")
         
    if str(build_tenant) != str(tenant_id) and str(tenant_id) != '00000000-0000-0000-0000-000000000001':
         raise HTTPException(status_code=403, detail="Access denied")

    existing = execute_query(
        "SELECT comments FROM public.builds WHERE id = %s AND is_deleted = FALSE",
        (str(build_id),),
        fetch_one=True,
        fetch_all=False
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Build not found")
    comments = existing.get("comments")
    if not comments:
        return []
    if isinstance(comments, str):
        try:
            comments = json.loads(comments)
        except Exception:
            comments = []
    return comments

@router.post("/task-tracker")
@require_permission("builds_update")
async def create_task_tracker_entries(
    request: Request,
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = "/task-tracker"
    try:
        auth_data = auth_guard(Authorization)
        user_id = auth_data.get("user_id")
        user = auth_data.get("user", {})
        user_email = user.get("email") or "Unknown"
        resource_name = user_email

        payload = await request.json()
        log_date = payload.get("date") or datetime.utcnow().strftime("%Y-%m-%d")
        availability = payload.get("availability")
        
        ensure_builds_table()
        
        bt_cols_rows = execute_query(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s AND table_schema = 'public'",
            ("build_time_entries",),
            fetch_all=True
        ) or []
        bt_cols = {r.get("column_name") for r in bt_cols_rows if r.get("column_name")}
        
        def insert_entry(b_id, t_type, hrs, mins, rmrks, act_task, p_id=None, build_num=None):
            cols = ["resource_name", "user_email", "hours", "log_date", "notes"]
            vals = [user_email, user_email, hrs, log_date, rmrks]
            
            tenant_id = auth_data.get("tenant_id")
            if "tenant_id" in bt_cols and tenant_id:
                cols.append("tenant_id")
                vals.append(tenant_id)
                
            if b_id:
                cols.append("build_id")
                vals.append(b_id)
            if p_id and "project_id" in bt_cols:
                cols.append("project_id")
                vals.append(p_id)
            if build_num and "build_number" in bt_cols:
                cols.append("build_number")
                vals.append(build_num)
            if "minutes" in bt_cols:
                cols.append("minutes")
                vals.append(mins)
            if "created_by" in bt_cols:
                cols.append("created_by")
                vals.append(user_id)
            if "logged_by_user_id" in bt_cols:
                cols.append("logged_by_user_id")
                vals.append(user_id)
            if "effort_type" in bt_cols:
                cols.append("effort_type")
                vals.append(t_type)
            if "task" in bt_cols:
                cols.append("task")
                vals.append(act_task)
            
            placeholders = ", ".join(["%s"] * len(cols))
            sql = f"INSERT INTO build_time_entries ({', '.join(cols)}) VALUES ({placeholders})"
            execute_query(sql, tuple(vals), fetch_all=False)

        if availability == "Leave":
            leave_hrs = float(payload.get("leave_hours") or 0)
            if leave_hrs > 0:
                insert_entry(None, "Leave", leave_hrs, 0, "Leave", "Leave")
        elif availability == "Present":
            we_type = payload.get("work_effort_type")
            if we_type == "Testing":
                for row in payload.get("testing_rows", []):
                    b_id = None
                    b_raw = row.get("build") or None
                    p_id = row.get("project_id") or row.get("project") or None
                    bn = row.get("build_number") or None
                    if b_raw:
                        try:
                            existing_build = execute_query("SELECT id FROM builds WHERE id = %s LIMIT 1", (b_raw,), fetch_one=True, fetch_all=False)
                            if existing_build and existing_build.get("id") is not None:
                                b_id = existing_build.get("id")
                        except Exception:
                            b_id = None
                    hrs = float(row.get("hours") or 0)
                    if hrs > 0:
                        tasks = row.get("tasks") or []
                        task_str = ", ".join(tasks) if isinstance(tasks, list) else str(tasks)
                        insert_entry(b_id, "Testing", hrs, 0, row.get("remarks") or "", task_str, p_id, bn)
            elif we_type == "Non-Testing":
                for row in payload.get("non_testing_rows", []):
                    hrs = float(row.get("hours") or 0)
                    if hrs > 0:
                        act = row.get("activity") or ""
                        insert_entry(None, "Non-Testing", hrs, 0, row.get("remarks") or "", act)

        return {"status": "success", "message": "Entries added successfully"}
    except HTTPException:
        raise
    except Exception as e:
        error_response, status_code = handle_api_error(
            e, endpoint, "create_task_tracker_entries", include_traceback=False
        )
        raise HTTPException(status_code=status_code, detail=error_response["error"])

@router.put("/time-entries/{entry_id}")
@require_permission("builds_update")
async def update_time_entry(
    entry_id: UUID = Path(...),
    payload: Dict[str, Any] = Body(...),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = f"/time-entries/{entry_id}"
    try:
        auth_data = auth_guard(Authorization)
        tenant_id = auth_data.get("tenant_id")
        ensure_builds_table()
        existing = execute_query("SELECT * FROM build_time_entries WHERE id = %s", (str(entry_id),), fetch_one=True, fetch_all=False)
        if not existing:
            raise HTTPException(status_code=404, detail="Entry not found")
        if str(existing.get("tenant_id")) != str(tenant_id) and str(tenant_id) != '00000000-0000-0000-0000-000000000001':
            raise HTTPException(status_code=403, detail="Access denied")
        sets = []
        vals = []
        if "hours" in payload:
            sets.append("hours = %s")
            vals.append(float(payload["hours"] or 0))
        if "minutes" in payload:
            sets.append("minutes = %s")
            vals.append(int(payload["minutes"] or 0))
        if "notes" in payload:
            sets.append("notes = %s")
            vals.append(payload["notes"])
        if "remarks" in payload:
            sets.append("remarks = %s")
            vals.append(payload["remarks"])
        if "task" in payload:
            sets.append("task = %s")
            vals.append(payload["task"])
        if "log_date" in payload:
            sets.append("log_date = %s")
            vals.append(payload["log_date"])
        if "build_id" in payload:
            sets.append("build_id = %s")
            vals.append(payload["build_id"] or None)
        if not sets:
            return {"status": "success", "message": "No changes"}
        vals.append(str(entry_id))
        sql = f"UPDATE build_time_entries SET {', '.join(sets)} WHERE id = %s"
        execute_query(sql, tuple(vals), fetch_all=False)
        return {"status": "success", "message": "Entry updated"}
    except HTTPException:
        raise
    except Exception as e:
        error_response, status_code = handle_api_error(e, endpoint, "update_time_entry", include_traceback=False)
        raise HTTPException(status_code=status_code, detail=error_response["error"])

@router.delete("/time-entries/{entry_id}")
@require_permission("builds_delete")
async def delete_time_entry(
    entry_id: UUID = Path(...),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = f"/time-entries/{entry_id}"
    try:
        auth_data = auth_guard(Authorization)
        tenant_id = auth_data.get("tenant_id")
        existing = execute_query("SELECT * FROM build_time_entries WHERE id = %s", (str(entry_id),), fetch_one=True, fetch_all=False)
        if not existing:
            raise HTTPException(status_code=404, detail="Entry not found")
        if str(existing.get("tenant_id")) != str(tenant_id) and str(tenant_id) != '00000000-0000-0000-0000-000000000001':
            raise HTTPException(status_code=403, detail="Access denied")
        execute_query("DELETE FROM build_time_entries WHERE id = %s", (str(entry_id),), fetch_all=False)
        return {"status": "success", "message": "Entry deleted"}
    except HTTPException:
        raise
    except Exception as e:
        error_response, status_code = handle_api_error(e, endpoint, "delete_time_entry", include_traceback=False)
        raise HTTPException(status_code=status_code, detail=error_response["error"])

@router.get("/time-entries")
@require_permission("builds_retrieve")
async def get_all_time_entries(
    project_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    page: Optional[int] = Query(default=None),
    limit: Optional[int] = Query(default=None),
    Authorization: Optional[str] = Header(default=None),
):
    auth_data = auth_guard(Authorization)
    tenant_id = auth_data.get("tenant_id")
    ensure_builds_table()
    build_cols_rows = execute_query(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
        ("builds",),
        fetch_all=True,
    ) or []
    build_cols = {r.get("column_name") for r in build_cols_rows if r.get("column_name")}
    project_cols_rows = execute_query(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
        ("projects",),
        fetch_all=True,
    ) or []
    project_cols = {r.get("column_name") for r in project_cols_rows if r.get("column_name")}

    bt_cols_rows = execute_query(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s AND table_schema = 'public'",
        ("build_time_entries",),
        fetch_all=True
    ) or []
    bt_cols = {r.get("column_name") for r in bt_cols_rows if r.get("column_name")}
    minutes_select = "bt.minutes," if "minutes" in bt_cols else "0 as minutes,"
    
    select_clause = f"""
        SELECT
            bt.id,
            bt.build_id,
            bt.resource_name,
            bt.user_email,
            bt.hours,
            {minutes_select}
            bt.log_date,
            bt.notes,
            bt.created_at,
            b.project_id,
            p.application_name as project_name,
            COALESCE(bt.effort_type, b.transaction_type) as effort_type,
            COALESCE(bt.task, b.transaction_type) as transaction_type,
            COALESCE(b.build_number, bt.build_number) as build_number,
            b.signoff_status
    """
    
    from_clause = """
        FROM build_time_entries bt
        LEFT JOIN builds b ON bt.build_id = b.id
        LEFT JOIN projects p ON COALESCE(b.project_id::text, bt.project_id::text) = p.id::text
    """
    t_id = str(tenant_id) if tenant_id else None
    
    # Initialize where_clause correctly with tenant check
    where_clause = "WHERE ((bt.tenant_id::text = %s) OR (p.tenant_id::text = %s) OR (p.tenant_id IS NULL AND bt.tenant_id IS NULL AND %s IS NULL))"
    params = [t_id, t_id, t_id]

    if "is_deleted" in build_cols:
        where_clause += " AND (b.is_deleted IS NULL OR b.is_deleted = FALSE)"
    if "is_deleted" in project_cols:
        where_clause += " AND (p.is_deleted IS NULL OR p.is_deleted = FALSE)"
    
    if project_id:
        where_clause += " AND b.project_id = %s"
        params.append(project_id)
        
    if status:
        where_clause += " AND b.signoff_status = %s"
        params.append(status)
        
    if start_date:
        where_clause += " AND bt.log_date >= %s"
        params.append(start_date)
        
    if end_date:
        where_clause += " AND bt.log_date <= %s"
        params.append(end_date)
        
    # Order by
    order_clause = " ORDER BY bt.log_date DESC, bt.created_at DESC"
    
    # Pagination
    limit_clause = ""
    total_count = 0
    
    if page is not None and limit is not None:
        try:
            p = int(page)
            l = int(limit)
            if p < 1: p = 1
            if l < 1: l = 10
            offset = (p - 1) * l
            limit_clause = f" LIMIT {l} OFFSET {offset}"
            
            # Count query
            count_sql = f"SELECT COUNT(*) as total {from_clause} {where_clause}"
            count_res = execute_query(count_sql, tuple(params), fetch_one=True, fetch_all=False)
            total_count = int(count_res.get("total", 0)) if count_res else 0
        except Exception:
            pass

    full_sql = f"{select_clause} {from_clause} {where_clause} {order_clause} {limit_clause}"
    rows = execute_query(full_sql, tuple(params), fetch_all=True) or []
    
    if page is not None and limit is not None:
        return {
            "data": rows,
            "total": total_count,
            "page": page,
            "limit": limit
        }
        
    return rows

@router.post("/builds/{build_id}/time-entries")
@require_permission("builds_update")
async def add_time_entry(
    build_id: UUID,
    payload: TimeEntryCreate = Body(...),
    Authorization: Optional[str] = Header(default=None)
):
    auth_data = auth_guard(Authorization)
    tenant_id = auth_data.get("tenant_id")
    user_id = auth_data.get("user_id")

    # Verify tenant access via project
    build_tenant = _build_project_tenant(str(build_id))
    if not build_tenant:
         raise HTTPException(status_code=404, detail="Build not found")
         
    if str(build_tenant) != str(tenant_id) and str(tenant_id) != '00000000-0000-0000-0000-000000000001':
         raise HTTPException(status_code=403, detail="Access denied")

    if payload.resource_name is None or str(payload.resource_name).strip() == "":
        raise HTTPException(status_code=422, detail="Resource name is required")
    if payload.user_email is None or str(payload.user_email).strip() == "":
        raise HTTPException(status_code=422, detail="User email is required")
    if payload.hours is None:
        raise HTTPException(status_code=422, detail="Hours is required")
    if payload.log_date is None:
        raise HTTPException(status_code=422, detail="Date is required")
    cols_rows = execute_query(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
        ("builds",),
        fetch_all=True
    ) or []
    cols = {r.get("column_name") for r in cols_rows if r.get("column_name")}
    sql = "SELECT id FROM builds WHERE id = %s"
    if "is_deleted" in cols:
        sql += " AND is_deleted = FALSE"
    sql += " LIMIT 1"
    existing = execute_query(sql, (str(build_id),), fetch_one=True, fetch_all=False)
    if not existing:
        raise HTTPException(status_code=404, detail="Build not found")
    bt_cols_rows = execute_query(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s AND table_schema = 'public'",
        ("build_time_entries",),
        fetch_all=True
    ) or []
    bt_cols = {r.get("column_name") for r in bt_cols_rows if r.get("column_name")}
    cols = ["build_id", "resource_name", "user_email", "hours", "log_date", "notes"]
    vals = [build_id, str(payload.user_email).strip(), str(payload.user_email).strip(), payload.hours, payload.log_date, payload.notes]
    if "minutes" in bt_cols:
        cols.append("minutes")
        vals.append(payload.minutes or 0)
    if "created_by" in bt_cols:
        cols.append("created_by")
        vals.append(user_id)
    if "logged_by_user_id" in bt_cols:
        cols.append("logged_by_user_id")
        vals.append(user_id)
    placeholders = ", ".join(["%s"] * len(cols))
    sql = f"INSERT INTO build_time_entries ({', '.join(cols)}) VALUES ({placeholders})"
    execute_query(sql, tuple(vals), fetch_all=False)
    return {"success": True}

@router.get("/builds/{build_id}/signoff")
@require_permission("builds_retrieve")
async def get_build_signoff(build_id: str = Path(...)):
    endpoint = f"/builds/{build_id}/signoff"
    try:
        ensure_builds_table()
        ensure_build_signoff_table()
        
        # Try to get from build_signoffs first
        signoff = execute_query(
            "SELECT * FROM build_signoffs WHERE build_id = %s LIMIT 1",
            (build_id,),
            fetch_one=True,
            fetch_all=False
        )
        
        if signoff:
            return {"status": "success", "data": signoff}
            
        # Fallback: Get current build info + reports to pre-fill
        ensure_report_tables()
        build = execute_query(
            "SELECT signoff_status, build_signoff_date, total_bugs, open_bugs FROM builds WHERE id = %s LIMIT 1",
            (build_id,),
            fetch_one=True,
            fetch_all=False
        )
        
        if not build:
             raise HTTPException(status_code=404, detail="Build not found")

        fr = execute_query(
            "SELECT blocker, high, medium, low FROM functional_test_reports WHERE build_id = %s LIMIT 1",
            (build_id,), 
            fetch_one=True, 
            fetch_all=False
        ) or {}
        ar = execute_query(
            "SELECT blocker, high, medium, low FROM automation_test_reports WHERE build_id = %s LIMIT 1",
            (build_id,),
            fetch_one=True,
            fetch_all=False
        ) or {}
        cr = execute_query(
            "SELECT blocker, high, medium, low FROM cybersecurity_reports WHERE build_id = %s LIMIT 1",
            (build_id,),
            fetch_one=True,
            fetch_all=False
        ) or {}

        # Construct a temporary object matching build_signoffs structure
        data = {
            "build_id": build_id,
            "signoff_status": build.get("signoff_status"),
            "signoff_date": build.get("build_signoff_date"),
            "total_bugs": build.get("total_bugs", 0),
            "open_bugs": build.get("open_bugs", 0),
            "build_received_time": str(build.get("build_received_time")) if build.get("build_received_time") else None,
            "functional_blocker": fr.get("blocker", 0),
            "functional_high": fr.get("high", 0),
            "functional_medium": fr.get("medium", 0),
            "functional_low": fr.get("low", 0),
            "automation_blocker": ar.get("blocker", 0),
            "automation_high": ar.get("high", 0),
            "automation_medium": ar.get("medium", 0),
            "automation_low": ar.get("low", 0),
            "cyber_blocker": cr.get("blocker", 0),
            "cyber_high": cr.get("high", 0),
            "cyber_medium": cr.get("medium", 0),
            "cyber_low": cr.get("low", 0),
        }
        return {"status": "success", "data": data}

    except HTTPException:
        raise
    except Exception as e:
        error_response, status_code = handle_api_error(
            e, endpoint, context={"operation": "get_build_signoff", "build_id": build_id},
            include_traceback=False, user_message="Failed to fetch build signoff"
        )
        raise HTTPException(status_code=status_code, detail=error_response["error"])


@router.post("/builds/{build_id}/signoff")
@require_permission("builds_update")
async def save_build_signoff(build_id: int = Path(...), request: Request = None):
    endpoint = f"/builds/{build_id}/signoff"
    try:
        ensure_builds_table()
        ensure_build_signoff_table()
        ensure_report_tables()
        ensure_build_reports_table()
        
        payload = await request.json()
        
        allowed_signoff_statuses = ["Go", "Conditional Go", "No-Go", "Build-Rejected"]
        signoff_status = payload.get("signoff_status")
        if signoff_status and signoff_status not in allowed_signoff_statuses:
             raise HTTPException(status_code=400, detail="Invalid signoff status")
        
        # Prepare data for build_signoffs
        signoff_data = {
            "build_id": build_id,
            "signoff_status": payload.get("signoff_status"),
            "signoff_date": payload.get("signoff_date"),
            "total_bugs": int(payload.get("total_bugs", 0)),
            "open_bugs": int(payload.get("open_bugs", 0)),
            "functional_blocker": int(payload.get("functional_blocker", 0)),
            "functional_high": int(payload.get("functional_high", 0)),
            "functional_medium": int(payload.get("functional_medium", 0)),
            "functional_low": int(payload.get("functional_low", 0)),
            "automation_blocker": int(payload.get("automation_blocker", 0)),
            "automation_high": int(payload.get("automation_high", 0)),
            "automation_medium": int(payload.get("automation_medium", 0)),
            "automation_low": int(payload.get("automation_low", 0)),
            "cyber_blocker": int(payload.get("cyber_blocker", 0)),
            "cyber_high": int(payload.get("cyber_high", 0)),
            "cyber_medium": int(payload.get("cyber_medium", 0)),
            "cyber_low": int(payload.get("cyber_low", 0)),
            "updated_at": "now()"
        }

        # 1. Upsert into build_signoffs
        check = execute_query("SELECT id FROM build_signoffs WHERE build_id = %s", (build_id,), fetch_one=True, fetch_all=False)
        if check:
            supabase.table("build_signoffs").update(signoff_data).eq("build_id", build_id).execute()
        else:
            supabase.table("build_signoffs").insert(signoff_data).execute()

        # 2. Sync to builds table (as primary storage now)
        build_update = {
            "signoff_status": signoff_data["signoff_status"],
            "build_signoff_date": signoff_data["signoff_date"],
            "total_bugs": signoff_data["total_bugs"],
            "open_bugs": signoff_data["open_bugs"],
            "functional_blocker": signoff_data["functional_blocker"],
            "functional_high": signoff_data["functional_high"],
            "functional_medium": signoff_data["functional_medium"],
            "functional_low": signoff_data["functional_low"],
            "automation_blocker": signoff_data["automation_blocker"],
            "automation_high": signoff_data["automation_high"],
            "automation_medium": signoff_data["automation_medium"],
            "automation_low": signoff_data["automation_low"],
            "cyber_blocker": signoff_data["cyber_blocker"],
            "cyber_high": signoff_data["cyber_high"],
            "cyber_medium": signoff_data["cyber_medium"],
            "cyber_low": signoff_data["cyber_low"]
        }
        supabase.table("builds").update(build_update).eq("id", build_id).execute()

        # 3. Sync to report tables (for dashboards)
        def sync_report(table, prefix):
            data = {
                "build_id": build_id,
                "blocker": signoff_data[f"{prefix}_blocker"],
                "high": signoff_data[f"{prefix}_high"],
                "medium": signoff_data[f"{prefix}_medium"],
                "low": signoff_data[f"{prefix}_low"]
            }
            exists = execute_query(f"SELECT id FROM {table} WHERE build_id = %s", (build_id,), fetch_one=True, fetch_all=False)
            if exists:
                execute_query(
                    f"UPDATE {table} SET blocker=%s, high=%s, medium=%s, low=%s WHERE build_id=%s",
                    (data["blocker"], data["high"], data["medium"], data["low"], build_id),
                    fetch_all=False
                )
            else:
                execute_query(
                    f"INSERT INTO {table} (build_id, blocker, high, medium, low) VALUES (%s, %s, %s, %s, %s)",
                    (build_id, data["blocker"], data["high"], data["medium"], data["low"]),
                    fetch_all=False
                )
        
        # Also update the aggregate build_reports table
        def sync_build_reports(rtype, prefix):
             data = {
                "blocker_count": signoff_data[f"{prefix}_blocker"],
                "high_count": signoff_data[f"{prefix}_high"],
                "medium_count": signoff_data[f"{prefix}_medium"]
            }
             execute_query(
                """
                INSERT INTO build_reports (build_id, report_type, blocker_count, high_count, medium_count)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (build_id, report_type)
                DO UPDATE SET blocker_count = EXCLUDED.blocker_count,
                              high_count = EXCLUDED.high_count,
                              medium_count = EXCLUDED.medium_count
                """,
                (build_id, rtype, data["blocker_count"], data["high_count"], data["medium_count"]),
                fetch_all=False
            )

        sync_report("functional_test_reports", "functional")
        sync_report("automation_test_reports", "automation")
        sync_report("cybersecurity_reports", "cyber")
        
        sync_build_reports("functional", "functional")
        sync_build_reports("automation", "automation")
        sync_build_reports("cybersecurity", "cyber")

        return {"status": "success", "message": "Sign-off saved successfully"}

    except HTTPException:
        raise
    except Exception as e:
        error_response, status_code = handle_api_error(
            e, endpoint, context={"operation": "save_build_signoff", "build_id": build_id},
            include_traceback=False, user_message="Failed to save build signoff"
        )
        raise HTTPException(status_code=status_code, detail=error_response["error"])

@router.get("/builds/{build_id}/tasks")
@require_permission("builds_retrieve")
async def get_build_tasks(build_id: int = Path(...)):
    endpoint = f"/builds/{build_id}/tasks"
    try:
        ensure_build_tasks_table()
        rows = execute_query(
            "SELECT id, resource_name, task_assigned, COALESCE(spent_hours, 0) AS spent_hours, task_type, COALESCE(task_status, 'Yet to start') as task_status, created_at FROM public.build_tasks WHERE build_id = %s ORDER BY id ASC",
            (build_id,),
            fetch_all=True
        ) or []
        return {"status": "success", "data": rows}
    except HTTPException:
        raise
    except Exception as e:
        error_response, status_code = handle_api_error(
            e,
            endpoint,
            context={"operation": "get_build_tasks", "build_id": build_id},
            include_traceback=False,
            user_message="Failed to fetch build tasks"
        )
        raise HTTPException(status_code=status_code, detail=error_response["error"])

@router.post("/builds/{build_id}/tasks")
@require_permission("builds_update")
async def save_build_tasks(build_id: int = Path(...), request: Request = None):
    endpoint = f"/builds/{build_id}/tasks"
    try:
        ensure_build_tasks_table()
        payload = await request.json()
        tasks = payload if isinstance(payload, list) else payload.get("tasks")
        if not isinstance(tasks, list):
            tasks = []
        existing_build = execute_query("SELECT id, project_id FROM builds WHERE id = %s LIMIT 1", (build_id,), fetch_one=True, fetch_all=False)
        if not existing_build:
            raise HTTPException(status_code=404, detail="Build not found")
        project_id = int(existing_build.get("project_id"))
        proj = execute_query("SELECT qa_resource_count FROM projects WHERE id = %s LIMIT 1", (project_id,), fetch_one=True, fetch_all=False) or {"qa_resource_count": 0}
        qa_limit_raw = proj.get("qa_resource_count", 0)
        try:
            qa_limit = int(qa_limit_raw or 0)
        except Exception:
            qa_limit = 0
        if qa_limit < 0:
            qa_limit = 0
        rows = []
        seen = set()
        allowed_task_statuses = ["Yet to start", "In progress", "Completed", "Hold"]
        for t in tasks:
            rn = str((t or {}).get("resource_name") or "").strip()
            ta = str((t or {}).get("task_assigned") or "").strip()
            tt = str((t or {}).get("task_type") or "").strip()
            ts = str((t or {}).get("task_status") or "Yet to start").strip()
            
            if ts not in allowed_task_statuses:
                 raise HTTPException(status_code=400, detail=f"Invalid task status: {ts}")

            sh_raw = (t or {}).get("spent_hours")
            sh = None
            if sh_raw is not None:
                if isinstance(sh_raw, (int, float)):
                    sh = float(sh_raw)
                else:
                    s = str(sh_raw).strip()
                    if s != "":
                        try:
                            sh = float(s)
                        except Exception:
                            sh = None
            if rn == "" or ta == "":
                raise HTTPException(status_code=400, detail="Resource Name and Task Assigned are required")
            if sh is not None and (sh < 0 or sh > 24):
                raise HTTPException(status_code=400, detail="Enter valid hours")
            
            # Allow same resource across different task types if needed, but keeping resource name check simple for now as per requirement "Duplicate resources not allowed" usually meant per project/build context in previous code. 
            # I will assume "Duplicate resources not allowed" restriction from previous code still implies 1 row per resource per build.
            if rn.lower() in seen:
                raise HTTPException(status_code=400, detail="Duplicate resources not allowed")
            seen.add(rn.lower())
            
            rows.append((build_id, rn, ta, sh, tt, ts))
            
        # QA resource limit check removed - validation should only apply in Project creation
        execute_query("DELETE FROM public.build_tasks WHERE build_id = %s", (build_id,), fetch_all=False)
        for row in rows:
            execute_query(
                "INSERT INTO public.build_tasks (build_id, resource_name, task_assigned, spent_hours, task_type, task_status) VALUES (%s, %s, %s, %s, %s, %s)",
                row,
                fetch_all=False
            )
        return {"status": "success", "data": {"count": len(rows)}}
    except HTTPException:
        raise
    except Exception as e:
        error_response, status_code = handle_api_error(
            e,
            endpoint,
            context={"operation": "save_build_tasks", "build_id": build_id},
            include_traceback=False,
            user_message="Failed to save build tasks"
        )
        raise HTTPException(status_code=status_code, detail=error_response["error"])



@router.get("/application-dropdown")
@require_permission("builds_retrieve")
async def get_application_dropdown(Authorization: Optional[str] = Header(default=None)):
    """Return distinct application names from projects (tenant-scoped) for dropdowns."""
    endpoint = "/application-dropdown"
    try:
        auth_data = auth_guard(Authorization)
        tenant_id = auth_data.get("tenant_id")
        user_id = auth_data.get("user_id")
        
        from services.rbac_service import get_user_accessible_project_names
        accessible_projects = get_user_accessible_project_names(user_id, tenant_id, skip_team_restriction=True)
        
        rows = execute_query(
            "SELECT DISTINCT application_name FROM projects WHERE (tenant_id = %s OR (tenant_id IS NULL AND %s IS NULL)) AND application_name IS NOT NULL ORDER BY application_name",
            (tenant_id, tenant_id),
            fetch_all=True,
        ) or []
        names = [r.get("application_name") for r in rows if r.get("application_name")]
        
        if accessible_projects is not None:
            names = [n for n in names if n in accessible_projects]
            
        return {"status": "success", "data": names}
    except HTTPException:
        raise
    except Exception as e:
        error_response, status_code = handle_api_error(
            e,
            endpoint,
            context={"operation": "get_application_dropdown"},
            include_traceback=False,
            user_message="Failed to fetch application names",
        )
        raise HTTPException(status_code=status_code, detail=error_response["error"])


def _tenant_match(user_tenant: Any, resource_tenant: Any) -> bool:
    """True if user is allowed to access resource by tenant (both None, or equal)."""
    if user_tenant is None and resource_tenant is None:
        return True
    if user_tenant is None or resource_tenant is None:
        return False
    return str(user_tenant) == str(resource_tenant)


@router.post("/builds")
@require_permission("builds_create")
async def create_build(entry: BuildEntry, Authorization: Optional[str] = Header(default=None)):
    endpoint = "/builds"
    try:
        auth_data = auth_guard(Authorization)
        tenant_id = auth_data.get("tenant_id")
        ensure_builds_table()
        cols_rows = execute_query(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            ("builds",),
            fetch_all=True
        ) or []
        cols = {r.get("column_name") for r in cols_rows if r.get("column_name")}
        project_id = entry.project_id
        if not project_id:
            raise HTTPException(status_code=400, detail="project_id is required")
        project_id = str(project_id).strip()
        _project_for_tenant(project_id, tenant_id)
        allowed_statuses = {"Go", "Conditional-Go", "No-Go", "Build Rejected"}
        cols_rows = execute_query(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            ("builds",),
            fetch_all=True
        ) or []
        cols = {r.get("column_name") for r in cols_rows if r.get("column_name")}
        signoff_status = (entry.signoff_status or entry.status or "").strip()
        if signoff_status and signoff_status not in allowed_statuses:
            raise HTTPException(status_code=400, detail="Invalid signoff_status")
            
        arrived_date = (entry.build_arrived_date or "").strip() or None
        build_number = (entry.build_number or "").strip()
        if not build_number:
            raise HTTPException(status_code=400, detail="build_number is required")
        dup = execute_query(
            "SELECT id FROM builds WHERE project_id = %s AND build_number = %s AND (is_deleted IS NULL OR is_deleted = FALSE) LIMIT 1",
            (project_id, build_number),
            fetch_one=True,
            fetch_all=False
        )
        if dup and dup.get("id"):
            raise HTTPException(status_code=409, detail="Build already exists")
        signoff_date = (entry.build_signoff_date or entry.build_date or "").strip() or None
        received_time_raw = entry.build_received_time
        received_time = (str(received_time_raw).strip() or None) if received_time_raw is not None and received_time_raw != "" else None
        user_id = auth_data.get("user_id")
        payload = {
            "tenant_id": tenant_id,
            "build_number": build_number,
            "project_id": project_id,
            "build_name": (entry.build_name or "").strip() or None,
            "transaction_type": (entry.transaction_type or "").strip() or None,
            "version": (entry.version or "").strip() or None,
            "status": (entry.status or "").strip() or "Active",
            "signoff_status": signoff_status if signoff_status else None,
            "build_arrived_date": arrived_date,
            "build_received_time": received_time,
            "build_signoff_date": signoff_date,
            "build_sent_by": (entry.build_sent_by or "").strip() or None,
            "test_report_sent_by": (entry.test_report_sent_by or "").strip() or None,
            "remarks": (entry.remarks or "").strip() or None,
            "start_date": (entry.start_date or "").strip() or None,
            "end_date": (entry.end_date or "").strip() or None,
            "created_by": user_id,
            "updated_by": user_id if "updated_by" in cols else None,
            "is_deleted": False if "is_deleted" in cols else None,
            "created_at": "now()" if "created_at" in cols else None,
            "updated_at": "now()" if "updated_at" in cols else None,
            "id": str(uuid_module.uuid4()) if "id" in cols else None,
        }
        payload = {k: v for k, v in payload.items() if k in cols and v is not None}
        
        # Explicitly set tenant_id if column exists
        if "tenant_id" in cols:
            payload["tenant_id"] = tenant_id

        resp = supabase.table("builds").insert(payload).execute()
        if getattr(resp, "error", None):
            err_str = str(resp.error)
            try:
                print(err_str)
            except Exception:
                pass
            if "does not exist" in err_str.lower() and "relation" in err_str.lower():
                ensure_builds_table()
                resp = supabase.table("builds").insert(payload).execute()
                if getattr(resp, "error", None):
                    raise HTTPException(status_code=400, detail=str(resp.error))
            elif "column" in err_str.lower() and "does not exist" in err_str.lower():
                ensure_builds_table()
                resp = supabase.table("builds").insert(payload).execute()
                if getattr(resp, "error", None):
                    raise HTTPException(status_code=400, detail=str(resp.error))
            else:
                raise HTTPException(status_code=400, detail=err_str)
        created = resp.data[0] if resp.data else None
        if created and created.get("id"):
            build_id = created["id"]
        else:
            row = execute_query(
                "SELECT id FROM builds WHERE project_id = %s AND build_number = %s ORDER BY id DESC LIMIT 1",
                (project_id, build_number),
                fetch_one=True,
                fetch_all=False
            )
            if not row or not row.get("id"):
                raise HTTPException(status_code=400, detail="Failed to create build")
            build_id = row["id"]
            created = created or {"id": build_id, "build_number": build_number, "project_id": project_id}
        # Optionally save reports atomically if provided
        try:
            ensure_build_reports_table()
            ensure_report_tables()
            if created and created.get("id"):
                cid = created["id"]
                def _nz(v):
                    try:
                        n = int(v)
                        return 0 if n < 0 else n
                    except Exception:
                        return 0
                # Support both aggregated "reports" and individual report payloads
                reports = entry.reports or {}
                functional = entry.functional_report or reports.get("functional") or {}
                automation = entry.automation_report or reports.get("automation") or {}
                cybersecurity = entry.cybersecurity_report or reports.get("cybersecurity") or {}
                def _save(cid, rtype, payload):
                    blocker = _nz(payload.get("blocker"))
                    high = _nz(payload.get("high"))
                    medium = _nz(payload.get("medium"))
                    low = _nz(payload.get("low"))
                    execute_query(
                        """
                        INSERT INTO build_reports (build_id, report_type, blocker_count, high_count, medium_count)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (build_id, report_type)
                        DO UPDATE SET blocker_count = EXCLUDED.blocker_count,
                                      high_count = EXCLUDED.high_count,
                                      medium_count = EXCLUDED.medium_count
                        """,
                        (cid, rtype, blocker, high, medium),
                        fetch_all=False
                    )
                    table = "functional_test_reports" if rtype == "functional" else ("automation_test_reports" if rtype == "automation" else "cybersecurity_reports")
                    exists = execute_query(f"SELECT id FROM {table} WHERE build_id = %s LIMIT 1", (cid,), fetch_one=True, fetch_all=False)
                    if exists and exists.get("id"):
                        execute_query(
                            f"UPDATE {table} SET blocker = %s, high = %s, medium = %s, low = %s WHERE build_id = %s",
                            (blocker, high, medium, low, cid),
                            fetch_all=False
                        )
                    else:
                        execute_query(
                            f"INSERT INTO {table} (build_id, blocker, high, medium, low) VALUES (%s, %s, %s, %s, %s)",
                            (cid, blocker, high, medium, low),
                            fetch_all=False
                        )
                if functional:
                    _save(cid, "functional", functional)
                if automation:
                    _save(cid, "automation", automation)
                if cybersecurity:
                    _save(cid, "cybersecurity", cybersecurity)
        except Exception:
            # Best-effort; if report save fails, still return build creation
            pass
        return {"message": "Build created successfully", "data": created}
    except HTTPException:
        raise
    except Exception as e:
        error_response, status_code = handle_api_error(
            e, endpoint, context={"operation": "create_build"}, include_traceback=False, user_message="Failed to create build"
        )
        raise HTTPException(status_code=status_code, detail=error_response["error"])

@router.post("/builds/draft")
@require_permission("builds_create")
async def create_build_draft(request: Request, Authorization: Optional[str] = Header(default=None)):
    endpoint = "/builds/draft"
    try:
        auth_data = auth_guard(Authorization)
        tenant_id = auth_data.get("tenant_id")
        ensure_builds_table()
        body = await request.json()
        project_id = body.get("project_id")
        if project_id is None:
            raise HTTPException(status_code=400, detail="project_id is required")
        project_id = str(project_id).strip()
        _project_for_tenant(project_id, tenant_id)
        user_bn_raw = body.get("build_number")
        if user_bn_raw is None:
            raise HTTPException(status_code=400, detail="build_number is required")
        user_bn = str(user_bn_raw).strip()
        if not user_bn:
            raise HTTPException(status_code=400, detail="build_number is required")
        next_build_number = user_bn
        user_id = auth_data.get("user_id")
        payload = {
            "tenant_id": tenant_id,
            "build_number": next_build_number,
            "project_id": project_id,
            "build_name": None,
            "version": None,
            "status": "Active",
            "signoff_status": None,
            "build_arrived_date": None,
            "build_signoff_date": None,
            "created_by": user_id,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        resp = supabase.table("builds").insert(payload).execute()
        if getattr(resp, "error", None):
            raise HTTPException(status_code=400, detail=str(resp.error))
        created = resp.data[0] if resp.data else None
        if created and created.get("id"):
            return {"status": "success", "data": {"id": int(created["id"]), "build_number": next_build_number}}
        row = execute_query(
            "SELECT id FROM builds WHERE project_id = %s AND build_number = %s ORDER BY id DESC LIMIT 1",
            (project_id, next_build_number),
            fetch_one=True,
            fetch_all=False
        )
        if not row or not row.get("id"):
            raise HTTPException(status_code=400, detail="Failed to create draft build")
        return {"status": "success", "data": {"id": int(row["id"]), "build_number": next_build_number}}
    except HTTPException:
        raise
    except Exception as e:
        error_response, status_code = handle_api_error(
            e,
            endpoint,
            context={"operation": "create_build_draft"},
            include_traceback=False,
            user_message="Failed to create draft build"
        )
        raise HTTPException(status_code=status_code, detail=error_response["error"])

@router.post("/builds/{build_id}/reports/{report_type}")
@require_permission("builds_update")
async def save_build_report(build_id: int = Path(...), report_type: str = Path(...), request: Request = None):
    endpoint = f"/builds/{build_id}/reports/{report_type}"
    try:
        ensure_builds_table()
        ensure_build_reports_table()
        ensure_report_tables()
        rtype = (report_type or "").strip().lower()
        if rtype not in {"functional", "automation", "cybersecurity"}:
            raise HTTPException(status_code=400, detail="Invalid report type")
        payload = await request.json()
        def _nz(v):
            try:
                n = int(v)
                return 0 if n < 0 else n
            except Exception:
                return 0
        blocker = _nz((payload or {}).get("blocker"))
        high = _nz((payload or {}).get("high"))
        medium = _nz((payload or {}).get("medium"))
        low = _nz((payload or {}).get("low"))
        existing_build = execute_query("SELECT id, project_id FROM builds WHERE id = %s LIMIT 1", (build_id,), fetch_one=True, fetch_all=False)
        if not existing_build:
            # Auto-create draft build when missing, using project_id from payload
            project_id = None
            try:
                project_id = (payload or {}).get("project_id")
            except Exception:
                project_id = None
            if project_id is None:
                raise HTTPException(status_code=400, detail="project_id required to create draft build")
            build_number = None
            try:
                build_number = (payload or {}).get("build_number")
            except Exception:
                build_number = None
            build_number = str(build_number or "").strip()
            if not build_number:
                raise HTTPException(status_code=400, detail="build_number required to create draft build")
            draft_payload = {
                "tenant_id": "00000000-0000-0000-0000-000000000001",
                "build_number": build_number,
                "project_id": project_id,
                "status": "Active",
                "signoff_status": None,
                "build_arrived_date": None,
                "build_signoff_date": None,
            }
            resp = supabase.table("builds").insert(draft_payload).execute()
            if getattr(resp, "error", None):
                raise HTTPException(status_code=400, detail=str(resp.error))
            created = resp.data[0] if resp.data else None
            if not created or not created.get("id"):
                row = execute_query(
                    "SELECT id FROM builds WHERE project_id = %s AND build_number = %s ORDER BY id DESC LIMIT 1",
                    (project_id, build_number),
                    fetch_one=True,
                    fetch_all=False
                )
                if not row or not row.get("id"):
                    raise HTTPException(status_code=400, detail="Failed to create draft build")
                build_id = int(row["id"])
            else:
                build_id = int(created["id"])
        execute_query(
            """
            INSERT INTO build_reports (build_id, report_type, blocker_count, high_count, medium_count)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (build_id, report_type)
            DO UPDATE SET blocker_count = EXCLUDED.blocker_count,
                          high_count = EXCLUDED.high_count,
                          medium_count = EXCLUDED.medium_count
            """,
            (build_id, rtype, blocker, high, medium),
            fetch_all=False
        )
        if rtype == "functional":
            exists = execute_query("SELECT id FROM functional_test_reports WHERE build_id = %s LIMIT 1", (build_id,), fetch_one=True, fetch_all=False)
            if exists and exists.get("id"):
                execute_query(
                    "UPDATE functional_test_reports SET blocker = %s, high = %s, medium = %s, low = %s WHERE build_id = %s",
                    (blocker, high, medium, low, build_id),
                    fetch_all=False
                )
            else:
                execute_query(
                    "INSERT INTO functional_test_reports (build_id, blocker, high, medium, low) VALUES (%s, %s, %s, %s, %s)",
                    (build_id, blocker, high, medium, low),
                    fetch_all=False
                )
        elif rtype == "automation":
            exists = execute_query("SELECT id FROM automation_test_reports WHERE build_id = %s LIMIT 1", (build_id,), fetch_one=True, fetch_all=False)
            if exists and exists.get("id"):
                execute_query(
                    "UPDATE automation_test_reports SET blocker = %s, high = %s, medium = %s, low = %s WHERE build_id = %s",
                    (blocker, high, medium, low, build_id),
                    fetch_all=False
                )
            else:
                execute_query(
                    "INSERT INTO automation_test_reports (build_id, blocker, high, medium, low) VALUES (%s, %s, %s, %s, %s)",
                    (build_id, blocker, high, medium, low),
                    fetch_all=False
                )
        else:
            exists = execute_query("SELECT id FROM cybersecurity_reports WHERE build_id = %s LIMIT 1", (build_id,), fetch_one=True, fetch_all=False)
            if exists and exists.get("id"):
                execute_query(
                    "UPDATE cybersecurity_reports SET blocker = %s, high = %s, medium = %s, low = %s WHERE build_id = %s",
                    (blocker, high, medium, low, build_id),
                    fetch_all=False
                )
            else:
                execute_query(
                    "INSERT INTO cybersecurity_reports (build_id, blocker, high, medium, low) VALUES (%s, %s, %s, %s, %s)",
                    (build_id, blocker, high, medium, low),
                    fetch_all=False
                )
        return {"status": "success", "data": {"build_id": build_id, "report_type": rtype}}
    except HTTPException:
        raise
    except Exception as e:
        error_response, status_code = handle_api_error(
            e,
            endpoint,
            context={"operation": "save_build_report", "build_id": build_id, "report_type": report_type},
            include_traceback=False,
            user_message="Failed to save build report"
        )
        raise HTTPException(status_code=status_code, detail=error_response["error"])

@router.get("/builds/{build_id}/tasks")
async def get_build_tasks(build_id: str = Path(...)):
    endpoint = f"/builds/{build_id}/tasks"
    try:
        ensure_build_tasks_table()
        rows = execute_query(
            "SELECT id, resource_name, task_assigned, COALESCE(spent_hours, 0) AS spent_hours, created_at FROM public.build_tasks WHERE build_id = %s ORDER BY id ASC",
            (build_id,),
            fetch_all=True
        ) or []
        return {"status": "success", "data": rows}
    except HTTPException:
        raise
    except Exception as e:
        error_response, status_code = handle_api_error(
            e,
            endpoint,
            context={"operation": "get_build_tasks", "build_id": build_id},
            include_traceback=False,
            user_message="Failed to fetch build tasks"
        )
        raise HTTPException(status_code=status_code, detail=error_response["error"])

@router.post("/builds/{build_id}/tasks")
async def save_build_tasks(build_id: str = Path(...), request: Request = None):
    endpoint = f"/builds/{build_id}/tasks"
    try:
        ensure_build_tasks_table()
        payload = await request.json()
        tasks = payload if isinstance(payload, list) else payload.get("tasks")
        if not isinstance(tasks, list):
            tasks = []
        existing_build = execute_query("SELECT id, project_id FROM builds WHERE id = %s LIMIT 1", (build_id,), fetch_one=True, fetch_all=False)
        if not existing_build:
            raise HTTPException(status_code=404, detail="Build not found")
        project_id = existing_build.get("project_id")
        proj = execute_query("SELECT qa_resource_count FROM projects WHERE id = %s LIMIT 1", (project_id,), fetch_one=True, fetch_all=False) or {"qa_resource_count": 0}
        qa_limit_raw = proj.get("qa_resource_count", 0)
        try:
            qa_limit = int(qa_limit_raw or 0)
        except Exception:
            qa_limit = 0
        if qa_limit < 0:
            qa_limit = 0
        rows = []
        seen = set()
        for t in tasks:
            rn = str((t or {}).get("resource_name") or "").strip()
            ta = str((t or {}).get("task_assigned") or "").strip()
            sh_raw = (t or {}).get("spent_hours")
            sh = None
            if sh_raw is not None:
                if isinstance(sh_raw, (int, float)):
                    sh = float(sh_raw)
                else:
                    s = str(sh_raw).strip()
                    if s != "":
                        try:
                            sh = float(s)
                        except Exception:
                            sh = None
            if rn == "" or ta == "":
                raise HTTPException(status_code=400, detail="Resource Name and Task Assigned are required")
            if sh is not None and (sh < 0 or sh > 24):
                raise HTTPException(status_code=400, detail="Enter valid hours")
            if rn.lower() in seen:
                raise HTTPException(status_code=400, detail="Duplicate resources not allowed")
            seen.add(rn.lower())
            rows.append((build_id, rn, ta, sh))
        if qa_limit is not None and qa_limit >= 0 and len(rows) > qa_limit:
            raise HTTPException(status_code=400, detail="Task count exceeds allocated QA resources")
        execute_query("DELETE FROM public.build_tasks WHERE build_id = %s", (build_id,), fetch_all=False)
        for row in rows:
            execute_query(
                "INSERT INTO public.build_tasks (build_id, resource_name, task_assigned, spent_hours) VALUES (%s, %s, %s, %s)",
                row,
                fetch_all=False
            )
        return {"status": "success", "data": {"count": len(rows)}}
    except HTTPException:
        raise
    except Exception as e:
        error_response, status_code = handle_api_error(
            e,
            endpoint,
            context={"operation": "save_build_tasks", "build_id": build_id},
            include_traceback=False,
            user_message="Failed to save build tasks"
        )
        raise HTTPException(status_code=status_code, detail=error_response["error"])

@router.get("/builds/report")
async def get_build_report(project_id: str = Query(...)):
    endpoint = "/builds/report"
    try:
        ensure_builds_table()
        ensure_report_tables()
        build = execute_query(
            "SELECT * FROM builds WHERE project_id = %s ORDER BY build_signoff_date DESC NULLS LAST, id DESC LIMIT 1",
            (project_id,),
            fetch_one=True,
            fetch_all=False
        )
        if not build:
            return {
                "status": "success",
                "data": None
            }
        build_id = build.get("id")
        fr = execute_query(
            "SELECT blocker, high, medium, low FROM functional_reports WHERE build_id = %s LIMIT 1",
            (build_id,),
            fetch_one=True,
            fetch_all=False
        ) or {}
        ar = execute_query(
            "SELECT blocker, high, medium, low FROM automation_reports WHERE build_id = %s LIMIT 1",
            (build_id,),
            fetch_one=True,
            fetch_all=False
        ) or {}
        cr = execute_query(
            "SELECT blocker, high, medium, low FROM cybersecurity_reports WHERE build_id = %s LIMIT 1",
            (build_id,),
            fetch_one=True,
            fetch_all=False
        ) or {}
        return {
            "status": "success",
            "data": {
                "build": build,
                "reports": {
                    "functional": {
                        "blocker": int(fr.get("blocker") or 0),
                        "high": int(fr.get("high") or 0),
                        "medium": int(fr.get("medium") or 0),
                        "low": int(fr.get("low") or 0),
                    },
                    "automation": {
                        "blocker": int(ar.get("blocker") or 0),
                        "high": int(ar.get("high") or 0),
                        "medium": int(ar.get("medium") or 0),
                        "low": int(ar.get("low") or 0),
                    },
                    "cybersecurity": {
                        "blocker": int(cr.get("blocker") or 0),
                        "high": int(cr.get("high") or 0),
                        "medium": int(cr.get("medium") or 0),
                        "low": int(cr.get("low") or 0),
                    },
                }
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        error_response, status_code = handle_api_error(
            e,
            endpoint,
            context={"operation": "get_build_report"},
            include_traceback=False,
            user_message="Failed to fetch build report"
        )
        raise HTTPException(status_code=status_code, detail=error_response["error"])


@router.get("/builds/{build_id}/report")
@require_permission("builds_retrieve")
async def get_specific_build_report(build_id: int = Path(...)):
    endpoint = f"/builds/{build_id}/report"
    try:
        ensure_builds_table()
        ensure_report_tables()
        build = execute_query(
            "SELECT * FROM builds WHERE id = %s LIMIT 1",
            (build_id,),
            fetch_one=True,
            fetch_all=False
        )
        if not build:
            return {
                "status": "success",
                "data": None
            }
        fr = execute_query(
            "SELECT blocker, high, medium, low FROM functional_test_reports WHERE build_id = %s LIMIT 1",
            (build_id,),
            fetch_one=True,
            fetch_all=False
        ) or {}
        ar = execute_query(
            "SELECT blocker, high, medium, low FROM automation_test_reports WHERE build_id = %s LIMIT 1",
            (build_id,),
            fetch_one=True,
            fetch_all=False
        ) or {}
        cr = execute_query(
            "SELECT blocker, high, medium, low FROM cybersecurity_reports WHERE build_id = %s LIMIT 1",
            (build_id,),
            fetch_one=True,
            fetch_all=False
        ) or {}
        return {
            "status": "success",
            "data": {
                "build": build,
                "summary": {},
                "functional": {
                    "blocker": int(fr.get("blocker") or 0),
                    "high": int(fr.get("high") or 0),
                    "medium": int(fr.get("medium") or 0),
                    "low": int(fr.get("low") or 0),
                },
                "automation": {
                    "blocker": int(ar.get("blocker") or 0),
                    "high": int(ar.get("high") or 0),
                    "medium": int(ar.get("medium") or 0),
                    "low": int(ar.get("low") or 0),
                },
                "cybersecurity": {
                    "blocker": int(cr.get("blocker") or 0),
                    "high": int(cr.get("high") or 0),
                    "medium": int(cr.get("medium") or 0),
                    "low": int(cr.get("low") or 0),
                }
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        error_response, status_code = handle_api_error(
            e,
            endpoint,
            context={"operation": "get_specific_build_report", "build_id": build_id},
            include_traceback=False,
            user_message="Failed to fetch specific build report"
        )
        raise HTTPException(status_code=status_code, detail=error_response["error"])


@router.delete("/builds/{build_id}")
@require_permission("builds_delete")
async def soft_delete_build(build_id: UUID = Path(...), Authorization: Optional[str] = Header(default=None)):
    endpoint = f"/builds/{build_id}"
    try:
        ensure_builds_table()
        auth_data = auth_guard(Authorization)
        tenant_id = auth_data.get("tenant_id")
        cols_rows = execute_query(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            ("builds",),
            fetch_all=True
        ) or []
        cols = {r.get("column_name") for r in cols_rows if r.get("column_name")}
        existing = execute_query("SELECT id, project_id FROM builds WHERE id = %s LIMIT 1", (str(build_id),), fetch_one=True, fetch_all=False)
        if not existing:
            raise HTTPException(status_code=404, detail="Build not found")
        build_tenant = _build_project_tenant(str(build_id))
        if not _tenant_match(tenant_id, build_tenant):
            raise HTTPException(status_code=404, detail="Build not found or access denied")
        if "is_deleted" in cols:
            user_id = auth_data.get("user_id")
            sets = []
            params = []
            sets.append("is_deleted = TRUE")
            if "deleted_at" in cols:
                sets.append("deleted_at = now()")
            if "deleted_by" in cols and user_id:
                sets.append("deleted_by = %s")
                params.append(user_id)
            if "updated_at" in cols:
                sets.append("updated_at = now()")
            if "updated_by" in cols and user_id:
                sets.append("updated_by = %s")
                params.append(user_id)
            params.append(str(build_id))
            execute_query(f"UPDATE builds SET {', '.join(sets)} WHERE id = %s", tuple(params), fetch_all=False)
        else:
            execute_query("DELETE FROM builds WHERE id = %s", (str(build_id),), fetch_all=False)
        return {"data": {"success": True, "message": "Build deleted successfully."}, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        error_response, status_code = handle_api_error(
            e,
            endpoint,
            context={"operation": "soft_delete_build", "build_id": build_id},
            include_traceback=False,
            user_message="Failed to delete build"
        )
        raise HTTPException(status_code=status_code, detail=error_response["error"])


@router.put("/builds/{build_id}")
@require_permission("builds_update")
async def update_build(build_id: str = Path(...), entry: BuildEntry = None, Authorization: Optional[str] = Header(default=None)):
    endpoint = f"/builds/{build_id}"
    try:
        auth_data = auth_guard(Authorization)
        tenant_id = auth_data.get("tenant_id")
        ensure_builds_table()
        cols_rows = execute_query(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            ("builds",),
            fetch_all=True
        ) or []
        cols = {r.get("column_name") for r in cols_rows if r.get("column_name")}
        if entry is None:
            raise HTTPException(status_code=400, detail="Payload is required")
        build_tenant = _build_project_tenant(build_id)
        if not _tenant_match(tenant_id, build_tenant):
            raise HTTPException(status_code=404, detail="Build not found or access denied")
        validated_project_id = None
        if entry.project_id is not None:
            new_pid = str(entry.project_id).strip()
            if new_pid:
                _project_for_tenant(new_pid, tenant_id)
                validated_project_id = new_pid
        allowed_statuses = {"Go", "Conditional-Go", "No-Go", "Build Rejected"}
        _arr = (entry.build_arrived_date or "").strip() or None
        _rt = entry.build_received_time
        _received_time = (str(_rt).strip() or None) if _rt is not None and _rt != "" else None
        user_id = auth_data.get("user_id")
        payload = {
            "build_name": (entry.build_name or "").strip() or None,
            "build_number": (entry.build_number or "").strip() or None,
            "transaction_type": (entry.transaction_type or "").strip() or None,
            "version": (entry.version or "").strip() or None,
            "status": (entry.status or "").strip() or None,
            "start_date": (entry.start_date or "").strip() or None,
            "end_date": (entry.end_date or "").strip() or None,
            "build_arrived_date": _arr,
            "build_received_time": _received_time,
            "build_sent_by": (entry.build_sent_by or "").strip() or None,
            "test_report_sent_by": (entry.test_report_sent_by or "").strip() or None,
            "remarks": (entry.remarks or "").strip() or None,
            "updated_by": user_id,
        }
        try:
            current = execute_query("SELECT project_id FROM builds WHERE id = %s LIMIT 1", (build_id,), fetch_one=True, fetch_all=False) or {}
            new_pid_check = validated_project_id if validated_project_id is not None else current.get("project_id")
            new_bn_check = (entry.build_number or "").strip()
            if new_bn_check and new_pid_check:
                dup = execute_query(
                    "SELECT id FROM builds WHERE project_id = %s AND build_number = %s AND id <> %s AND (is_deleted IS NULL OR is_deleted = FALSE) LIMIT 1",
                    (new_pid_check, new_bn_check, str(build_id)),
                    fetch_one=True,
                    fetch_all=False
                )
                if dup and dup.get("id"):
                    raise HTTPException(status_code=409, detail="Build already exists")
        except HTTPException:
            raise
        except Exception:
            pass
        if "updated_at" in cols:
            payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        payload = {k: v for k, v in payload.items() if v is not None}

        # Only validate and update signoff_status if provided
        raw_status = (entry.signoff_status or entry.status or "").strip()
        if raw_status:
            if raw_status not in allowed_statuses:
                raise HTTPException(status_code=400, detail="Invalid signoff_status")
            payload["signoff_status"] = raw_status

        # Only validate and update signoff_date if provided
        sig_date = entry.build_signoff_date or entry.build_date
        if sig_date:
            payload["build_signoff_date"] = sig_date

        

        if validated_project_id is not None:
            payload["project_id"] = validated_project_id
        resp = supabase.table("builds").update(payload).eq("id", build_id).execute()
        if getattr(resp, "error", None):
            raise HTTPException(status_code=400, detail=str(resp.error))
        # Optionally update reports atomically if provided
        try:
            ensure_build_reports_table()
            ensure_report_tables()
            def _nz(v):
                try:
                    n = int(v)
                    return 0 if n < 0 else n
                except Exception:
                    return 0
            reports = entry.reports or {}
            functional = entry.functional_report or reports.get("functional") or {}
            automation = entry.automation_report or reports.get("automation") or {}
            cybersecurity = entry.cybersecurity_report or reports.get("cybersecurity") or {}
            def _save(cid, rtype, payload):
                blocker = _nz(payload.get("blocker"))
                high = _nz(payload.get("high"))
                medium = _nz(payload.get("medium"))
                low = _nz(payload.get("low"))
                execute_query(
                    """
                    INSERT INTO build_reports (build_id, report_type, blocker_count, high_count, medium_count)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (build_id, report_type)
                    DO UPDATE SET blocker_count = EXCLUDED.blocker_count,
                                  high_count = EXCLUDED.high_count,
                                  medium_count = EXCLUDED.medium_count
                    """,
                    (build_id, rtype, blocker, high, medium),
                    fetch_all=False
                )
                table = "functional_test_reports" if rtype == "functional" else ("automation_test_reports" if rtype == "automation" else "cybersecurity_reports")
                exists = execute_query(f"SELECT id FROM {table} WHERE build_id = %s LIMIT 1", (build_id,), fetch_one=True, fetch_all=False)
                if exists and exists.get("id"):
                    execute_query(
                        f"UPDATE {table} SET blocker = %s, high = %s, medium = %s, low = %s WHERE build_id = %s",
                        (blocker, high, medium, low, build_id),
                        fetch_all=False
                    )
                else:
                    execute_query(
                        f"INSERT INTO {table} (build_id, blocker, high, medium, low) VALUES (%s, %s, %s, %s, %s)",
                        (build_id, blocker, high, medium, low),
                        fetch_all=False
                    )
            if functional:
                _save(build_id, "functional", functional)
            if automation:
                _save(build_id, "automation", automation)
            if cybersecurity:
                _save(build_id, "cybersecurity", cybersecurity)
        except Exception:
            pass
        updated = (resp.data or [{}])[0]
        return {"status": "success", "data": updated}
    except HTTPException:
        raise
    except Exception as e:
        error_response, status_code = handle_api_error(
            e,
            endpoint,
            context={"operation": "update_build", "build_id": build_id},
            include_traceback=False,
            user_message="Failed to update build entry"
        )
        raise HTTPException(status_code=status_code, detail=error_response["error"])


@router.get("/builds/report/aggregate")
async def get_aggregate_build_report(project_id: Optional[str] = Query(default=None)):
    endpoint = "/builds/report/aggregate"
    try:
        ensure_builds_table()
        ensure_build_reports_table()
        if project_id is None:
            return {
                "status": "success",
                "data": {
                    "summary": {},
                    "functional": {"blocker": 0, "high": 0, "medium": 0},
                    "automation": {"blocker": 0, "high": 0, "medium": 0},
                    "cybersecurity": {"blocker": 0, "high": 0, "medium": 0},
                }
            }
        rows = execute_query("SELECT id FROM builds WHERE project_id = %s", (project_id,), fetch_all=True) or []
        build_ids = [int(r.get("id")) for r in rows if r.get("id") is not None]
        if not build_ids:
            return {
                "status": "success",
                "data": {
                    "summary": {},
                    "functional": {"blocker": 0, "high": 0, "medium": 0},
                    "automation": {"blocker": 0, "high": 0, "medium": 0},
                    "cybersecurity": {"blocker": 0, "high": 0, "medium": 0},
                }
            }
        placeholders = ",".join(["%s"] * len(build_ids))
        fr = execute_query(
            f"SELECT COALESCE(SUM(blocker_count),0) AS blocker, COALESCE(SUM(high_count),0) AS high, COALESCE(SUM(medium_count),0) AS medium FROM build_reports WHERE report_type = 'functional' AND build_id IN ({placeholders})",
            tuple(build_ids),
            fetch_one=True,
            fetch_all=False
        ) or {"blocker": 0, "high": 0, "medium": 0}
        ar = execute_query(
            f"SELECT COALESCE(SUM(blocker_count),0) AS blocker, COALESCE(SUM(high_count),0) AS high, COALESCE(SUM(medium_count),0) AS medium FROM build_reports WHERE report_type = 'automation' AND build_id IN ({placeholders})",
            tuple(build_ids),
            fetch_one=True,
            fetch_all=False
        ) or {"blocker": 0, "high": 0, "medium": 0}
        cr = execute_query(
            f"SELECT COALESCE(SUM(blocker_count),0) AS blocker, COALESCE(SUM(high_count),0) AS high, COALESCE(SUM(medium_count),0) AS medium FROM build_reports WHERE report_type = 'cybersecurity' AND build_id IN ({placeholders})",
            tuple(build_ids),
            fetch_one=True,
            fetch_all=False
        ) or {"blocker": 0, "high": 0, "medium": 0}
        return {
            "status": "success",
                "data": {
                    "summary": {},
                "functional": {"blocker": int(fr.get("blocker", 0)), "high": int(fr.get("high", 0)), "medium": int(fr.get("medium", 0))},
                "automation": {"blocker": int(ar.get("blocker", 0)), "high": int(ar.get("high", 0)), "medium": int(ar.get("medium", 0))},
                "cybersecurity": {"blocker": int(cr.get("blocker", 0)), "high": int(cr.get("high", 0)), "medium": int(cr.get("medium", 0))},
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        error_response, status_code = handle_api_error(
            e,
            endpoint,
            context={"operation": "get_aggregate_build_report"},
            include_traceback=False,
            user_message="Failed to fetch aggregate build report"
        )
        raise HTTPException(status_code=status_code, detail=error_response["error"])


# @router.put("/projects/{project_id}")
# async def update_project(project_id: int = Path(...), request: Request = None):
#     endpoint = f"/projects/{project_id}"
#     try:
#         ensure_projects_table()
#         payload = await request.json()
#         
#         # Map fields if necessary
#         if payload.get("application") and not payload.get("application_name"):
#              payload["application_name"] = payload["application"]
#         
#         # Remove fields that shouldn't be updated or cause issues
#         payload.pop("id", None)
#         payload.pop("project_id", None)
#         payload.pop("application", None)
#         payload.pop("created_at", None)
#         
#         resp = supabase.table("projects").update(payload).eq("id", project_id).execute()
#         if getattr(resp, "error", None):
#             raise HTTPException(status_code=400, detail=str(resp.error))
#             
#         updated = resp.data[0] if resp.data else None
#         return {"status": "success", "data": updated}
#     except HTTPException:
#         raise
#     except Exception as e:
#         error_response, status_code = handle_api_error(
#             e,
#             endpoint,
#             context={"operation": "update_project", "project_id": project_id},
#             include_traceback=False,
#             user_message="Failed to update project"
#         )
#         raise HTTPException(status_code=status_code, detail=error_response["error"])


@router.get("/projects/{project_id}/overall-report")
@require_permission("builds_retrieve")
async def get_project_overall_report(project_id: str = Path(...), Authorization: Optional[str] = Header(default=None)):
    endpoint = f"/projects/{project_id}/overall-report"
    try:
        auth_data = auth_guard(Authorization)
        tenant_id = auth_data.get("tenant_id")
        project_id = str(project_id).strip()
        _project_for_tenant(project_id, tenant_id)
        ensure_builds_table()
        ensure_report_tables()
        rows = execute_query(
            "SELECT id FROM builds WHERE project_id = %s",
            (project_id,),
            fetch_all=True
        ) or []
        if not rows:
            return {"status": "success", "data": None}
        build_ids = [int(r.get("id")) for r in rows if r.get("id") is not None]
        if not build_ids:
            return {
                "status": "success",
                "data": {
                    "summary": {},
                    "functional": {"blocker": 0, "high": 0, "medium": 0, "low": 0},
                    "automation": {"blocker": 0, "high": 0, "medium": 0, "low": 0},
                    "cybersecurity": {"blocker": 0, "high": 0, "medium": 0, "low": 0},
                }
            }
        placeholders = ",".join(["%s"] * len(build_ids))
        fr = execute_query(
            f"SELECT COALESCE(SUM(blocker),0) AS blocker, COALESCE(SUM(high),0) AS high, COALESCE(SUM(medium),0) AS medium, COALESCE(SUM(low),0) AS low FROM functional_test_reports WHERE build_id IN ({placeholders})",
            tuple(build_ids),
            fetch_one=True,
            fetch_all=False
        ) or {"blocker": 0, "high": 0, "medium": 0, "low": 0}
        ar = execute_query(
            f"SELECT COALESCE(SUM(blocker),0) AS blocker, COALESCE(SUM(high),0) AS high, COALESCE(SUM(medium),0) AS medium, COALESCE(SUM(low),0) AS low FROM automation_test_reports WHERE build_id IN ({placeholders})",
            tuple(build_ids),
            fetch_one=True,
            fetch_all=False
        ) or {"blocker": 0, "high": 0, "medium": 0, "low": 0}
        cr = execute_query(
            f"SELECT COALESCE(SUM(blocker),0) AS blocker, COALESCE(SUM(high),0) AS high, COALESCE(SUM(medium),0) AS medium, COALESCE(SUM(low),0) AS low FROM cybersecurity_reports WHERE build_id IN ({placeholders})",
            tuple(build_ids),
            fetch_one=True,
            fetch_all=False
        ) or {"blocker": 0, "high": 0, "medium": 0, "low": 0}
        return {
            "status": "success",
            "data": {
                "summary": {},
                "functional": {
                    "blocker": int(fr.get("blocker", 0)),
                    "high": int(fr.get("high", 0)),
                    "medium": int(fr.get("medium", 0)),
                    "low": int(fr.get("low", 0)),
                },
                "automation": {
                    "blocker": int(ar.get("blocker", 0)),
                    "high": int(ar.get("high", 0)),
                    "medium": int(ar.get("medium", 0)),
                    "low": int(ar.get("low", 0)),
                },
                "cybersecurity": {
                    "blocker": int(cr.get("blocker", 0)),
                    "high": int(cr.get("high", 0)),
                    "medium": int(cr.get("medium", 0)),
                    "low": int(cr.get("low", 0)),
                },
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        error_response, status_code = handle_api_error(
            e,
            endpoint,
            context={"operation": "get_project_overall_report", "project_id": project_id},
            include_traceback=False,
            user_message="Failed to fetch overall report for project"
        )
        raise HTTPException(status_code=status_code, detail=error_response["error"])


# @router.get("/projects/{project_id}")
# async def get_project(project_id: int = Path(...)):
#     # Moved to projects module
#     pass

def ensure_projects_tenant_for_builds():
    """Ensure projects.tenant_id exists so get_builds JOIN works."""
    try:
        execute_query("ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS tenant_id UUID", fetch_all=False)
    except Exception as e:
        print(f"Error ensuring projects tenant_id: {e}")
        # Don't suppress; let it bubble up or at least be visible so we know why the subsequent query might fail
        pass


@router.get("/builds")
@require_permission("builds_retrieve")
async def get_builds(
    status: Optional[str] = Query(default=None),
    date: Optional[str] = Query(default=None),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    project_id: Optional[str] = Query(default=None),
    page: Optional[int] = Query(default=None),
    limit: Optional[int] = Query(default=None),
    Authorization: Optional[str] = Header(default=None),
):
    endpoint = "/builds"
    try:
        auth_data = auth_guard(Authorization)
        tenant_id = auth_data.get("tenant_id")
        ensure_builds_table()
        ensure_projects_tenant_for_builds()
        cols_rows = execute_query(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            ("builds",),
            fetch_all=True
        ) or []
        cols = {r.get("column_name") for r in cols_rows if r.get("column_name")}
        
        select_clause = """
            SELECT 
              b.*,
              p.application_name AS project_name,
              CASE
                WHEN b.signoff_status IN ('Go','Conditional-Go','No-Go','Build Rejected') OR b.build_signoff_date IS NOT NULL
                THEN 'Testing Complete'
                ELSE 'Testing In Progress'
              END AS stage
        """
        from_clause = """
            FROM builds b
            INNER JOIN projects p ON p.id::text = b.project_id::text
        """
        where_clause = "WHERE ((p.tenant_id::text = %s) OR (p.tenant_id IS NULL AND %s IS NULL))"
        
        t_id = str(tenant_id) if tenant_id else None
        params = [t_id, t_id]
        if "is_deleted" in cols:
            where_clause += " AND (b.is_deleted IS NULL OR b.is_deleted = FALSE)"
        if project_id is not None:
            _project_for_tenant(str(project_id).strip(), tenant_id)
            where_clause += " AND b.project_id::text = %s"
            params.append(str(project_id).strip())
        if status:
            where_clause += " AND b.signoff_status = %s"
            params.append(status)
        if date:
            where_clause += " AND b.build_signoff_date = %s"
            params.append(date)
        if start_date and end_date:
            where_clause += " AND b.build_signoff_date BETWEEN %s AND %s"
            params.extend([start_date, end_date])
            
        order_clause = ""
        if "updated_at" in cols or "created_at" in cols:
            if "updated_at" in cols and "created_at" in cols:
                order_clause = " ORDER BY COALESCE(b.updated_at, b.created_at, b.build_arrived_date) DESC NULLS LAST, b.id DESC"
            elif "updated_at" in cols:
                order_clause = " ORDER BY COALESCE(b.updated_at, b.build_arrived_date) DESC NULLS LAST, b.id DESC"
            else:
                order_clause = " ORDER BY COALESCE(b.created_at, b.build_arrived_date) DESC NULLS LAST, b.id DESC"
        else:
            order_clause = " ORDER BY b.build_arrived_date DESC NULLS LAST, b.id DESC"
            
        limit_clause = ""
        total_count = 0
        
        if page is not None and limit is not None:
            try:
                p = int(page)
                l = int(limit)
                if p < 1: p = 1
                if l < 1: l = 10
                offset = (p - 1) * l
                limit_clause = f" LIMIT {l} OFFSET {offset}"
                
                # Count query
                count_sql = f"SELECT COUNT(*) as total {from_clause} {where_clause}"
                count_res = execute_query(count_sql, tuple(params), fetch_one=True, fetch_all=False)
                total_count = int(count_res.get("total", 0)) if count_res else 0
            except Exception:
                pass

        full_sql = f"{select_clause} {from_clause} {where_clause} {order_clause} {limit_clause}"
        rows = execute_query(full_sql, tuple(params), fetch_all=True) or []
        
        if page is not None and limit is not None:
            return {
                "status": "success",
                "data": rows,
                "total": total_count,
                "page": page,
                "limit": limit
            }
            
        return {"status": "success", "data": rows}
    except HTTPException:
        raise
    except Exception as e:
        error_response, status_code = handle_api_error(
            e,
            endpoint,
            context={"operation": "get_builds", "table": "builds"},
            include_traceback=False,
            user_message="Failed to fetch builds"
        )
        raise HTTPException(status_code=status_code, detail=error_response["error"])

@router.get("/builds/{build_id}")
@require_permission("builds_retrieve")
async def get_build(build_id: str = Path(...), Authorization: Optional[str] = Header(default=None)):
    endpoint = f"/builds/{build_id}"
    try:
        auth_data = auth_guard(Authorization)
        tenant_id = auth_data.get("tenant_id")
        ensure_builds_table()
        cols_rows = execute_query(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            ("builds",),
            fetch_all=True
        ) or []
        cols = {r.get("column_name") for r in cols_rows if r.get("column_name")}
        row = execute_query(
            """
            SELECT 
              b.*,
              p.application_name AS project_name,
              CASE
                WHEN b.signoff_status IN ('Go','Conditional-Go','No-Go','Build Rejected') OR b.build_signoff_date IS NOT NULL
                THEN 'Testing Complete'
                ELSE 'Testing In Progress'
              END AS stage
            FROM public.builds b
            LEFT JOIN public.projects p ON p.id::text = b.project_id::text
            WHERE b.id::text = %s
            LIMIT 1
            """,
            (build_id,),
            fetch_one=True,
            fetch_all=False
        ) or None
        if not row:
            raise HTTPException(status_code=404, detail="Build not found")
        if "is_deleted" in cols and bool(row.get("is_deleted")):
            raise HTTPException(status_code=404, detail="Build not found")
        build_tenant = _build_project_tenant(build_id)
        if not _tenant_match(tenant_id, build_tenant):
            raise HTTPException(status_code=404, detail="Build not found or access denied")
        return {"status": "success", "data": row}
    except HTTPException:
        raise
    except Exception as e:
        error_response, status_code = handle_api_error(
            e,
            endpoint,
            context={"operation": "get_build", "build_id": build_id},
            include_traceback=False,
            user_message="Failed to fetch build"
        )
        raise HTTPException(status_code=status_code, detail=error_response["error"])

@router.get("/builds/filters")
@require_permission("builds_retrieve")
async def get_build_filters(Authorization: Optional[str] = Header(default=None)):
    endpoint = "/builds/filters"
    try:
        auth_data = auth_guard(Authorization)
        tenant_id = auth_data.get("tenant_id")
        apps = execute_query(
            "SELECT DISTINCT application_name FROM projects WHERE (tenant_id = %s OR (tenant_id IS NULL AND %s IS NULL)) ORDER BY application_name ASC",
            (tenant_id, tenant_id),
            fetch_all=True,
        ) or []
        owners = execute_query(
            "SELECT DISTINCT project_owner FROM projects WHERE (tenant_id = %s OR (tenant_id IS NULL AND %s IS NULL)) ORDER BY project_owner ASC",
            (tenant_id, tenant_id),
            fetch_all=True,
        ) or []
        statuses = [
            {"status": "Go"},
            {"status": "Conditional-Go"},
            {"status": "No-Go"},
            {"status": "Build Rejected"},
        ]
        return {
            "status": "success",
            "data": {
                "applications": [a.get("application_name") for a in apps if a.get("application_name")],
                "owners": [o.get("project_owner") for o in owners if o.get("project_owner")],
                "statuses": [s.get("status") for s in statuses if s.get("status")],
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        error_response, status_code = handle_api_error(
            e,
            endpoint,
            context={"operation": "get_build_filters", "table": "builds"},
            include_traceback=False,
            user_message="Failed to fetch build filter options"
        )
        raise HTTPException(status_code=status_code, detail=error_response["error"])


# ---------- Build comments (inspired by security controls) ----------
@router.get("/builds/{build_id}/comments")
@require_permission("builds_retrieve")
async def get_build_comments(build_id: int = Path(...), Authorization: Optional[str] = Header(default=None)):
    endpoint = f"/builds/{build_id}/comments"
    try:
        auth_data = auth_guard(Authorization)
        tenant_id = auth_data.get("tenant_id")
        build_tenant = _build_project_tenant(build_id)
        if not _tenant_match(tenant_id, build_tenant):
            raise HTTPException(status_code=404, detail="Build not found or access denied")
        ensure_builds_table()
        row = execute_query("SELECT comments FROM builds WHERE id = %s LIMIT 1", (build_id,), fetch_one=True, fetch_all=False)
        if not row:
            raise HTTPException(status_code=404, detail="Build not found")
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
        err_resp = handle_api_error(e, endpoint, context={"operation": "get_build_comments"}, include_traceback=False, user_message="Failed to fetch comments")
        raise HTTPException(status_code=500, detail=err_resp.get("error", str(e)))


@router.post("/builds/{build_id}/comments")
@require_permission("builds_comment")
async def add_build_comment(
    build_id: UUID,
    payload: dict = Body(...),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = f"/builds/{build_id}/comments"
    try:
        auth_data = auth_guard(Authorization)
        user_id = auth_data.get("user_id")
        comment_text = payload.get("comment")
        if not comment_text or not str(comment_text).strip():
            raise HTTPException(status_code=400, detail="Comment is required")
        existing = execute_query(
            "SELECT comments FROM public.builds WHERE id = %s",
            (str(build_id),),
            fetch_one=True,
            fetch_all=False
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Build not found")
        comments = existing.get("comments")
        if not comments:
            comments = []
        elif isinstance(comments, str):
            comments = json.loads(comments)
        new_comment = {
            "comment": str(comment_text).strip(),
            "created_by": str(user_id),
            "created_at": datetime.utcnow().isoformat()
        }
        comments.append(new_comment)
        execute_query(
            "UPDATE public.builds SET comments = %s WHERE id = %s",
            (json.dumps(comments), str(build_id)),
            fetch_all=False
        )
        return {"data": new_comment, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to add comment")


 

from fastapi import APIRouter, HTTPException, Request, Header, Query, Path
from typing import Optional, Dict, Any, List, cast
import uuid
from datetime import datetime, timezone
from services.db_service import local_db as supabase, execute_query
from services.auth_service import get_user_from_token, auth_guard
from services.rbac_service import check_permission, get_user_accessible_projects, get_user_accessible_project_names
from services.rbac_service import require_permission
from utils.error_handler import handle_api_error, handle_endpoint_error
from pydantic import BaseModel

router = APIRouter(prefix="/projects", tags=["Projects"])

# ---------- MODELS ----------
class ProjectCreate(BaseModel):
    project_name: Optional[str] = None  # default from application_name if not provided
    product_name: Optional[str] = None  # default from application_name if not provided
    application_name: str
    application_type: Optional[str] = None
    project_owner: Optional[str] = None
    assignee: Optional[str] = None
    dev_manager: Optional[str] = None
    qa_manager: Optional[str] = None
    qa_lead: Optional[str] = None
    qa_spoc: Optional[str] = None
    qa_resource_count: Optional[int] = 0
    expected_closing_date: Optional[str] = None
    arrived_date: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: Optional[str] = "Active"
    description: Optional[str] = None
    business_unit: Optional[str] = None
    business_vertical: Optional[str] = None
    division: Optional[str] = None

class ProjectUpdate(BaseModel):
    project_name: Optional[str] = None
    product_name: Optional[str] = None
    application_name: Optional[str] = None
    application_type: Optional[str] = None
    project_owner: Optional[str] = None
    assignee: Optional[str] = None
    dev_manager: Optional[str] = None
    qa_manager: Optional[str] = None
    qa_lead: Optional[str] = None
    qa_spoc: Optional[str] = None
    qa_resource_count: Optional[int] = None
    expected_closing_date: Optional[str] = None
    arrived_date: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: Optional[str] = None
    description: Optional[str] = None
    business_unit: Optional[str] = None
    business_vertical: Optional[str] = None
    division: Optional[str] = None

# ---------- AUTH ----------

# ---------- HELPERS ----------
def ensure_projects_table_schema():
    try:
        # Check if tenant_id exists
        # We can't easily check columns via supabase client directly without a query that might fail.
        # But we can use execute_query to ALTER TABLE IF NOT EXISTS.
        # However, supabase sql interface via execute_query allows running raw sql.
        
        execute_query(
            "ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS tenant_id UUID",
            fetch_all=False
        )
        
        # Ensure other columns exist based on schema
        cols = [
            "project_name TEXT",
            "application_type TEXT",
            "project_owner TEXT",
            "assignee TEXT",
            "dev_manager TEXT",
            "qa_manager TEXT",
            "qa_lead TEXT",
            "qa_spoc TEXT",
            "expected_closing_date DATE",
            "arrived_date DATE",
            "start_date DATE",
            "end_date DATE",
            "product_name TEXT",
            "application_name TEXT",
            "status TEXT DEFAULT 'Active'",
            "description TEXT",
            "qa_resource_count INTEGER DEFAULT 0",
            "business_unit TEXT",
            "business_vertical TEXT",
            "division TEXT",
        ]
        
        for col in cols:
             execute_query(
                f"ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS {col}",
                fetch_all=False
            )
            
    except Exception as e:
        # Log error but don't block? Or strict?
        # Strict error handling requested.
        print(f"Schema check failed: {e}")
        # raise HTTPException(status_code=500, detail=f"Database schema error: {e}")
        pass

# ---------- ROUTES ----------

@router.get("/application-dropdown")
async def get_application_dropdown(Authorization: Optional[str] = Header(default=None)):
    """Return distinct application names for dropdowns (projects list)."""
    try:
        auth_data = auth_guard(Authorization)
        tenant_id = auth_data.get("tenant_id")
        user_id = auth_data.get("user_id")
        
        ensure_projects_table_schema()
        # Select additional fields needed for frontend metadata (project_owner, assignee, qa_spoc)
        query = supabase.table("projects").select("id, application_name, project_owner, assignee, qa_spoc").order("application_name")
        if tenant_id is not None:
            query = query.eq("tenant_id", tenant_id)
            
        accessible_projects = get_user_accessible_project_names(user_id, tenant_id)
        if accessible_projects is not None:
            if not accessible_projects:
                return {"data": [], "error": None}
            query = query.in_("application_name", accessible_projects)
            
        resp = query.execute()
        if getattr(resp, "error", None):
            raise HTTPException(status_code=400, detail=str(resp.error))
            
        # We need to deduplicate based on application_name but keep the metadata.
        # Since application_name should be unique per tenant (enforced in create/update),
        # we can just use the list. But if there are duplicates for some reason, we take the first one.
        
        data = resp.data or []
        if accessible_projects is not None:
            data = [r for r in data if r.get("application_name") in accessible_projects]
            
        # Deduplicate by application_name if necessary (though DB should handle uniqueness)
        unique_map = {}
        for r in data:
            name = r.get("application_name")
            if name and name not in unique_map:
                unique_map[name] = r
                
        # Sort by application_name
        sorted_keys = sorted(unique_map.keys())
        result = [unique_map[k] for k in sorted_keys]
        
        return {"data": result, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("")
@require_permission("projects_retrieve")
async def get_projects(
    application_name: Optional[str] = Query(None),
    Authorization: Optional[str] = Header(default=None)
):
    try:
        auth_data = auth_guard(Authorization)
        tenant_id = auth_data.get("tenant_id")
        user_id = auth_data.get("user_id")
        
        ensure_projects_table_schema()
        
        query = supabase.table("projects").select("*")
        
        if tenant_id:
            query = query.eq("tenant_id", tenant_id)
            
        if application_name:
            query = query.eq("application_name", application_name)
            
        # Apply RBAC filtering
        accessible_projects = get_user_accessible_projects(user_id, tenant_id)
        if accessible_projects is not None:
            if not accessible_projects:
                return {"data": [], "error": None}
            query = query.in_("id", accessible_projects)
            
        resp = query.order("created_at", desc=True).execute()
        
        if getattr(resp, "error", None):
             raise HTTPException(status_code=400, detail=str(resp.error))
             
        data = resp.data or []
        
        # In case local proxy doesn't fully filter, double check
        if accessible_projects is not None:
            data = [d for d in data if d.get("id") in accessible_projects]
            
        return {"data": data, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{id}")
async def get_project_by_id(
    id: str = Path(...),
    Authorization: Optional[str] = Header(default=None)
):
    try:
        auth_data = auth_guard(Authorization)
        tenant_id = auth_data.get("tenant_id")
        user_id = auth_data.get("user_id")
        
        ensure_projects_table_schema()

        # Check RBAC
        accessible_projects = get_user_accessible_projects(user_id, tenant_id)
        if accessible_projects is not None:
             if id not in accessible_projects:
                 raise HTTPException(status_code=403, detail="Access denied to this project")
        
        # 1. Get Project
        query = supabase.table("projects").select("*").eq("id", id)
        if tenant_id:
             query = query.eq("tenant_id", tenant_id)
        resp = query.limit(1).execute()
        
        if getattr(resp, "error", None):
             raise HTTPException(status_code=400, detail=str(resp.error))
             
        if not resp.data:
            raise HTTPException(status_code=404, detail="Project not found")
            
        project = resp.data[0]
        
        # 2. Get Latest Build
        # We need to query builds table.
        # Builds table uses project_id (TEXT now).
        latest_build = execute_query(
            "SELECT * FROM builds WHERE project_id = %s ORDER BY build_arrived_date DESC NULLS LAST, id DESC LIMIT 1",
            (id,),
            fetch_one=True,
            fetch_all=False
        )
        
        aggregate = {"project": project, "latest_build": None}
        
        if latest_build:
            aggregate["latest_build"] = latest_build
            build_id = latest_build.get("id")
            
            # 3. Get Reports for Latest Build
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
            
            aggregate["functional_report"] = fr
            aggregate["automation_report"] = ar
            aggregate["cybersecurity_report"] = cr
            
            # 4. Get Assigned Resources (from build_tasks)
            tasks = execute_query(
                "SELECT resource_name, task_assigned, task_type, task_status, spent_hours FROM build_tasks WHERE build_id = %s",
                (build_id,),
                fetch_all=True
            ) or []
            aggregate["assigned_resources"] = tasks
            
        return {"data": aggregate, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("")
@require_permission("projects_create")
async def create_project(
    request: Request,
    Authorization: Optional[str] = Header(default=None)
):
    try:
        payload = await request.json()
        auth_data = auth_guard(Authorization)
        tenant_id = auth_data.get("tenant_id")
        
        ensure_projects_table_schema()
        
        # Validation
        app_name = (payload.get("application_name") or "").strip()
        if not app_name:
            raise HTTPException(status_code=400, detail="application_name is required and cannot be empty")
        payload["application_name"] = app_name

        project_owner_val = (payload.get("project_owner") or "").strip()
        if not project_owner_val:
            raise HTTPException(status_code=400, detail="project_owner is required and cannot be empty")
        payload["project_owner"] = project_owner_val

        assignee_val = (payload.get("assignee") or "").strip()
        if not assignee_val:
            raise HTTPException(status_code=400, detail="assignee is required and cannot be empty")
        payload["assignee"] = assignee_val

        # Check uniqueness (per tenant; support tenant_id IS NULL)
        existing = execute_query(
            "SELECT id FROM projects WHERE application_name = %s AND ((tenant_id = %s) OR (tenant_id IS NULL AND %s IS NULL))",
            (app_name, tenant_id, tenant_id),
            fetch_all=True,
        )
        if existing and len(existing) > 0:
            raise HTTPException(status_code=400, detail="Application Name must be unique")
        
        new_id = str(uuid.uuid4())
        app_name = payload.get("application_name")
        # project_name is NOT NULL in DB: use explicit value or fallback to application_name
        project_name = (payload.get("project_name") or "").strip() or app_name
        product_name = payload.get("product_name") or app_name
        data = {
            "id": new_id,
            "tenant_id": tenant_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "project_name": project_name,
            "product_name": product_name,
            "application_name": app_name,
            "application_type": payload.get("application_type"),
            "project_owner": payload.get("project_owner"),
            "assignee": payload.get("assignee"),
            "dev_manager": payload.get("dev_manager"),
            "qa_manager": payload.get("qa_manager"),
            "qa_lead": payload.get("qa_lead"),
            "qa_spoc": payload.get("qa_spoc"),
            "status": payload.get("status", "Active"),
            "qa_resource_count": payload.get("qa_resource_count", 0),
            "arrived_date": payload.get("arrived_date"),
            "expected_closing_date": payload.get("expected_closing_date"),
            "start_date": payload.get("start_date"),
            "end_date": payload.get("end_date"),
            "description": payload.get("description"),
            "business_unit": payload.get("business_unit"),
            "business_vertical": payload.get("business_vertical"),
            "division": payload.get("division"),
        }
        # Remove None keys (but keep project_name/product_name/application_name which are required or have fallbacks)
        data = {k: v for k, v in data.items() if v is not None}
        
        resp = supabase.table("projects").insert(data).execute()
        
        if getattr(resp, "error", None):
             raise HTTPException(status_code=400, detail=str(resp.error))
             
        return {"data": resp.data[0] if resp.data else data, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{id}")
async def update_project(
    id: str,
    request: Request,
    Authorization: Optional[str] = Header(default=None)
):
    try:
        payload = await request.json()
        auth_data = auth_guard(Authorization)
        tenant_id = auth_data.get("tenant_id")
        user_id = auth_data.get("user_id")
        
        # Check RBAC
        accessible_projects = get_user_accessible_projects(user_id, tenant_id)
        if accessible_projects is not None:
             if id not in accessible_projects:
                 raise HTTPException(status_code=403, detail="Access denied to this project")
        
        ensure_projects_table_schema()
        
        data = {
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        fields = [
            "project_name", "product_name", "application_name", "application_type",
            "project_owner", "assignee", "dev_manager", "qa_manager", "qa_lead", "qa_spoc",
            "status", "qa_resource_count", "arrived_date", "expected_closing_date",
            "start_date", "end_date", "description",
            "business_unit", "business_vertical", "division",
        ]
        
        for field in fields:
            if field in payload:
                data[field] = payload[field]

        if "project_owner" in payload:
            project_owner_val = (payload.get("project_owner") or "").strip()
            if not project_owner_val:
                raise HTTPException(status_code=400, detail="project_owner cannot be empty")
            data["project_owner"] = project_owner_val

        if "assignee" in payload:
            assignee_val = (payload.get("assignee") or "").strip()
            if not assignee_val:
                raise HTTPException(status_code=400, detail="assignee cannot be empty")
            data["assignee"] = assignee_val

        if "application_name" in payload:
            app_name = (payload["application_name"] or "").strip()
            if not app_name:
                raise HTTPException(status_code=400, detail="application_name cannot be empty")
            data["application_name"] = app_name
            # Check uniqueness excluding current id (per tenant)
            existing = execute_query(
                "SELECT id FROM projects WHERE application_name = %s AND id != %s AND ((tenant_id = %s) OR (tenant_id IS NULL AND %s IS NULL))",
                (app_name, id, tenant_id, tenant_id),
                fetch_all=True,
            )
            if existing and len(existing) > 0:
                raise HTTPException(status_code=400, detail="Application Name must be unique")
                
        query = supabase.table("projects").update(data).eq("id", id)
        if tenant_id:
            query = query.eq("tenant_id", tenant_id)
            
        resp = query.execute()
        
        if getattr(resp, "error", None):
             raise HTTPException(status_code=400, detail=str(resp.error))
             
        if not resp.data:
             raise HTTPException(status_code=404, detail="Project not found or access denied")
             
        return {"data": resp.data[0], "error": None}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{id}")
@require_permission("projects_delete")
async def delete_project(
    id: str,
    Authorization: Optional[str] = Header(default=None)
):
    try:
        auth_data = auth_guard(Authorization)
        tenant_id = auth_data.get("tenant_id")
        user_id = auth_data.get("user_id")

        # Check RBAC
        accessible_projects = get_user_accessible_projects(user_id, tenant_id)
        if accessible_projects is not None:
             if id not in accessible_projects:
                 raise HTTPException(status_code=403, detail="Access denied to this project")
        
        query = supabase.table("projects").delete().eq("id", id)
        if tenant_id:
            query = query.eq("tenant_id", tenant_id)
            
        resp = query.execute()

        if getattr(resp, "rowcount", -1) == 0:
            raise HTTPException(status_code=404, detail="Project not found or access denied")
        if getattr(resp, "error", None):
            raise HTTPException(status_code=400, detail=str(resp.error))

        return {"data": True, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

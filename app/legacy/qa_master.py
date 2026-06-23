# REFERENCE_ONLY_MODULE — legacy Kaizen module; preserved for compatibility.
# ################ QA MASTER #################
from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from services.db_service import execute_query, insert_table, update_table, delete_table
from services.auth_service import get_user_from_token, auth_guard
from utils.error_handler import handle_endpoint_error
from services.rbac_service import require_permission

router = APIRouter()

DEFAULT_TENANT = '00000000-0000-0000-0000-000000000001'

# ---------- AUTH ----------


def now():
    return datetime.now(timezone.utc).isoformat()

# ---------- MODELS ----------

class SprintCreate(BaseModel):
    application_name: str
    sprint_name: str

class ComponentCreate(BaseModel):
    application_name: str
    component_name: str

class BuildNumberCreate(BaseModel):
    application_name: str
    project_id: str
    build_number: str

class SprintUpdate(BaseModel):
    sprint_name: Optional[str] = None

class ComponentUpdate(BaseModel):
    component_name: Optional[str] = None

# ---------- COMMON MASTER HELPERS ----------

def ensure_masters_project_id_column():
    try:
        execute_query("ALTER TABLE public.masters ADD COLUMN IF NOT EXISTS project_id TEXT", fetch_all=False)
    except Exception:
        pass

def map_name(row, key):
    row[key] = row.get("name")
    return row

def fetch_masters(app, mtype, key, tenant_id):
    query = 'SELECT * FROM "masters" WHERE "application_name" = %s AND "type" = %s AND "tenant_id" = %s ORDER BY "created_at" DESC'
    data = execute_query(query, (app, mtype, tenant_id), fetch_all=True)
    return [map_name(i, key) for i in (data or [])]

def create_master(app, mtype, name, tenant_id):
    data = insert_table("masters", {
        "application_name": app,
        "type": mtype,
        "name": name,
        "tenant_id": tenant_id
    })
    return map_name(data, f"{mtype}_name") if data else None

def update_master(id, mtype, name, tenant_id):
    data = update_table("masters", {
        "name": name,
        "updated_at": now()
    }, {"id": id, "type": mtype, "tenant_id": tenant_id})
    return map_name(data, f"{mtype}_name") if data else None

def delete_master(id, mtype, tenant_id):
    delete_table("masters", {"id": id, "type": mtype, "tenant_id": tenant_id})

# ===========================
# SPRINT APIs
# ===========================

@router.get("/sprints")
@require_permission("masters_retrieve")
async def get_sprints(application_name: str = Query(...), Authorization: str = Header(None)):
    try:
        user = auth_guard(Authorization)
        tenant_id = user.get("tenant_id") or DEFAULT_TENANT
        return {"data": fetch_masters(application_name, "sprint", "sprint_name", tenant_id), "error": None}
    except Exception as e:
        return handle_endpoint_error(e, "/sprints", "get_sprints", True)

@router.post("/sprints")
@require_permission("masters_create")
async def create_sprint(payload: SprintCreate, Authorization: str = Header(None)):
    try:
        user = auth_guard(Authorization)
        tenant_id = user.get("tenant_id") or DEFAULT_TENANT
        return {"data": create_master(payload.application_name, "sprint", payload.sprint_name, tenant_id), "error": None}
    except Exception as e:
        return handle_endpoint_error(e, "/sprints", "create_sprint", True)

@router.put("/sprints/{id}")
@require_permission("masters_update")
async def update_sprint(id: str, payload: SprintUpdate, Authorization: str = Header(None)):
    try:
        user = auth_guard(Authorization)
        tenant_id = user.get("tenant_id") or DEFAULT_TENANT
        return {"data": update_master(id, "sprint", payload.sprint_name, tenant_id), "error": None}
    except Exception as e:
        return handle_endpoint_error(e, f"/sprints/{id}", "update_sprint", True)

@router.delete("/sprints/{id}")
@require_permission("masters_delete")
async def delete_sprint(id: str, Authorization: str = Header(None)):
    try:
        user = auth_guard(Authorization)
        tenant_id = user.get("tenant_id") or DEFAULT_TENANT
        delete_master(id, "sprint", tenant_id)
        return {"data": True, "error": None}
    except Exception as e:
        return handle_endpoint_error(e, f"/sprints/{id}", "delete_sprint", True)

# ===========================
# COMPONENT APIs
# ===========================

@router.get("/project-components")
@require_permission("masters_retrieve")
async def get_components(application_name: str = Query(...), Authorization: str = Header(None)):
    try:
        user = auth_guard(Authorization)
        tenant_id = user.get("tenant_id") or DEFAULT_TENANT
        return {"data": fetch_masters(application_name, "component", "component_name", tenant_id), "error": None}
    except Exception as e:
        return handle_endpoint_error(e, "/project-components", "get_components", True)

@router.post("/project-components")
@require_permission("masters_create")
async def create_component(payload: ComponentCreate, Authorization: str = Header(None)):
    try:
        user = auth_guard(Authorization)
        tenant_id = user.get("tenant_id") or DEFAULT_TENANT
        return {"data": create_master(payload.application_name, "component", payload.component_name, tenant_id), "error": None}
    except Exception as e:
        return handle_endpoint_error(e, "/project-components", "create_component", True)

@router.put("/project-components/{id}")
@require_permission("masters_update")
async def update_component(id: str, payload: ComponentUpdate, Authorization: str = Header(None)):
    try:
        user = auth_guard(Authorization)
        tenant_id = user.get("tenant_id") or DEFAULT_TENANT
        return {"data": update_master(id, "component", payload.component_name, tenant_id), "error": None}
    except Exception as e:
        return handle_endpoint_error(e, f"/project-components/{id}", "update_component", True)

@router.delete("/project-components/{id}")
@require_permission("masters_delete")
async def delete_component(id: str, Authorization: str = Header(None)):
    try:
        user = auth_guard(Authorization)
        tenant_id = user.get("tenant_id") or DEFAULT_TENANT
        delete_master(id, "component", tenant_id)
        return {"data": True, "error": None}
    except Exception as e:
        return handle_endpoint_error(e, f"/project-components/{id}", "delete_component", True)

# ===========================
# BUILD NUMBER APIs
# ===========================

@router.get("/build-numbers")
@require_permission("masters_retrieve")
async def get_build_numbers(
    application_name: Optional[str] = Query(default=None),
    project_id: Optional[str] = Query(default=None),
    Authorization: str = Header(None)
):
    try:
        user = auth_guard(Authorization)
        tenant_id = user.get("tenant_id") or DEFAULT_TENANT
        ensure_masters_project_id_column()
        query = 'SELECT * FROM "masters" WHERE "type" = %s AND "tenant_id" = %s'
        params = ["build_number", tenant_id]
        if application_name:
            query += ' AND "application_name" = %s'
            params.append(application_name)
        if project_id:
            query += ' AND "project_id" = %s'
            params.append(project_id)
        query += ' ORDER BY "created_at" DESC'
        data = execute_query(query, tuple(params), fetch_all=True)
        return {"data": [map_name(i, "build_number_name") for i in (data or [])], "error": None}
    except Exception as e:
        return handle_endpoint_error(e, "/build-numbers", "get_build_numbers", True)

@router.post("/build-numbers")
@require_permission("masters_create")
async def create_build_number(payload: BuildNumberCreate, Authorization: str = Header(None)):
    try:
        user = auth_guard(Authorization)
        tenant_id = user.get("tenant_id") or DEFAULT_TENANT
        ensure_masters_project_id_column()
        build_number = (payload.build_number or "").strip()
        project_id = (payload.project_id or "").strip()
        if not build_number:
            raise HTTPException(400, "build_number is required")
        if not project_id:
            raise HTTPException(400, "project_id is required")
        data = insert_table("masters", {
            "application_name": payload.application_name,
            "type": "build_number",
            "name": build_number,
            "tenant_id": tenant_id,
            "project_id": project_id
        })
        return {"data": map_name(data, "build_number_name") if data else None, "error": None}
    except Exception as e:
        return handle_endpoint_error(e, "/build-numbers", "create_build_number", True)

@router.delete("/build-numbers/{id}")
@require_permission("masters_delete")
async def delete_build_number(id: str, Authorization: str = Header(None)):
    try:
        user = auth_guard(Authorization)
        tenant_id = user.get("tenant_id") or DEFAULT_TENANT
        delete_master(id, "build_number", tenant_id)
        return {"data": True, "error": None}
    except Exception as e:
        return handle_endpoint_error(e, f"/build-numbers/{id}", "delete_build_number", True)

# ===========================
# BUILD SIGNOFF STATUS API
# ===========================

@router.get("/master/build-signoff-status")
@require_permission("masters_retrieve")
async def get_build_signoff_statuses(Authorization: str = Header(None)):
    try:
        user = auth_guard(Authorization)
        statuses = [
            {"id": 1, "code": "Go", "name": "Go"},
            {"id": 2, "code": "Conditional-Go", "name": "Conditional-Go"},
            {"id": 3, "code": "No-Go", "name": "No-Go"},
            {"id": 4, "code": "Build Rejected", "name": "Build Rejected"}
        ]
        return statuses
    except Exception as e:
        return handle_endpoint_error(e, "/master/build-signoff-status", "get_build_signoff_statuses", True)

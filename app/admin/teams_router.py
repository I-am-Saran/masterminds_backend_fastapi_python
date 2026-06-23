from fastapi import APIRouter, HTTPException, Request, Header
from typing import Optional, Dict, Any
import uuid
from datetime import datetime, timezone
from services.db_service import local_db as supabase, execute_query
from services.auth_service import get_user_from_token, auth_guard
from services.rbac_service import is_superadmin, is_global_superadmin
from services.rbac_service import require_permission

router = APIRouter()


def require_admin(user: Dict[str, Any], tenant_id: str):
    user_id = user.get("user_id") or user.get("id")
    if not (is_global_superadmin(user_id) or is_superadmin(user_id, tenant_id)):
        raise HTTPException(status_code=403, detail="Admin privileges required")

@router.get("")
@require_permission("teams_retrieve")
async def get_teams(Authorization: Optional[str] = Header(None)):
    user = auth_guard(Authorization)
    tenant_id = user.get("tenant_id") or "00000000-0000-0000-0000-000000000001"
    
    resp = supabase.table("teams").select("*").eq("tenant_id", tenant_id).order("created_at", desc=True).execute()
    return {"data": resp.data or [], "error": None}

@router.post("")
@require_permission("teams_create")
async def create_team(request: Request, Authorization: Optional[str] = Header(None)):
    user = auth_guard(Authorization)
    tenant_id = user.get("tenant_id") or "00000000-0000-0000-0000-000000000001"
    require_admin(user, tenant_id)
    
    payload = await request.json()
    name = payload.get("name")
    description = payload.get("description", "")
    
    if not name:
        raise HTTPException(status_code=400, detail="Team name is required")
        
    team_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    data = {
        "id": team_id,
        "name": name,
        "description": description,
        "tenant_id": tenant_id,
        "created_at": now,
        "updated_at": now
    }
    
    resp = supabase.table("teams").insert(data).execute()
    if getattr(resp, "error", None):
        raise HTTPException(status_code=500, detail=str(resp.error))
        
    return {"data": data, "error": None}

@router.put("/{team_id}")
@require_permission("teams_update")
async def update_team(team_id: str, request: Request, Authorization: Optional[str] = Header(None)):
    user = auth_guard(Authorization)
    tenant_id = user.get("tenant_id") or "00000000-0000-0000-0000-000000000001"
    require_admin(user, tenant_id)
    
    payload = await request.json()
    name = payload.get("name")
    description = payload.get("description")
    
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if name is not None:
        update_data["name"] = name
    if description is not None:
        update_data["description"] = description
        
    resp = supabase.table("teams").update(update_data).eq("id", team_id).eq("tenant_id", tenant_id).execute()
    if getattr(resp, "error", None):
        raise HTTPException(status_code=500, detail=str(resp.error))
        
    return {"data": resp.data[0] if resp.data else None, "error": None}

@router.delete("/{team_id}")
@require_permission("teams_delete")
async def delete_team(team_id: str, Authorization: Optional[str] = Header(None)):
    user = auth_guard(Authorization)
    tenant_id = user.get("tenant_id") or "00000000-0000-0000-0000-000000000001"
    require_admin(user, tenant_id)
    
    resp = supabase.table("teams").delete().eq("id", team_id).eq("tenant_id", tenant_id).execute()
    if getattr(resp, "error", None):
        raise HTTPException(status_code=500, detail=str(resp.error))
        
    return {"data": True, "error": None}

@router.get("/{team_id}/users")
@require_permission("teams_retrieve")
async def get_team_users(team_id: str, Authorization: Optional[str] = Header(None)):
    user = auth_guard(Authorization)
    tenant_id = user.get("tenant_id") or "00000000-0000-0000-0000-000000000001"
    
    query = '''
    SELECT tu.id as mapping_id, tu.user_id, u.full_name, u.email, u.department, u.role
    FROM team_users tu
    JOIN users u ON tu.user_id = u.id OR tu.user_id = u.email
    WHERE tu.team_id = %s AND tu.tenant_id = %s
    '''
    rows = execute_query(query, (team_id, tenant_id), fetch_all=True) or []
    return {"data": rows, "error": None}

@router.post("/{team_id}/users")
@require_permission("teams_update")
async def add_team_user(team_id: str, request: Request, Authorization: Optional[str] = Header(None)):
    user = auth_guard(Authorization)
    tenant_id = user.get("tenant_id") or "00000000-0000-0000-0000-000000000001"
    require_admin(user, tenant_id)
    
    payload = await request.json()
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
        
    # Check if exists
    existing = supabase.table("team_users").select("*").eq("team_id", team_id).eq("user_id", user_id).execute()
    if existing.data:
        return {"data": existing.data[0], "error": None}
        
    data = {
        "id": str(uuid.uuid4()),
        "team_id": team_id,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    resp = supabase.table("team_users").insert(data).execute()
    return {"data": data, "error": None}

@router.delete("/{team_id}/users/{user_id}")
@require_permission("teams_update")
async def remove_team_user(team_id: str, user_id: str, Authorization: Optional[str] = Header(None)):
    user = auth_guard(Authorization)
    tenant_id = user.get("tenant_id") or "00000000-0000-0000-0000-000000000001"
    require_admin(user, tenant_id)
    
    supabase.table("team_users").delete().eq("team_id", team_id).eq("user_id", user_id).eq("tenant_id", tenant_id).execute()
    return {"data": True, "error": None}

@router.get("/{team_id}/projects")
@require_permission("teams_retrieve")
async def get_team_projects(team_id: str, Authorization: Optional[str] = Header(None)):
    user = auth_guard(Authorization)
    tenant_id = user.get("tenant_id") or "00000000-0000-0000-0000-000000000001"
    
    query = '''
    SELECT tp.id as mapping_id, tp.project_id, p.project_name, p.application_name, p.product_name
    FROM team_projects tp
    JOIN projects p ON tp.project_id = CAST(p.id AS TEXT) OR tp.project_id = p.application_name
    WHERE tp.team_id = %s AND tp.tenant_id = %s
    '''
    rows = execute_query(query, (team_id, tenant_id), fetch_all=True) or []
    return {"data": rows, "error": None}

@router.post("/{team_id}/projects")
@require_permission("teams_update")
async def add_team_project(team_id: str, request: Request, Authorization: Optional[str] = Header(None)):
    user = auth_guard(Authorization)
    tenant_id = user.get("tenant_id") or "00000000-0000-0000-0000-000000000001"
    require_admin(user, tenant_id)
    
    payload = await request.json()
    project_id = payload.get("project_id")
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id is required")
        
    existing = supabase.table("team_projects").select("*").eq("team_id", team_id).eq("project_id", project_id).execute()
    if existing.data:
        return {"data": existing.data[0], "error": None}
        
    data = {
        "id": str(uuid.uuid4()),
        "team_id": team_id,
        "project_id": project_id,
        "tenant_id": tenant_id,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    supabase.table("team_projects").insert(data).execute()
    return {"data": data, "error": None}

@router.delete("/{team_id}/projects/{project_id}")
@require_permission("teams_update")
async def remove_team_project(team_id: str, project_id: str, Authorization: Optional[str] = Header(None)):
    user = auth_guard(Authorization)
    tenant_id = user.get("tenant_id") or "00000000-0000-0000-0000-000000000001"
    require_admin(user, tenant_id)
    
    supabase.table("team_projects").delete().eq("team_id", team_id).eq("project_id", project_id).eq("tenant_id", tenant_id).execute()
    return {"data": True, "error": None}

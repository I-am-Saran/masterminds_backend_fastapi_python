# REFERENCE_ONLY_MODULE — legacy Kaizen module; preserved for compatibility.
from fastapi import APIRouter, HTTPException, Request, Header, Query, File, UploadFile
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any, List
import json, base64
from datetime import datetime, timezone
from psycopg2.extras import Json
from services.db_service import execute_query, insert_table, update_table
from services.bug_validator import (
    validate_bug_payload, prepare_bug_payload, get_dropdown_values
)
from services.auth_service import get_user_from_token, auth_guard
from services.rbac_service import get_user_accessible_project_names
from utils.error_handler import handle_endpoint_error
from utils.application_enum import ApplicationName
from services.rbac_service import require_permission

router = APIRouter()

DEFAULT_TENANT = '00000000-0000-0000-0000-000000000001'

# ---------- COMMON HELPERS ----------


def jload(v, default):
    if v is None:
        return default
    try:
        return json.loads(v) if isinstance(v, str) else v
    except:
        return default

def now():
    return datetime.now(timezone.utc).isoformat()

# ---------- NORMALIZER ----------

def get_next_bug_id(tenant_id: str):
    try:
        # Fetch all bug IDs for this tenant
        query = 'SELECT "Bug ID" FROM "bugs" WHERE "tenant_id" = %s'
        rows = execute_query(query, (tenant_id,), fetch_all=True) or []
        existing_ids = [row.get("Bug ID") for row in rows if row.get("Bug ID")]
        
        max_id = 0
        for bid in existing_ids:
            if isinstance(bid, str) and bid.startswith("BUG-"):
                try:
                    parts = bid.split("-")
                    if len(parts) == 2:
                        num = int(parts[1])
                        if num > max_id:
                            max_id = num
                except:
                    pass
        
        return f"BUG-{max_id + 1:03d}"
    except Exception as e:
        print(f"Error generating bug ID: {e}")
        return f"BUG-{int(datetime.now().timestamp())}"

def normalize_bug_row(r: Dict[str, Any], user_map: Dict[str, str] = None) -> Dict[str, Any]:
    # Helper to resolve name/email from ID if missing
    def resolve(id_key, name_key, type="name"):
        val = r.get(name_key)
        if val: return val
        uid = r.get(id_key)
        if uid and user_map and uid in user_map:
            user_info = user_map[uid]
            if isinstance(user_info, dict):
                return user_info.get(type, "")
            return user_info if type == "name" else "" # Fallback for old simple map
        return ""

    return {
        "Bug ID": r.get("Bug ID") or r.get("bug_id") or r.get("id"),
        "Summary": r.get("Summary") or r.get("summary", ""),
        "Priority": r.get("Priority") or r.get("priority", ""),
        "Status": r.get("Status") or r.get("status", ""),
        "Assignee": r.get("Assignee", ""),
        "Assignee Real Name": resolve("Assignee", "Assignee Real Name", "name"),
        "Assignee Email": resolve("Assignee", "Assignee Email", "email"),
        "Reporter": r.get("Reporter", ""),
        "Reporter Real Name": resolve("Reporter", "Reporter Real Name", "name"),
        "Reporter Email": resolve("Reporter", "Reporter Email", "email"),
        "Product": r.get("Product") or r.get("Project", ""),
        "Component": r.get("Component", ""),
        "Defect type": r.get("Defect type", ""),
        "Steps to Reproduce": r.get("Steps to Reproduce", ""),
        "Automation Intent": r.get("Automation Intent", ""),
        "Device type": r.get("Device type", ""),
        "Browser tested": r.get("Browser tested", ""),
        "Testing phase": r.get("Testing phase", ""),
        "Ticket Type": r.get("Ticket Type", ""),
        "Project Owner": r.get("Project Owner", ""),
        "Project Owner Name": resolve("Project Owner", "Project Owner Name", "name"),
        "Project Owner Email": resolve("Project Owner", "Project Owner Email", "email"),
        "Sprint details": r.get("Sprint details", ""),
        "Automation Owner": r.get("automation_owner", ""),
        "Automation Owner Name": resolve("automation_owner", "Automation Owner Name", "name"),
        "Automation Owner Email": resolve("automation_owner", "Automation Owner Email", "email"),
        "Description": r.get("Description", ""),
        "Comments": jload(r.get("Comments") or r.get("Comment"), []),
        "Attachments": jload(r.get("Attachments"), []),
        "ActivityLog": jload(r.get("ActivityLog"), []),
        "Changed": r.get("Changed", ""),
        "Created": r.get("Opened") or r.get("created_at", ""),
        "created_at": r.get("created_at", ""),
        "tester_type": r.get("tester_type", "Internal Tester")
    }

# ---------- DB HELPERS ----------

def get_user_map(tenant_id: str) -> Dict[str, Dict[str, str]]:
    """Fetch all users and return a mapping of id -> {full_name, email} for a tenant"""
    try:
        query = 'SELECT id, full_name, email FROM "users" WHERE "tenant_id" = %s'
        rows = execute_query(query, (tenant_id,), fetch_all=True) or []
        return {u['id']: {"name": u['full_name'], "email": u['email']} for u in rows}
    except:
        return {}

def fetch_bugs():
    query = 'SELECT * FROM "bugs" ORDER BY "Changed" DESC'
    rows = execute_query(query, fetch_all=True) or []
    user_map = get_user_map()
    return [normalize_bug_row(b, user_map) for b in rows]

def insert_bug(payload):
    row = insert_table("bugs", payload)
    user_map = get_user_map()
    return normalize_bug_row(row, user_map) if row else {}

# ---------- ENDPOINTS ----------

def fetch_bugs(tenant_id: str, user_id: str) -> List[Dict[str, Any]]:
    """Fetches all bugs for a given tenant, with lite normalization for list view."""
    accessible_projects = get_user_accessible_project_names(user_id, tenant_id)
    
    if accessible_projects is not None:
        if not accessible_projects:
            return [] # No projects accessible
        
        # Optimize query by filtering at the DB level
        placeholders = ', '.join(['%s'] * len(accessible_projects))
        query = f'''
            SELECT "Bug ID", "id", "Summary", "Priority", "Status",
                   "Assignee", "Assignee Real Name", "Reporter", "Reporter Real Name",
                   "Product", "Project", "Component", "Defect type", "Steps to Reproduce", "Automation Intent",
                   "Device type", "Browser tested", "Testing phase", "Ticket Type", "Project Owner", "Project Owner Name",
                   "Sprint details", "automation_owner", "Description", "Comments", "Comment", "Attachments", "Changed", "created_at", "tester_type", "Severity", "Opened"
            FROM "bugs" 
            WHERE "tenant_id" = %s AND "is_deleted" IS DISTINCT FROM %s 
            AND ("Project" IN ({placeholders}) OR "Product" IN ({placeholders}))
            ORDER BY "Changed" DESC
        '''
        params = [tenant_id, True] + list(accessible_projects) + list(accessible_projects)
        rows = execute_query(query, tuple(params), fetch_all=True) or []
    else:
        query = '''
            SELECT "Bug ID", "id", "Summary", "Priority", "Status",
                   "Assignee", "Assignee Real Name", "Reporter", "Reporter Real Name",
                   "Product", "Project", "Component", "Defect type", "Steps to Reproduce", "Automation Intent",
                   "Device type", "Browser tested", "Testing phase", "Ticket Type", "Project Owner", "Project Owner Name",
                   "Sprint details", "automation_owner", "Description", "Comments", "Comment", "Attachments", "Changed", "created_at", "tester_type", "Severity", "Opened"
            FROM "bugs" 
            WHERE "tenant_id" = %s AND "is_deleted" IS DISTINCT FROM %s 
            ORDER BY "Changed" DESC
        '''
        rows = execute_query(query, (tenant_id, True), fetch_all=True) or []

    user_map = get_user_map(tenant_id)
    
    data = []
    for b in rows:
        row = normalize_bug_row(b, user_map)
        # Strip heavy attachment content (data URIs) for list view
        if row.get("Attachments"):
            for att in row["Attachments"]:
                if isinstance(att, dict) and att.get("url", "").startswith("data:"):
                    att["url"] = "" # Strip data URI to reduce payload size
                    att["_has_content"] = True
        
        # Remove ActivityLog entirely to save massive payload sizes
        row["ActivityLog"] = []
        data.append(row)
    return data

def get_bug(bug_id: str, tenant_id: str, user_id: str) -> Dict[str, Any]:
    """Fetches a single bug by ID for a given tenant."""
    query = 'SELECT * FROM "bugs" WHERE "Bug ID" = %s AND "tenant_id" = %s AND "is_deleted" IS DISTINCT FROM %s LIMIT 1'
    row = execute_query(query, (bug_id, tenant_id, True), fetch_one=True)
    if not row:
        raise HTTPException(404, "Bug not found")
        
    accessible_projects = get_user_accessible_project_names(user_id, tenant_id)
    if accessible_projects is not None:
        if row.get("Project") not in accessible_projects and row.get("Product") not in accessible_projects:
            raise HTTPException(403, "Access denied to this bug's project")
    
    user_map = get_user_map(tenant_id)
    return normalize_bug_row(row, user_map)

def create_bug(payload: Dict[str, Any], tenant_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    """Creates a new bug."""
    
    # 1. Ignore Bug ID from frontend (it must be server-generated)
    payload.pop("Bug ID", None)
    payload.pop("bug_id", None)
    
    user_id = user.get("user_id") or user.get("id")
    accessible_projects = get_user_accessible_project_names(user_id, tenant_id)
    
    # Check for project/product key in various casings
    project = payload.get("Project") or payload.get("Product") or payload.get("project") or payload.get("product")
    
    if accessible_projects is not None and project not in accessible_projects:
        raise HTTPException(403, "Cannot create bug in this project. Access denied.")

    # 2. Validate payload (checks required fields, etc.)
    # Note: We validate BEFORE sanitization to ensure required fields are present in the original request
    ok, msg = validate_bug_payload(payload, "create")
    if not ok:
        raise HTTPException(400, msg)

    # 3. Sanitize payload - This MUST happen before adding system fields
    # to ensure we only have valid DB columns + mapped fields.
    sanitized_payload = prepare_bug_payload(payload)
    
    # 4. Generate Bug ID server-side
    sanitized_payload["Bug ID"] = get_next_bug_id(tenant_id)

    # 5. Add system-managed fields
    sanitized_payload["tenant_id"] = tenant_id
    sanitized_payload.setdefault("Status", "OPEN")
    sanitized_payload.setdefault("Priority", "Medium")
    sanitized_payload["Changed"] = now()
    
    # Ensure automation_owner is handled if present (already mapped by prepare_bug_payload)
    # sanitized_payload["automation_owner"] = sanitized_payload.get("automation_owner")

    sanitized_payload["ActivityLog"] = json.dumps([{
        "user": user.get("full_name", "System"),
        "timestamp": now(),
        "changes": [{"field": "System", "old": "", "new": "Bug Created"}]
    }])

    # 6. Ensure JSON fields are correctly handled
    # Convert them to JSON using json.dumps before insertion
    json_fields = ["Comments", "Attachments", "ActivityLog"]
    for field in json_fields:
        if field in sanitized_payload and isinstance(sanitized_payload[field], list):
             sanitized_payload[field] = json.dumps(sanitized_payload[field])

    # Debugging
    print(f"[DEBUG] FINAL PAYLOAD for INSERT: {json.dumps(sanitized_payload, default=str)}")
    print(f"[DEBUG] FINAL PAYLOAD KEYS: {list(sanitized_payload.keys())}")

    # 7. Insert using ONLY the sanitized payload
    row = insert_table("bugs", sanitized_payload)
    user_map = get_user_map(tenant_id)
    return normalize_bug_row(row, user_map) if row else {}

def update_bug(bug_id: str, payload: Dict[str, Any], tenant_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    """Updates an existing bug."""
    user_id = user.get("user_id") or user.get("id")
    accessible_projects = get_user_accessible_project_names(user_id, tenant_id)
    
    # Verify bug exists and check permissions
    query_existing = 'SELECT "Project", "Product" FROM "bugs" WHERE "Bug ID" = %s AND "tenant_id" = %s LIMIT 1'
    existing = execute_query(query_existing, (bug_id, tenant_id), fetch_one=True)
    if not existing:
        raise HTTPException(404, "Bug not found")
        
    if accessible_projects is not None:
        if existing.get("Project") not in accessible_projects and existing.get("Product") not in accessible_projects:
             raise HTTPException(403, "Cannot update bug in this project. Access denied.")
        
        # Also check if they are trying to move the bug to an inaccessible project
        new_project = payload.get("Project") or payload.get("Product") or payload.get("project") or payload.get("product")
        if new_project and new_project not in accessible_projects:
             raise HTTPException(403, "Cannot move bug to an inaccessible project. Access denied.")
             
    ok, msg = validate_bug_payload(payload, "update")
    if not ok:
        raise HTTPException(400, msg)

    payload = prepare_bug_payload(payload)
    payload["Changed"] = now()

    for k in ["Comments", "Attachments", "ActivityLog"]:
        if isinstance(payload.get(k), list):
            payload[k] = json.dumps(payload[k])

    print("UPDATE PAYLOAD:", payload)

    row = update_table("bugs", payload, {"Bug ID": bug_id, "tenant_id": tenant_id})
    if not row:
        raise HTTPException(404, "Update failed or bug not found for this tenant")

    user_map = get_user_map(tenant_id)
    return normalize_bug_row(row, user_map)

# ---------- ENDPOINTS ----------

@router.get("/users/dropdown")
@require_permission("bugs_retrieve")
async def users_dropdown(Authorization: str = Header(None)):
    try:
        user = auth_guard(Authorization)
        tenant_id = user.get("tenant_id") or DEFAULT_TENANT
        query = 'SELECT id, full_name, email FROM "users" WHERE "is_active" = %s AND "tenant_id" = %s'
        rows = execute_query(query, (True, tenant_id), fetch_all=True) or []
        return {"data": rows, "error": None}
    except Exception as e:
        return handle_endpoint_error(e, "/users/dropdown", "users_dropdown", True)

@router.get("/bugs/users-dropdown")
@require_permission("bugs_retrieve")
async def bugs_users_dropdown(
    project: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    Authorization: str = Header(None)
):
    try:
        user = auth_guard(Authorization)
        tenant_id = user.get("tenant_id") or DEFAULT_TENANT
        user_id = user.get("user_id") or user.get("id")
        
        # Enforce RBAC: only allow fetching users for accessible projects
        accessible_projects = get_user_accessible_project_names(user_id, tenant_id)
        if project and accessible_projects is not None and project not in accessible_projects:
            # Forbidden to access users for this project
            return {"data": [], "error": None}
        
        if project:
            # Tolerant joins for legacy data:
            # - tu.user_id may be UUID or email
            # - tp.project_id may be UUID or application_name
            # - tenant_id on tp/tu/p may be NULL; accept NULL for project row and team links
            query = """
                SELECT DISTINCT u.id, u.full_name, u.email, u.department 
                FROM users u
                JOIN team_users tu 
                    ON (tu.user_id = u.id OR tu.user_id = u.email)
                JOIN team_projects tp 
                    ON tp.team_id = tu.team_id
                JOIN projects p 
                    ON (tp.project_id = CAST(p.id AS TEXT) OR tp.project_id = p.application_name)
                WHERE u.is_active = TRUE
                  AND (u.tenant_id = %s OR u.tenant_id IS NULL)
                  AND (p.tenant_id = %s OR p.tenant_id IS NULL)
                  AND p.application_name = %s
            """
            rows = execute_query(query, (tenant_id, tenant_id, project), fetch_all=True) or []
            
            # Always include explicit project_owner/assignee emails from projects table if present
            meta_sql = """
                SELECT project_owner, assignee 
                FROM projects 
                WHERE application_name = %s 
                  AND (tenant_id = %s OR tenant_id IS NULL)
                LIMIT 1
            """
            meta = execute_query(meta_sql, (project, tenant_id), fetch_one=True) or {}
            extras = []
            for email_col in ("project_owner", "assignee"):
                em = (meta.get(email_col) or "").strip()
                if not em:
                    continue
                urow = execute_query(
                    'SELECT id, full_name, email, department FROM "users" WHERE ("email" = %s OR "id"::text = %s) AND ("is_active" = TRUE) AND ("tenant_id" = %s OR "tenant_id" IS NULL) LIMIT 1',
                    (em, em, tenant_id),
                    fetch_one=True
                )
                if urow:
                    extras.append(urow)
            if extras:
                # Merge extras into rows, dedup later
                rows = (rows or []) + extras
        else:
            # Fetch all users with detailed info for this tenant (used for general search/fallback)
            query = 'SELECT id, full_name, email, department FROM "users" WHERE "is_active" = %s AND ("tenant_id" = %s OR "tenant_id" IS NULL)'
            rows = execute_query(query, (True, tenant_id), fetch_all=True) or []
        
        # Optional in-memory search filter for q
        if q:
            ql = q.strip().lower()
            rows = [
                r for r in rows
                if (str(r.get("full_name") or "").lower().find(ql) >= 0) 
                or (str(r.get("email") or "").lower().find(ql) >= 0)
            ]
        
        # Deduplicate by id or email, preserve first-seen
        seen = set()
        unique_rows = []
        for r in rows:
            key = (str(r.get("id") or ""), str(r.get("email") or "").lower())
            if key in seen:
                continue
            seen.add(key)
            unique_rows.append(r)
        
        # Sort by full name
        unique_rows.sort(key=lambda r: (r.get("full_name") or "").lower())
        return {"data": unique_rows, "error": None}
    except Exception as e:
        return handle_endpoint_error(e, "/bugs/users-dropdown", "bugs_users_dropdown", True)

@router.get("/products")
@require_permission("bugs_retrieve")
async def products(Authorization: str = Header(None)):
    user = auth_guard(Authorization)
    tenant_id = user.get("tenant_id") or DEFAULT_TENANT
    user_id = user.get("user_id") or user.get("id")
    
    accessible_projects = get_user_accessible_project_names(user_id, tenant_id)
    if accessible_projects is not None:
        # User is restricted by team, return only accessible projects
        return {"data": sorted(list(accessible_projects)), "error": None}
    else:
        # Admin / Superadmin, return all projects
        query = 'SELECT DISTINCT application_name FROM "projects" WHERE "tenant_id" = %s'
        rows = execute_query(query, (tenant_id,), fetch_all=True) or []
        names = [r.get("application_name") for r in rows if r.get("application_name")]
        return {"data": sorted(list(set(names))), "error": None}

@router.get("/bugs/dropdowns")
@require_permission("bugs_retrieve")
async def bug_dropdowns(Authorization: str = Header(None)):
    try:
        user = auth_guard(Authorization)
        tenant_id = user.get("tenant_id") or DEFAULT_TENANT
        user_id = user.get("user_id") or user.get("id")
        
        dropdowns = get_dropdown_values().copy()
        
        accessible_projects = get_user_accessible_project_names(user_id, tenant_id)
        if accessible_projects is not None:
            dropdowns["Product"] = sorted(list(accessible_projects))
        else:
            query = 'SELECT DISTINCT application_name FROM "projects" WHERE "tenant_id" = %s'
            rows = execute_query(query, (tenant_id,), fetch_all=True) or []
            names = [r.get("application_name") for r in rows if r.get("application_name")]
            dropdowns["Product"] = sorted(list(set(names)))
            
        return {"data": dropdowns, "error": None}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return handle_endpoint_error(e, "/bugs/dropdowns", "bug_dropdowns", True)

@router.get("/bugs")
@require_permission("bugs_retrieve")
async def get_bugs_api(Authorization: str = Header(None)):
    user = auth_guard(Authorization)
    tenant_id = user.get("tenant_id") or DEFAULT_TENANT
    user_id = user.get("user_id") or user.get("id")
    return {"data": fetch_bugs(tenant_id, user_id), "error": None}

@router.get("/bugs/{bug_id}")
@require_permission("bugs_retrieve")
async def get_bug_by_id(bug_id: str, Authorization: str = Header(None)):
    user = auth_guard(Authorization)
    tenant_id = user.get("tenant_id") or DEFAULT_TENANT
    user_id = user.get("user_id") or user.get("id")
    bug = get_bug(bug_id, tenant_id, user_id)
    return {"data": bug, "error": None}

@router.post("/bugs")
@require_permission("bugs_create")
async def create_bug_api(req: Request, Authorization: str = Header(None)):
    user = auth_guard(Authorization)
    tenant_id = user.get("tenant_id") or DEFAULT_TENANT
    payload = await req.json()
    new_bug = create_bug(payload, tenant_id, user)
    return {"data": new_bug, "error": None}

@router.put("/bugs/{bug_id}")
@require_permission("bugs_update")
async def update_bug_api(bug_id: str, req: Request, Authorization: str = Header(None)):
    try:
        user = auth_guard(Authorization)
        tenant_id = user.get("tenant_id") or DEFAULT_TENANT
        payload = await req.json()
        updated_bug = update_bug(bug_id, payload, tenant_id, user)
        return {"data": updated_bug, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Internal Server Error: {str(e)}")

@router.delete("/bugs/{bug_id}")
@require_permission("bugs_delete")
async def delete_bug(bug_id: str, Authorization: str = Header(None)):
    user = auth_guard(Authorization)
    tenant_id = user.get("tenant_id") or DEFAULT_TENANT
    user_id = user.get("user_id") or user.get("id")
    accessible_projects = get_user_accessible_project_names(user_id, tenant_id)
    
    # Verify bug exists and check permissions
    query_existing = 'SELECT "Project", "Product" FROM "bugs" WHERE "Bug ID" = %s AND "tenant_id" = %s LIMIT 1'
    existing = execute_query(query_existing, (bug_id, tenant_id), fetch_one=True)
    if not existing:
        raise HTTPException(404, "Bug not found")
        
    if accessible_projects is not None:
        if existing.get("Project") not in accessible_projects and existing.get("Product") not in accessible_projects:
             raise HTTPException(403, "Cannot delete bug in this project. Access denied.")

    update_table("bugs", {"is_deleted": True}, {"Bug ID": bug_id, "tenant_id": tenant_id})
    return {"data": True, "error": None}

@router.post("/bugs/{bug_id}/upload")
@require_permission("bugs_update")
async def upload_attachment(
    bug_id: str,
    file: UploadFile = File(...),
    Authorization: str = Header(None)
):
    try:
        user = auth_guard(Authorization)
        tenant_id = user.get("tenant_id") or DEFAULT_TENANT
        user_id = user.get("user_id") or user.get("id")
        accessible_projects = get_user_accessible_project_names(user_id, tenant_id)
        
        content = await file.read()
        print(f"[DEBUG] Uploading file: {file.filename}, Size: {len(content)}")
        attach = {
            "name": file.filename,
            "type": file.content_type,
            "size": len(content),
            "uploaded_at": now(),
            "url": f"data:{file.content_type};base64,{base64.b64encode(content).decode()}"
        }

        query = 'SELECT "Attachments", "Project", "Product" FROM "bugs" WHERE "Bug ID" = %s AND "tenant_id" = %s LIMIT 1'
        row = execute_query(query, (bug_id, tenant_id), fetch_one=True)
        
        if not row:
            print(f"[DEBUG] Bug {bug_id} not found for tenant {tenant_id}")
            raise HTTPException(404, "Bug not found")
            
        if accessible_projects is not None:
            if row.get("Project") not in accessible_projects and row.get("Product") not in accessible_projects:
                raise HTTPException(403, "Cannot upload attachment to this bug. Access denied.")

        current_att = row.get("Attachments")
        print(f"[DEBUG] Current attachments raw: {current_att}, type: {type(current_att)}")
        attachments = jload(current_att, [])
        print(f"[DEBUG] Parsed attachments: {len(attachments)}")
        
        attachments.append(attach)
        print(f"[DEBUG] New attachment count: {len(attachments)}")

        # Use json.dumps for consistency with other endpoints
        updated_val = json.dumps(attachments)

        res = update_table("bugs", {"Attachments": updated_val}, {"Bug ID": bug_id, "tenant_id": tenant_id})
        print(f"[DEBUG] Update result: {res}")
        
        return {"data": attach, "error": None}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"detail": str(e), "traceback": traceback.format_exc()})



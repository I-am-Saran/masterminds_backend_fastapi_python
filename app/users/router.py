from fastapi import APIRouter, HTTPException, Request, Header, Query
from typing import Optional, Dict, Any, List
import os
import logging
import smtplib
from email.message import EmailMessage
from datetime import datetime, timezone
import uuid
from services.db_service import local_db as supabase, execute_query, update_table
from services.rbac_service import (
    get_user_roles,
    assign_role_to_user,
    remove_role_from_user,
    remove_role_from_user_any_tenant,
    is_superadmin,
    is_global_superadmin,
    get_role_id_by_name,
    get_role_permissions,
    check_permission,
)
from services.auth_service import (
    get_user_from_token,
    auth_guard,
    hash_password,
    verify_password,
)
from utils.error_handler import handle_api_error, handle_endpoint_error
from services.rbac_service import require_permission

router = APIRouter()


def _resolve_user_db_id(user_key: str, tenant_id: Optional[str] = None) -> Optional[str]:
    """Resolve users.id from id, email, or uuid_id text (tenant-scoped when provided)."""
    key = (user_key or "").strip()
    if not key:
        return None
    if tenant_id:
        row = execute_query(
            """
            SELECT id FROM users
            WHERE tenant_id = %s
              AND (
                id = %s
                OR LOWER(TRIM(email)) = LOWER(TRIM(%s))
                OR uuid_id::text = %s
              )
            ORDER BY updated_at DESC NULLS LAST
            LIMIT 1
            """,
            (tenant_id, key, key, key),
            fetch_one=True,
        )
    else:
        row = execute_query(
            """
            SELECT id FROM users
            WHERE id = %s
               OR LOWER(TRIM(email)) = LOWER(TRIM(%s))
               OR uuid_id::text = %s
            ORDER BY updated_at DESC NULLS LAST
            LIMIT 1
            """,
            (key, key, key),
            fetch_one=True,
        )
    if not row or row.get("id") is None:
        return None
    return str(row["id"])


def _resolve_user_db_id_by_email(email: str, tenant_id: str) -> Optional[str]:
    normalized = (email or "").strip().lower()
    if not normalized or not tenant_id:
        return None
    row = execute_query(
        """
        SELECT id FROM users
        WHERE tenant_id = %s AND LOWER(TRIM(email)) = LOWER(%s)
        LIMIT 1
        """,
        (tenant_id, normalized),
        fetch_one=True,
    )
    if not row or row.get("id") is None:
        return None
    return str(row["id"])


def _user_public_row(user_id: str) -> Optional[Dict[str, Any]]:
    return execute_query(
        """
        SELECT id, email, full_name, role, department, department_owner, is_active, tenant_id, created_at, updated_at
        FROM users
        WHERE id = %s
        LIMIT 1
        """,
        (user_id,),
        fetch_one=True,
    )


def users_has_roles_column() -> bool:
    try:
        result = execute_query(
            "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
            params=("users", "roles"),
            fetch_one=True,
            fetch_all=False,
        )
        return bool(result)
    except Exception:
        return False



@router.get("/users/search")
@require_permission("users_retrieve")
async def search_users(q: str = Query(default=""), tenant_id: str = Query('00000000-0000-0000-0000-000000000001'), Authorization: Optional[str] = Header(default=None)):
    endpoint = "/users/search"
    try:
        auth_data = auth_guard(Authorization)
        effective_tenant_id = auth_data.get("tenant_id") or tenant_id
        query = q.strip()
        if not query:
            return {"data": [], "error": None}
        resp = (
            supabase
            .table("users")
            .select("id,email,full_name,department")
            .eq("tenant_id", effective_tenant_id)
            .ilike("email", f"%{query}%")
            .limit(10)
            .execute()
        )
        if getattr(resp, "error", None):
            raise HTTPException(status_code=400, detail=str(resp.error))
        return {"data": resp.data or [], "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "search_users", return_dict=True, query=q)

@router.get("/users/dropdown")
@require_permission("users_retrieve")
async def users_dropdown(tenant_id: str = Query('00000000-0000-0000-0000-000000000001'), Authorization: Optional[str] = Header(default=None)):
    endpoint = "/users/dropdown"
    try:
        auth_data = auth_guard(Authorization)
        effective_tenant_id = auth_data.get("tenant_id") or tenant_id
        resp = supabase.table("users").select("id, full_name").eq("is_active", True).eq("tenant_id", effective_tenant_id).execute()
        return {"data": resp.data or [], "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "users_dropdown", return_dict=True)

@router.get("/users")
@require_permission("users_retrieve")
async def get_users(
    tenant_id: str = Query('00000000-0000-0000-0000-000000000001'),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = "/users"
    try:
        auth_data = auth_guard(Authorization)
        effective_tenant_id = auth_data.get("tenant_id") or tenant_id
        try:
            resp = supabase.table("users").select("*").eq("tenant_id", effective_tenant_id).order("last_login", desc=True).execute()
        except Exception:
            try:
                resp = supabase.table("users").select("*").eq("tenant_id", effective_tenant_id).execute()
            except Exception:
                return {"status": "success", "data": []}
        rows = resp.data if hasattr(resp, 'data') else (resp if isinstance(resp, list) else [])
        if not isinstance(rows, list):
            rows = []
        for r in rows:
            if isinstance(r, dict):
                if "name" not in r or not r.get("name"):
                    r["name"] = r.get("full_name") or (r.get("email") or "").split("@")[0]
        return {"status": "success", "data": rows}
    except HTTPException:
        raise
    except Exception as e:
        error_response, status_code = handle_api_error(
            e,
            endpoint,
            context={"operation": "get_users", "table": "users"},
            include_traceback=False,
            user_message="Failed to fetch users"
        )
        raise HTTPException(status_code=status_code, detail=error_response["error"])

@router.post("/users")
@require_permission("users_create")
async def create_user(
    request: Request,
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = "/users"
    try:
        payload = await request.json()
        auth_data = auth_guard(Authorization)
        current_user_id = auth_data.get("user_id")
        
        # Determine tenant_id
        # Only global superadmin can specify a different tenant_id
        user_tenant_id = auth_data.get("tenant_id")
        requested_tenant_id = payload.get("tenant_id")
        
        tenant_id = user_tenant_id or "00000000-0000-0000-0000-000000000001"
        
        if requested_tenant_id and requested_tenant_id != user_tenant_id:
            if is_global_superadmin(current_user_id):
                tenant_id = requested_tenant_id
            else:
                # If not superadmin, silently ignore requested_tenant_id and use their own, 
                # or raise 403. Silently ignoring or using own is safer/common, 
                # but let's stick to using their own to prevent creating users in other tenants.
                pass 

        email = (payload.get("email") or "").strip().lower()
        full_name = (payload.get("username") or payload.get("name") or "").strip()
        role = (payload.get("role") or "Viewer").strip()
        department = (payload.get("department") or "").strip()
        if not email:
            raise HTTPException(status_code=400, detail="Email is required")
        existing = supabase.table("users").select("id").eq("email", email).execute()
        if (existing.data or []):
            raise HTTPException(status_code=409, detail="User with this email already exists")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        has_roles_col = users_has_roles_column()
        user_id = str(uuid.uuid4())
        sso_user_id = payload.get("sso_user_id") or None
        if sso_user_id == "":
            sso_user_id = None
        password = (payload.get("password") or "").strip()
        hashed_password = hash_password(password) if password else None
        department_owner = (payload.get("department_owner") or "").strip() or None
        # tenant_id logic moved up
        
        to_insert = {
            "id": user_id,
            "email": email,
            "full_name": full_name or email.split("@")[0],
            "role": role or "Viewer",
            "department": department or None,
            "department_owner": department_owner,
            **({"password": hashed_password} if hashed_password else {}),
            "is_active": True,
            "created_at": now,
            "updated_at": now,
            "sso_provider": (payload.get("sso_provider") or "manual"),
            "sso_user_id": sso_user_id,
            "login_count": 0,
            "tenant_id": tenant_id,
        }
        if has_roles_col:
            to_insert["roles"] = role or "Viewer"
        resp = supabase.table("users").insert(to_insert, returning="representation").execute()
        if getattr(resp, "error", None):
            raise HTTPException(status_code=500, detail=str(resp.error))
        inserted = (resp.data or [None])[0]
        # Assign the selected role dynamically (fallback to Viewer only if not found)
        role_id = get_role_id_by_name(role, tenant_id) if role else None
        if not role_id:
            role_id = get_role_id_by_name("Viewer", tenant_id)
        if role_id:
            assign_success = assign_role_to_user(user_id, role_id, tenant_id, None)
            if not assign_success:
                logging.warning(f"Failed to assign role {role} to user {user_id}")
        else:
            logging.warning(f"Role '{role or 'Viewer'}' not found for tenant {tenant_id}")
        return {"status": "success", "data": inserted}
    except HTTPException:
        raise
    except Exception as e:
        error_response, status_code = handle_api_error(
            e,
            endpoint,
            context={"operation": "create_user", "email": payload.get("email") if 'payload' in locals() else None},
            include_traceback=False,
            user_message="Failed to create user"
        )
        error_detail = error_response.get("error", {"message": "Failed to create user"})
        raise HTTPException(status_code=status_code, detail=error_detail)

@router.get("/users/{user_id}")
@require_permission("users_retrieve")
async def get_user(
    user_id: str,
    tenant_id: str = Query('00000000-0000-0000-0000-000000000001'),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = f"/users/{user_id}"
    try:
        auth_data = auth_guard(Authorization)
        effective_tenant_id = auth_data.get("tenant_id") or tenant_id
        
        user = None
        try:
            uid_int = int(user_id)
            resp = supabase.table("users").select("*").eq("id", uid_int).eq("tenant_id", effective_tenant_id).execute()
            if (getattr(resp, "data", None) or []):
                user = resp.data[0]
        except Exception:
            pass
        if not user:
            # Try by UUID
            resp = supabase.table("users").select("*").eq("id", user_id).eq("tenant_id", effective_tenant_id).execute()
            if not (getattr(resp, "data", None) or []):
                # Try by Email
                resp = supabase.table("users").select("*").eq("email", user_id).eq("tenant_id", effective_tenant_id).execute()
            if (getattr(resp, "data", None) or []):
                user = resp.data[0]
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if "name" not in user or not user.get("name"):
            user["name"] = user.get("full_name") or (user.get("email") or "").split("@")[0]
        return {"status": "success", "data": user}
    except HTTPException:
        raise
    except Exception as e:
        error_response, status_code = handle_api_error(
            e,
            endpoint,
            context={"operation": "get_user", "user_id": user_id},
            include_traceback=False,
            user_message="Failed to fetch user"
        )
        raise HTTPException(status_code=status_code, detail=error_response["error"])

@router.put("/users/{user_id}")
@require_permission("users_update")
async def update_user(
    user_id: str,
    request: Request,
    tenant_id: str = Query('00000000-0000-0000-0000-000000000001'),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = f"/users/{user_id}"
    try:
        payload = await request.json()
        auth_data = auth_guard(Authorization)
        effective_tenant_id = auth_data.get("tenant_id") or tenant_id
        current_user_id = auth_data.get("user_id") or auth_data.get("id")

        if "password" in payload:
            if not (is_global_superadmin(current_user_id) or is_superadmin(current_user_id, effective_tenant_id)):
                raise HTTPException(status_code=403, detail="Only Super Admin can change user passwords")
            new_password = (payload.get("password") or "").strip()
            if not new_password:
                raise HTTPException(status_code=400, detail="Password is required")

            payload_email = (payload.get("email") or "").strip().lower()
            if payload_email:
                actual_user_id = _resolve_user_db_id_by_email(payload_email, effective_tenant_id)
            else:
                actual_user_id = _resolve_user_db_id(user_id, effective_tenant_id)
            if not actual_user_id:
                raise HTTPException(status_code=404, detail="User not found")

            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            hashed_password = hash_password(new_password)
            updated = execute_query(
                """
                UPDATE users
                SET password = %s, updated_at = %s
                WHERE id = %s
                RETURNING id, email
                """,
                (hashed_password, now, actual_user_id),
                fetch_one=True,
            )
            if not updated:
                raise HTTPException(status_code=404, detail="User not found or password update failed")

            stored = execute_query(
                "SELECT password FROM users WHERE id = %s LIMIT 1",
                (actual_user_id,),
                fetch_one=True,
            )
            stored_hash = (stored or {}).get("password")
            if not stored_hash or not verify_password(new_password, stored_hash):
                logging.error(
                    "[users] password update verification failed for user_id=%s email=%s",
                    actual_user_id,
                    updated.get("email"),
                )
                raise HTTPException(
                    status_code=500,
                    detail="Password was not saved correctly. Please try again.",
                )

            password_only = set(payload.keys()) <= {"password", "email"}
            if password_only:
                updated_user = _user_public_row(actual_user_id) or {"id": actual_user_id}
                if "name" not in updated_user or not updated_user.get("name"):
                    updated_user["name"] = updated_user.get("full_name") or (updated_user.get("email") or "").split("@")[0]
                return {"status": "success", "data": updated_user}

        if "email" in payload:
            email = (payload.get("email") or "").strip().lower()
            if email:
                existing_resp = supabase.table("users").select("id").eq("email", email).execute()
                existing_users = existing_resp.data or []
                for existing_user in existing_users:
                    if existing_user.get("id") != user_id:
                        raise HTTPException(status_code=409, detail="Email already in use by another user")
        update_payload = {}
        valid_fields = ["full_name", "email", "role", "department", "department_owner", "is_active"]
        for field in valid_fields:
            if field in payload:
                if field == "department_owner":
                    dept_owner = (payload.get("department_owner") or "").strip() or None
                    update_payload["department_owner"] = dept_owner
                elif field == "department":
                    dept = (payload.get("department") or "").strip() or None
                    update_payload["department"] = dept
                else:
                    update_payload[field] = payload[field]
        if "name" in payload and "full_name" not in payload:
            update_payload["full_name"] = payload["name"]
        if "role" in update_payload and users_has_roles_column():
            update_payload["roles"] = update_payload["role"]

        if not update_payload:
            raise HTTPException(status_code=400, detail="No valid fields to update")
        update_payload["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        actual_user_id = _resolve_user_db_id(user_id, effective_tenant_id)
        if not actual_user_id:
            raise HTTPException(status_code=404, detail="User not found")
        updated_user = update_table("users", update_payload, {"id": actual_user_id})
        if not updated_user:
            raise HTTPException(status_code=404, detail="User not found")
        if "role" in update_payload:
            role = update_payload.get("role")
            actual_user_id = updated_user.get("id") or user_id
            user_tenant_id = updated_user.get("tenant_id") or tenant_id or "00000000-0000-0000-0000-000000000001"
            # Dynamically map role by its actual name (fallback to Viewer)
            role_id = get_role_id_by_name(role, user_tenant_id) if role else None
            if not role_id:
                role_id = get_role_id_by_name("Viewer", user_tenant_id)
            if role_id:
                existing_roles = get_user_roles(actual_user_id, user_tenant_id)
                for existing_role in existing_roles:
                    existing_role_id = existing_role.get("role_id")
                    if existing_role_id:
                        success, _ = remove_role_from_user(actual_user_id, existing_role_id, user_tenant_id)
                        if not success:
                            logging.warning(f"Failed to remove existing role {existing_role_id} from user {actual_user_id}")
                auth_data = auth_guard(Authorization) if Authorization else None
                assigned_by = None
                if auth_data:
                    assigned_by = auth_data.get("user", {}).get("user_id") or auth_data.get("user", {}).get("id")
                assign_success = assign_role_to_user(actual_user_id, role_id, user_tenant_id, assigned_by)
                if not assign_success:
                    logging.warning(f"Failed to assign role {role} to user {actual_user_id} during update")
            else:
                logging.warning(f"Role '{role or 'Viewer'}' not found for tenant {user_tenant_id}")
        if "name" not in updated_user or not updated_user.get("name"):
            updated_user["name"] = updated_user.get("full_name") or (updated_user.get("email") or "").split("@")[0]
        return {"status": "success", "data": updated_user}
    except HTTPException:
        raise
    except Exception as e:
        error_response, status_code = handle_api_error(
            e,
            endpoint,
            context={"operation": "update_user", "user_id": user_id},
            include_traceback=False,
            user_message="Failed to update user"
        )
        raise HTTPException(status_code=status_code, detail=error_response["error"])

@router.delete("/users/{user_id}")
@require_permission("users_delete")
async def delete_user(
    user_id: str,
    tenant_id: str = Query('00000000-0000-0000-0000-000000000001'),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = f"/users/{user_id}"
    try:
        auth_data = auth_guard(Authorization)
        effective_tenant_id = auth_data.get("tenant_id") or tenant_id
        
        user_found = None
        try:
            uid_int = int(user_id)
            find_resp = supabase.table("users").select("id").eq("id", uid_int).eq("tenant_id", effective_tenant_id).limit(1).execute()
            if find_resp and getattr(find_resp, "data", None) and len(find_resp.data) > 0:
                user_found = find_resp.data[0].get("id")
        except Exception:
            pass
        if not user_found:
            try:
                find_resp = supabase.table("users").select("id").eq("id", user_id).eq("tenant_id", effective_tenant_id).limit(1).execute()
                if find_resp and getattr(find_resp, "data", None) and len(find_resp.data) > 0:
                    user_found = find_resp.data[0].get("id")
            except Exception:
                pass
        if not user_found:
            try:
                find_resp = supabase.table("users").select("id").eq("email", user_id).eq("tenant_id", effective_tenant_id).limit(1).execute()
                if find_resp and getattr(find_resp, "data", None) and len(find_resp.data) > 0:
                    user_found = find_resp.data[0].get("id")
            except Exception:
                pass
        if not user_found:
            raise HTTPException(status_code=404, detail="User not found")
        deleted = False
        try:
            resp = supabase.table("users").eq("id", user_found).eq("tenant_id", effective_tenant_id).delete().execute()
            if resp and not getattr(resp, "error", None):
                deleted = True
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to delete user: {str(e)}")
        if not deleted:
            raise HTTPException(status_code=400, detail="Delete operation did not succeed")
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        error_response, status_code = handle_api_error(
            e,
            endpoint,
            context={"operation": "delete_user", "user_id": user_id},
            include_traceback=False,
            user_message="Failed to delete user"
        )
        raise HTTPException(status_code=status_code, detail=error_response["error"])

@router.post("/invite")
@require_permission("users_create")
async def invite_user(request: Request, Authorization: Optional[str] = Header(default=None)):
    try:
        auth_data = auth_guard(Authorization)
        # Enforce tenant_id from token
        tenant_id = auth_data.get("tenant_id") or "00000000-0000-0000-0000-000000000001"
        
        payload = await request.json()
        email = (payload.get("email") or "").strip().lower()
        name = (payload.get("name") or "").strip()
        role = (payload.get("role") or "Viewer").strip()
        if not email:
            raise HTTPException(status_code=400, detail="Email is required")
        
        # Check if user already exists in this tenant
        existing_check = supabase.table("users").select("id").eq("email", email).eq("tenant_id", tenant_id).execute()
        if getattr(existing_check, "data", None) and len(existing_check.data) > 0:
             # User exists, maybe update? For now just log
             pass

        try:
            admin = getattr(supabase, "auth", None)
            admin = getattr(admin, "admin", None)
            if admin and hasattr(admin, "invite_user_by_email"):
                # Supabase invite (optional, depends on setup)
                # resp = admin.invite_user_by_email(email)
                pass
            else:
                pass
        except Exception as e:
            logging.warning(f"Admin invite attempt failed: {e}")
            
        email_sent = False
        try:
            smtp_host = os.getenv("SMTP_HOST")
            smtp_port = int(os.getenv("SMTP_PORT", "587"))
            smtp_user = os.getenv("SMTP_USER")
            smtp_pass = os.getenv("SMTP_PASS")
            smtp_from = os.getenv("SMTP_FROM", smtp_user or "noreply@example.com")
            if smtp_host and smtp_from:
                msg = EmailMessage()
                msg["Subject"] = "You're invited to Kaizen"
                msg["From"] = smtp_from
                msg["To"] = email
                msg.set_content(
                    f"Hello {name or email},\n\n"
                    f"You have been invited to Kaizen with role '{role}'. "
                    f"Please check your inbox for the Supabase invite or use the app's login with Microsoft (Azure).\n\n"
                    f"Thanks,\nKaizen Team"
                )
                with smtplib.SMTP(smtp_host, smtp_port) as server:
                    server.starttls()
                    if smtp_user and smtp_pass:
                        server.login(smtp_user, smtp_pass)
                    server.send_message(msg)
                email_sent = True
            else:
                logging.info("SMTP not configured; skipping direct email send")
        except Exception as e:
            logging.warning(f"SMTP send failed: {e}")
            
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        upsert = {
            "email": email,
            "full_name": name or email.split("@")[0],
            "role": role,
            "is_active": False,
            "created_at": now,
            "updated_at": now,
            "sso_provider": "azure",
            "sso_user_id": payload.get("sso_user_id") or None,
            "login_count": 0,
            "tenant_id": tenant_id,
        }
        try:
            # Check existing by email AND tenant_id
            existing = supabase.table("users").select("id").eq("email", email).eq("tenant_id", tenant_id).execute()
            if getattr(existing, "data", None) and len(existing.data) > 0:
                user_id = existing.data[0].get("id")
                supabase.table("users").update({
                    "full_name": upsert["full_name"],
                    "role": upsert["role"],
                    "is_active": upsert["is_active"],
                    "updated_at": upsert["updated_at"],
                    "sso_provider": upsert["sso_provider"],
                    "sso_user_id": upsert["sso_user_id"],
                    # Don't update tenant_id, it should match
                }).eq("id", user_id).eq("tenant_id", tenant_id).execute()
            else:
                supabase.table("users").insert(upsert, returning="representation").execute()
        except Exception as upsert_error:
            logging.warning(f"User upsert/insert failed: {upsert_error}")
            raise HTTPException(status_code=500, detail=f"Failed to invite user: {str(upsert_error)}")
            
        return {"status": "success", "message": "Invitation processed", "email_sent": email_sent}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/users/{user_id}/roles")
async def get_user_roles_endpoint(
    user_id: str,
    tenant_id: str = Query(default="00000000-0000-0000-0000-000000000001"),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = f"/users/{user_id}/roles"
    try:
        auth_data = auth_guard(Authorization)
        user = auth_data.get("user", {})
        current_user_id = user.get("user_id") or user.get("id")
        
        # Secure tenant logic
        token_tenant_id = auth_data.get("tenant_id")
        effective_tenant = token_tenant_id or tenant_id or "00000000-0000-0000-0000-000000000001"
        
        if tenant_id and tenant_id != token_tenant_id:
            if is_global_superadmin(current_user_id):
                effective_tenant = tenant_id
            else:
                effective_tenant = token_tenant_id
        
        if current_user_id and current_user_id != user_id:
            if not is_global_superadmin(current_user_id):
                has_permission = check_permission(current_user_id, effective_tenant, "roles", "retrieve")
                if not has_permission:
                    raise HTTPException(status_code=403, detail="You do not have permission to retrieve roles")
        
        roles = get_user_roles(user_id, effective_tenant)

        for role in roles:
            role_id = role.get("role_id")
            if not role_id:
                continue

            role_tenant_id = None
            roles_data = role.get("roles")
            if isinstance(roles_data, dict):
                role_tenant_id = roles_data.get("tenant_id")
            elif isinstance(roles_data, list) and len(roles_data) > 0:
                role_tenant_id = roles_data[0].get("tenant_id")

            effective_role_tenant = role_tenant_id or effective_tenant
            permissions = get_role_permissions(role_id, effective_role_tenant)

            if roles_data:
                if isinstance(roles_data, dict):
                    roles_data["permissions"] = permissions
                else:
                    role["roles"] = {"permissions": permissions}
            else:
                role["permissions"] = permissions

        return {"data": roles, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "get_user_roles", return_dict=True, user_id=user_id, tenant_id=tenant_id)

@router.post("/users/{user_id}/roles")
@require_permission("roles_update")
async def assign_role_to_user_endpoint(
    user_id: str,
    request: Request,
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = f"/users/{user_id}/roles"
    payload: Dict[str, Any] = {}
    try:
        payload = await request.json()
        auth_data = auth_guard(Authorization)
        assigned_by = auth_data.get("user", {}).get("user_id") or auth_data.get("user", {}).get("id")
        role_id = payload.get("role_id")
        
        # Secure tenant logic
        token_tenant_id = auth_data.get("tenant_id")
        requested_tenant_id = payload.get("tenant_id")
        tenant_id = token_tenant_id or "00000000-0000-0000-0000-000000000001"
        
        if requested_tenant_id and requested_tenant_id != token_tenant_id:
            if is_global_superadmin(assigned_by):
                tenant_id = requested_tenant_id
            # Else ignore requested and use token tenant
            
        if not role_id:
            raise HTTPException(status_code=400, detail="role_id is required")
        success = assign_role_to_user(user_id, role_id, tenant_id, assigned_by)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to assign role")
        return {"data": {"success": True}, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "assign_role_to_user", return_dict=True, user_id=user_id, role_id=payload.get("role_id"))

@router.delete("/users/{user_id}/roles/{role_id}")
@require_permission("roles_update")
async def remove_role_from_user_endpoint(
    user_id: str,
    role_id: str,
    tenant_id: str = Query(default="00000000-0000-0000-0000-000000000001"),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = f"/users/{user_id}/roles/{role_id}"
    try:
        auth_data = auth_guard(Authorization)
        current_user_id = auth_data.get("user_id") or auth_data.get("user", {}).get("id")
        
        # Secure tenant logic
        token_tenant_id = auth_data.get("tenant_id")
        effective_tenant = token_tenant_id or tenant_id or "00000000-0000-0000-0000-000000000001"
        
        if tenant_id and tenant_id != token_tenant_id:
            if is_global_superadmin(current_user_id):
                effective_tenant = tenant_id
            else:
                effective_tenant = token_tenant_id
                
        success, error_message = remove_role_from_user(user_id, role_id, effective_tenant)
        if not success and current_user_id and is_global_superadmin(current_user_id):
            success, error_message = remove_role_from_user_any_tenant(user_id, role_id)
        if not success:
            raise HTTPException(status_code=400, detail=error_message or "Failed to remove role")
        return {"data": {"success": True}, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "remove_role_from_user", return_dict=True, user_id=user_id, role_id=role_id, tenant_id=tenant_id)


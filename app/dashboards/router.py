from fastapi import APIRouter, HTTPException, Header, Query
from typing import Optional, Dict, Any, List, cast
from datetime import datetime, timezone
import logging
from services.db_service import execute_query, local_db as supabase
from services.rbac_service import is_superadmin
from services.auth_service import get_user_from_token, auth_guard
from services.rbac_service import require_permission
from utils.error_handler import handle_endpoint_error

router = APIRouter()


def get_user_department_info_by_email(email: str) -> Dict[str, Optional[str]]:
    try:
        if not email or not email.strip():
            return {"department": None, "department_owner": None}
        resp = supabase.table("users").select("department, department_owner").eq("email", email.strip().lower()).limit(1).execute()
        if resp.data and len(resp.data) > 0:
            user_data = resp.data[0]
            return {
                "department": user_data.get("department"),
                "department_owner": user_data.get("department_owner")
            }
        return {"department": None, "department_owner": None}
    except Exception:
        return {"department": None, "department_owner": None}

def _count_table(table_name: str, select_col: str = '"id"', tenant_id: str = None):
    try:
        logging.info(f"Querying table: {table_name} using column {select_col!r}")
        query = supabase.table(table_name).select(select_col, count="exact")
        if tenant_id:
            query = query.eq("tenant_id", tenant_id)
            
        resp = query.execute()
        if hasattr(resp, "error") and resp.error:
            logging.warning(f"Column {select_col!r} failed on {table_name}: {resp.error}")
            if "bug" in table_name.lower() or table_name.lower().startswith("bugs"):
                fallback_col = '"Bug ID"'
            else:
                fallback_col = '"id"'
            logging.info(f"Trying fallback column {fallback_col!r} for table {table_name}")
            query = supabase.table(table_name).select(fallback_col, count="exact")
            if tenant_id:
                query = query.eq("tenant_id", tenant_id)
            resp = query.execute()
            if hasattr(resp, "error") and resp.error:
                error_msg = f"Both {select_col!r} and fallback {fallback_col!r} failed: {resp.error}"
                logging.error(error_msg)
                return 0, error_msg
        count_attr = getattr(resp, "count", None)
        if count_attr is not None:
            count = int(count_attr)
            return count, None
        if isinstance(resp, dict) and resp.get("count") is not None:
            count = int(resp["count"])
            return count, None
        data = getattr(resp, "data", None)
        if data is None and isinstance(resp, dict):
            data = resp.get("data", [])
        if data is None:
            data = []
        count = len(data or [])
        return count, None
    except Exception as e:
        error_msg = f"Exception while counting {table_name}: {str(e)}"
        logging.exception(f"Error counting table {table_name}: {e}")
        return 0, error_msg

@router.get("/counts")
@require_permission("dashboard_retrieve")
def get_counts(Authorization: Optional[str] = Header(default=None)):
    try:
        auth_data = auth_guard(Authorization)
        tenant_id = auth_data.get("tenant_id")
        
        total_bugs, _ = _count_table("Bugs_file", select_col="*", tenant_id=tenant_id)
        total_users, _ = _count_table("users", tenant_id=tenant_id)
        transaction_tracker, _ = _count_table("transtrackers", tenant_id=tenant_id)
        if transaction_tracker == 0:
            alt_count, _ = _count_table("transtracker", tenant_id=tenant_id)
            if alt_count == 0:
                alt_count2, _ = _count_table("transactions", tenant_id=tenant_id)
                transaction_tracker = alt_count2
            else:
                transaction_tracker = alt_count
        security_controls, _ = _count_table("security_controls", tenant_id=tenant_id)
        response = {
            "status": "success",
            "data": {
                "total_bugs": total_bugs,
                "users": total_users,
                "transactions": transaction_tracker,
                "security_alerts": security_controls,
            },
        }
        return response
    except Exception as e:
        error_detail = f"Error in /counts: {str(e)}"
        logging.exception(error_detail)
        return {"status": "error", "detail": error_detail}, 500

PRIORITY_COLUMN_CANDIDATES = ["Priority", "priority", "severity", "Severity"]

def _classify_priority_value(val: Any) -> str:
    s = str(val or "").strip().lower()
    if any(k in s for k in ["critical", "crit", "p0", "p1", "high"]):
        return "high"
    if any(k in s for k in ["medium", "med", "p2"]):
        return "medium"
    return "low"

def _pick_priority_value(row: Dict[str, Any]) -> Any:
    if not isinstance(row, dict):
        return None
    for c in PRIORITY_COLUMN_CANDIDATES:
        if c in row:
            return row[c]
    normalized_keys = {k.strip().lower().replace(" ", "_"): k for k in row.keys()}
    for candidate in ("priority", "bug_priority", "severity"):
        if candidate in normalized_keys:
            return row[normalized_keys[candidate]]
    for v in row.values():
        if v is not None:
            return v
    return None

def _normalize_resp_to_rows(resp: Any) -> List[Dict[str, Any]]:
    if resp is None:
        return []
    if isinstance(resp, dict):
        return resp.get("data") or []
    return getattr(resp, "data", None) or []

@router.get("/priority-stats")
@require_permission("dashboard_retrieve")
def get_priority_stats(Authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    auth_data = auth_guard(Authorization)
    tenant_id = auth_data.get("tenant_id")
    
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase client not configured on server")
    rows: List[Dict[str, Any]] = []
    try:
        try:
            resp = supabase.table("Bugs_file").select("*").eq("tenant_id", tenant_id).limit(5000).execute()
        except:
            resp = supabase.from_("Bugs_file").select("*").eq("tenant_id", tenant_id).limit(5000).execute()
        if isinstance(resp, dict) and resp.get("error"):
            rows = []
        else:
            rows_raw = _normalize_resp_to_rows(resp)
            rows = [r for r in rows_raw if isinstance(r, dict)]
    except Exception:
        rows = []
    high = medium = low = 0
    for r in rows:
        val = _pick_priority_value(r)
        cls = _classify_priority_value(val)
        if cls == "high":
            high += 1
        elif cls == "medium":
            medium += 1
        else:
            low += 1
    total = high + medium + low
    data_map = {"high": int(high), "medium": int(medium), "low": int(low), "total": int(total)}
    bar_data = [
        {"priority": "High", "count": int(high)},
        {"priority": "Medium", "count": int(medium)},
        {"priority": "Low", "count": int(low)},
    ]
    return {"status": "success", "data_map": data_map, "bar_data": bar_data}

@router.get("/dashboard/tasks/metrics")
@require_permission("dashboard_retrieve")
async def get_task_metrics(
    tenant_id: str = Query('00000000-0000-0000-0000-000000000001'),
    organization: Optional[List[str]] = Query(None),
    certification: Optional[List[str]] = Query(None),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = "/dashboard/tasks/metrics"
    try:
        auth_data = auth_guard(Authorization)
        tenant_id = auth_data.get("tenant_id") or tenant_id
        user = auth_data.get("user", {}) or {}
        user_id = user.get("id") or user.get("user", {}).get("id")
        is_admin = is_superadmin(user_id, tenant_id) if user_id else False
        
        query = supabase.table("tasks").select("*").eq("tenant_id", tenant_id)
        
        # Apply filters
        if organization:
            try:
                query = query.in_("organization", organization)
            except Exception as e:
                logging.error(f"Error filtering by organization: {e}")
                pass
            
        if certification:
            # Tasks don't have certification directly, so we filter by control_id
            # First fetch controls with these certifications
            controls_resp = supabase.table("security_controls").select("id").eq("tenant_id", tenant_id).in_("certification", certification).execute()
            if getattr(controls_resp, "error", None):
                logging.error(f"Error fetching controls for certification filter: {controls_resp.error}")
            else:
                control_data = controls_resp.data or []
                control_ids = [c.get("id") for c in control_data if c.get("id")]
                if control_ids:
                    query = query.in_("control_id", control_ids)
                else:
                    # If no controls match, then no tasks match
                    # We can force an empty result by filtering by a dummy ID
                    query = query.eq("id", "00000000-0000-0000-0000-000000000000")

        if not is_admin:
            query = query.eq("is_deleted", False)
            
        resp = query.execute()
        if getattr(resp, "error", None):
            error_str = str(resp.error)
            if "is_deleted" in error_str.lower() and ("column" in error_str.lower() or "does not exist" in error_str.lower()):
                query = supabase.table("tasks").select("*").eq("tenant_id", tenant_id)
                resp = query.execute()
                if getattr(resp, "error", None):
                    raise HTTPException(status_code=400, detail=str(resp.error))
            else:
                raise HTTPException(status_code=400, detail=str(resp.error))
        tasks = resp.data or []
        tasks = [t for t in tasks if isinstance(t, dict)]
        total_tasks = len(tasks)
        tasks_vs_assignees_ageing = {}
        tasks_vs_assignee_vs_priority = {}
        priority_vs_ageing_vs_assignee = {}
        for task in tasks:
            assignee = task.get("assigned_to") or "Unassigned"
            priority = task.get("task_priority") or "Unknown"
            created_at_str = task.get("created_at") or task.get("updated_at")
            age_days = None
            age_bucket = "Unknown"
            if created_at_str:
                try:
                    if isinstance(created_at_str, str):
                        try:
                            created_date = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                        except:
                            try:
                                created_date = datetime.strptime(created_at_str.split('T')[0], '%Y-%m-%d')
                            except:
                                created_date = datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S')
                    else:
                        created_date = created_at_str
                    if created_date.tzinfo is None:
                        created_date = created_date.replace(tzinfo=timezone.utc)
                    age_days = (datetime.now(timezone.utc) - created_date).days
                    if age_days < 30:
                        age_bucket = "0-30 days"
                    elif age_days < 90:
                        age_bucket = "31-90 days"
                    elif age_days < 180:
                        age_bucket = "91-180 days"
                    elif age_days < 365:
                        age_bucket = "181-365 days"
                    else:
                        age_bucket = "365+ days"
                except Exception:
                    age_bucket = "Unknown"
            if assignee not in tasks_vs_assignees_ageing:
                tasks_vs_assignees_ageing[assignee] = {}
            tasks_vs_assignees_ageing[assignee][age_bucket] = tasks_vs_assignees_ageing[assignee].get(age_bucket, 0) + 1
            if assignee not in tasks_vs_assignee_vs_priority:
                tasks_vs_assignee_vs_priority[assignee] = {}
            tasks_vs_assignee_vs_priority[assignee][priority] = tasks_vs_assignee_vs_priority[assignee].get(priority, 0) + 1
            if priority not in priority_vs_ageing_vs_assignee:
                priority_vs_ageing_vs_assignee[priority] = {}
            if age_bucket not in priority_vs_ageing_vs_assignee[priority]:
                priority_vs_ageing_vs_assignee[priority][age_bucket] = {}
            priority_vs_ageing_vs_assignee[priority][age_bucket][assignee] = priority_vs_ageing_vs_assignee[priority][age_bucket].get(assignee, 0) + 1
        formatted_tasks_vs_assignees_ageing = []
        for assignee, age_buckets in tasks_vs_assignees_ageing.items():
            for age_bucket, count in age_buckets.items():
                formatted_tasks_vs_assignees_ageing.append({
                    "assignee": assignee,
                    "age_bucket": age_bucket,
                    "count": count
                })
        formatted_tasks_vs_assignee_vs_priority = []
        for assignee, priorities in tasks_vs_assignee_vs_priority.items():
            for priority, count in priorities.items():
                formatted_tasks_vs_assignee_vs_priority.append({
                    "assignee": assignee,
                    "priority": priority,
                    "count": count
                })
        formatted_priority_vs_ageing_vs_assignee = []
        for priority, age_buckets in priority_vs_ageing_vs_assignee.items():
            for age_bucket, assignees in age_buckets.items():
                for assignee, count in assignees.items():
                    formatted_priority_vs_ageing_vs_assignee.append({
                        "priority": priority,
                        "age_bucket": age_bucket,
                        "assignee": assignee,
                        "count": count
                    })
        return {
            "data": {
                "total": total_tasks,
                "tasks_vs_assignees_ageing": formatted_tasks_vs_assignees_ageing,
                "tasks_vs_assignee_vs_priority": formatted_tasks_vs_assignee_vs_priority,
                "priority_vs_ageing_vs_assignee": formatted_priority_vs_ageing_vs_assignee
            },
            "error": None
        }
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "get_task_metrics", return_dict=True, tenant_id=tenant_id)

@router.get("/dashboard/controls/metrics")
@require_permission("dashboard_retrieve")
async def get_controls_metrics(
    tenant_id: str = Query('00000000-0000-0000-0000-000000000001'),
    organization: Optional[List[str]] = Query(None),
    certification: Optional[List[str]] = Query(None),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = "/dashboard/controls/metrics"
    try:
        auth_data = auth_guard(Authorization)
        tenant_id = auth_data.get("tenant_id") or tenant_id
        user = auth_data.get("user", {})
        user_id = user.get("id") or user.get("user", {}).get("id")
        is_admin = is_superadmin(user_id, tenant_id) if user_id else False
        query = supabase.table("security_controls").select("*").eq("tenant_id", tenant_id)

        # Apply filters
        if organization:
            try:
                query = query.in_("organization", organization)
            except Exception as e:
                logging.error(f"Error filtering by organization: {e}")
                pass

        if certification:
            query = query.in_("certification", certification)
            
        resp = query.execute()
        if getattr(resp, "error", None):
            raise HTTPException(status_code=400, detail=str(resp.error))
        controls = resp.data or []
        controls = [c for c in controls if isinstance(c, dict)]
        if not is_admin:
            filtered_controls = []
            for control in controls:
                is_deleted = control.get("is_deleted")
                if is_deleted is not True:
                    filtered_controls.append(control)
            controls = filtered_controls
        total_controls = len(controls)
        status_vs_assignee = {}
        status_vs_domain = {}
        dept_deptowner_vs_status = {}
        for control in controls:
            control_status = control.get("Status") or "Unknown"
            control_domain = control.get("control_domain") or "Unknown"
            control_owner = control.get("owner") or "Unassigned"
            control_department = control.get("department")
            control_dept_owner = None
            if control_owner and control_owner != "Unassigned":
                dept_info = get_user_department_info_by_email(control_owner)
                if not control_department:
                    control_department = dept_info.get("department")
                control_dept_owner = dept_info.get("department_owner")
            control_department = control_department or "Unknown"
            control_dept_owner = control_dept_owner or "Unknown"
            if control_status not in status_vs_assignee:
                status_vs_assignee[control_status] = {}
            status_vs_assignee[control_status][control_owner] = status_vs_assignee[control_status].get(control_owner, 0) + 1
            if control_status not in status_vs_domain:
                status_vs_domain[control_status] = {}
            status_vs_domain[control_status][control_domain] = status_vs_domain[control_status].get(control_domain, 0) + 1
            dept_key = (control_department, control_dept_owner)
            if dept_key not in dept_deptowner_vs_status:
                dept_deptowner_vs_status[dept_key] = {}
            dept_deptowner_vs_status[dept_key][control_status] = dept_deptowner_vs_status[dept_key].get(control_status, 0) + 1
        formatted_status_vs_assignee = []
        for status, assignees in status_vs_assignee.items():
            for assignee, count in assignees.items():
                formatted_status_vs_assignee.append({
                    "status": status,
                    "assignee": assignee,
                    "count": count
                })
        formatted_status_vs_domain = []
        for status, domains in status_vs_domain.items():
            for domain, count in domains.items():
                if domain != "Unknown":
                    formatted_status_vs_domain.append({
                        "status": status,
                        "domain": domain,
                        "count": count
                    })
        formatted_dept_deptowner_vs_status = []
        for (department, dept_owner), statuses in dept_deptowner_vs_status.items():
            for status, count in statuses.items():
                formatted_dept_deptowner_vs_status.append({
                    "department": department,
                    "dept_owner": dept_owner,
                    "status": status,
                    "count": count
                })
        compliance_rate = 0
        if total_controls > 0:
            active_statuses = ["Active", "Implemented", "Complete", "Compliant"]
            active_count = sum(
                item["count"] for item in formatted_status_vs_assignee
                if item["status"] in active_statuses
            )
            compliance_rate = round((active_count / total_controls) * 100, 1)
        return {
            "data": {
                "total_controls": total_controls,
                "status_vs_assignee": formatted_status_vs_assignee,
                "status_vs_domain": formatted_status_vs_domain,
                "dept_deptowner_vs_status": formatted_dept_deptowner_vs_status,
                "compliance_rate": compliance_rate
            },
            "error": None
        }
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "get_controls_metrics", return_dict=True, tenant_id=tenant_id)

@router.get("/dashboard/metrics")
@require_permission("dashboard_retrieve")
async def get_combined_dashboard_metrics(
    tenant_id: str = Query('00000000-0000-0000-0000-000000000001'),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = "/dashboard/metrics"
    try:
        auth_data = auth_guard(Authorization)
        user = auth_data.get("user", {})
        user_id = user.get("id") or user.get("user", {}).get("id")
        is_admin = is_superadmin(user_id, tenant_id) if user_id else False
        task_query = supabase.table("tasks").select("*").eq("tenant_id", tenant_id)
        if not is_admin:
            task_query = task_query.eq("is_deleted", False)
        task_resp = task_query.execute()
        if getattr(task_resp, "error", None):
            error_str = str(task_resp.error)
            if "is_deleted" in error_str.lower() and ("column" in error_str.lower() or "does not exist" in error_str.lower()):
                task_query = supabase.table("tasks").select("*").eq("tenant_id", tenant_id)
                task_resp = task_query.execute()
                if getattr(task_resp, "error", None):
                    raise HTTPException(status_code=400, detail=str(task_resp.error))
            else:
                raise HTTPException(status_code=400, detail=str(task_resp.error))
        tasks = task_resp.data or []
        tasks = [t for t in tasks if isinstance(t, dict)]
        total_tasks = len(tasks)
        control_query = supabase.table("security_controls").select("*").eq("tenant_id", tenant_id)
        control_resp = control_query.execute()
        if getattr(control_resp, "error", None):
            raise HTTPException(status_code=400, detail=str(control_resp.error))
        controls = control_resp.data or []
        controls = [c for c in controls if isinstance(c, dict)]
        if not is_admin:
            filtered_controls = []
            for control in controls:
                is_deleted = control.get("is_deleted")
                if is_deleted is not True:
                    filtered_controls.append(control)
            controls = filtered_controls
        total_controls = len(controls)
        compliance_rate = 0
        if total_controls > 0:
            active_statuses = ["Active", "Implemented", "Complete", "Compliant"]
            active_count = sum(1 for control in controls if control.get("Status") in active_statuses)
            compliance_rate = round((active_count / total_controls) * 100, 1)
        return {
            "data": {
                "tasks": {
                    "total": total_tasks
                },
                "controls": {
                    "total_controls": total_controls,
                    "compliance_rate": compliance_rate
                }
            },
            "error": None
        }
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "get_combined_dashboard_metrics", return_dict=True, tenant_id=tenant_id)

@router.get("/dashboard/controls/by-certifications")
@router.get("/dashboard/controls/by-certifications")
@require_permission("dashboard_retrieve")
async def get_controls_by_certifications(
    tenant_id: str = Query('00000000-0000-0000-0000-000000000001'),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = "/dashboard/controls/by-certifications"
    try:
        auth_data = auth_guard(Authorization)
        user = auth_data.get("user", {})
        user_id = user.get("id") or user.get("user", {}).get("id")
        is_admin = is_superadmin(user_id, tenant_id) if user_id else False
        query = supabase.table("security_controls").select("*").eq("tenant_id", tenant_id)
        resp = query.execute()
        if getattr(resp, "error", None):
            raise HTTPException(status_code=400, detail=str(resp.error))
        controls = resp.data or []
        if not is_admin:
            filtered_controls = []
            for control in controls:
                is_deleted = control.get("is_deleted")
                if is_deleted is not True:
                    filtered_controls.append(control)
            controls = filtered_controls
        cert_columns = ["ISO_27001", "NIST_CSF", "SOC_2", "GDPR", "PCI_DSS", "HIPAA", "IT_Act_2000"]
        cert_metrics = {}
        for cert in cert_columns:
            cert_metrics[cert] = {
                "total_controls": 0,
                "by_status": {},
                "by_priority": {},
                "by_domain": {},
                "by_owner": {},
                "controls_list": []
            }
        for control in controls:
            control_status = control.get("Status") or "Unknown"
            control_priority = control.get("Priority") or "Unknown"
            control_domain = control.get("control_domain") or "Unknown"
            control_owner = control.get("owner") or "Unassigned"
            control_id = control.get("id") or ""
            for cert in cert_columns:
                cert_value = control.get(cert)
                if cert_value and str(cert_value).strip() and str(cert_value).strip().lower() not in ["", "n/a", "none", "null"]:
                    cert_metrics[cert]["total_controls"] += 1
                    cert_metrics[cert]["by_status"][control_status] = cert_metrics[cert]["by_status"].get(control_status, 0) + 1
                    cert_metrics[cert]["by_priority"][control_priority] = cert_metrics[cert]["by_priority"].get(control_priority, 0) + 1
                    cert_metrics[cert]["by_domain"][control_domain] = cert_metrics[cert]["by_domain"].get(control_domain, 0) + 1
                    cert_metrics[cert]["by_owner"][control_owner] = cert_metrics[cert]["by_owner"].get(control_owner, 0) + 1
                    cert_metrics[cert]["controls_list"].append({
                        "id": control_id,
                        "status": control_status,
                        "priority": control_priority,
                        "domain": control_domain,
                        "owner": control_owner
                    })
        status_assignee_matrix = {}
        aging_by_assignee = {}
        for cert in cert_columns:
            status_assignee_matrix[cert] = {}
            aging_by_assignee[cert] = {}
        for control in controls:
            control_status = control.get("Status") or "Unknown"
            control_owner = control.get("owner") or "Unassigned"
            created_at_str = control.get("created_at") or control.get("Date") or control.get("Review_Date") or control.get("last_review_date")
            age_days = None
            if created_at_str:
                try:
                    if isinstance(created_at_str, str):
                        try:
                            created_date = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                        except:
                            try:
                                created_date = datetime.strptime(created_at_str.split('T')[0], '%Y-%m-%d')
                            except:
                                created_date = datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S')
                    else:
                        created_date = created_at_str
                    if created_date.tzinfo is None:
                        created_date = created_date.replace(tzinfo=timezone.utc)
                    age_days = (datetime.now(timezone.utc) - created_date).days
                except Exception:
                    age_days = None
            age_bucket = "Unknown"
            if age_days is not None:
                if age_days < 30:
                    age_bucket = "0-30 days"
                elif age_days < 90:
                    age_bucket = "31-90 days"
                elif age_days < 180:
                    age_bucket = "91-180 days"
                elif age_days < 365:
                    age_bucket = "181-365 days"
                else:
                    age_bucket = "365+ days"
            for cert in cert_columns:
                cert_value = control.get(cert)
                if cert_value and str(cert_value).strip() and str(cert_value).strip().lower() not in ["", "n/a", "none", "null"]:
                    if control_status not in status_assignee_matrix[cert]:
                        status_assignee_matrix[cert][control_status] = {}
                    status_assignee_matrix[cert][control_status][control_owner] = status_assignee_matrix[cert][control_status].get(control_owner, 0) + 1
                    if control_owner not in aging_by_assignee[cert]:
                        aging_by_assignee[cert][control_owner] = {}
                    aging_by_assignee[cert][control_owner][age_bucket] = aging_by_assignee[cert][control_owner].get(age_bucket, 0) + 1
        formatted_metrics = []
        for cert in cert_columns:
            metrics = cert_metrics[cert]
            status_assignee_data = []
            for status, assignees in status_assignee_matrix[cert].items():
                for assignee, count in assignees.items():
                    status_assignee_data.append({
                        "status": status,
                        "assignee": assignee,
                        "count": count
                    })
            aging_data = []
            for assignee, age_buckets in aging_by_assignee[cert].items():
                for age_bucket, count in age_buckets.items():
                    aging_data.append({
                        "assignee": assignee,
                        "age_bucket": age_bucket,
                        "count": count
                    })
            formatted_metrics.append({
                "certification": cert,
                "total_controls": metrics["total_controls"],
                "by_status": [
                    {"status": status, "count": count}
                    for status, count in sorted(metrics["by_status"].items(), key=lambda x: x[1], reverse=True)
                ],
                "by_priority": [
                    {"priority": priority, "count": count}
                    for priority, count in sorted(metrics["by_priority"].items(), key=lambda x: x[1], reverse=True)
                ],
                "by_domain": [
                    {"domain": domain, "count": count}
                    for domain, count in sorted(metrics["by_domain"].items(), key=lambda x: x[1], reverse=True)
                    if domain != "Unknown"
                ],
                "by_owner": [
                    {"owner": owner, "count": count}
                    for owner, count in sorted(metrics["by_owner"].items(), key=lambda x: x[1], reverse=True)
                    if owner != "Unassigned"
                ][:5],
                "status_vs_assignee": status_assignee_data,
                "aging_by_assignee": aging_data,
                "compliance_rate": 0
            })
            total = metrics["total_controls"]
            if total > 0:
                active_count = sum(
                    count for status, count in metrics["by_status"].items()
                    if status in ["Active", "Implemented", "Complete", "Compliant"]
                )
                formatted_metrics[-1]["compliance_rate"] = round((active_count / total) * 100, 1)
        return {
            "data": {
                "total_controls": len(controls),
                "by_certification": formatted_metrics
            },
            "error": None
        }
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "get_controls_by_certifications", return_dict=True, tenant_id=tenant_id)

@router.get("/dashboard/certifications/metrics")
@require_permission("dashboard_retrieve")
async def get_certifications_metrics(
    tenant_id: str = Query('00000000-0000-0000-0000-000000000001'),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = "/dashboard/certifications/metrics"
    try:
        auth_data = auth_guard(Authorization)
        user = auth_data.get("user", {})
        user_id = auth_data.get("user_id") or user.get("user_id")
        is_admin = is_superadmin(user_id, tenant_id) if user_id else False
        query = supabase.table("certifications").select("*").eq("tenant_id", tenant_id)
        if not is_admin:
            query = query.eq("is_deleted", False)
        resp = query.execute()
        if getattr(resp, "error", None):
            raise HTTPException(status_code=400, detail=str(resp.error))
        certifications = resp.data or []
        certifications = [c for c in certifications if isinstance(c, dict)]
        status_counts = {}
        type_counts = {}
        expiry_counts = {"expired": 0, "expiring_soon": 0, "active": 0, "no_expiry": 0}
        total_certs = len(certifications)
        today = datetime.now(timezone.utc).date()
        for cert in certifications:
            status = cert.get("status") or "Unknown"
            status_counts[status] = status_counts.get(status, 0) + 1
            cert_type = cert.get("certification_type") or "Unknown"
            type_counts[cert_type] = type_counts.get(cert_type, 0) + 1
            expiry_date_str = cert.get("expiry_date")
            if expiry_date_str:
                try:
                    if isinstance(expiry_date_str, str):
                        expiry_date = datetime.fromisoformat(expiry_date_str.replace('Z', '+00:00')).date()
                    else:
                        expiry_date = expiry_date_str
                    days_until_expiry = (expiry_date - today).days
                    if days_until_expiry < 0:
                        expiry_counts["expired"] += 1
                    elif days_until_expiry <= 30:
                        expiry_counts["expiring_soon"] += 1
                    else:
                        expiry_counts["active"] += 1
                except:
                    expiry_counts["no_expiry"] += 1
            else:
                expiry_counts["no_expiry"] += 1
        return {
            "data": {
                "total": total_certs,
                "by_status": [{"status": k, "count": v} for k, v in status_counts.items()],
                "by_type": [{"type": k, "count": v} for k, v in type_counts.items()],
                "by_expiry": [
                    {"category": k, "count": v}
                    for k, v in expiry_counts.items()
                    if v > 0
                ]
            },
            "error": None
        }
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "get_certifications_metrics", return_dict=True, tenant_id=tenant_id)

@router.get("/dashboard/kpi/metrics")
@require_permission("dashboard_retrieve")
async def get_kpi_metrics(
    tenant_id: str = Query('00000000-0000-0000-0000-000000000001'),
    Authorization: Optional[str] = Header(default=None)
):
    endpoint = "/dashboard/kpi/metrics"
    try:
        auth_data = auth_guard(Authorization)
        user = auth_data.get("user", {})
        user_id = user.get("id") or user.get("user", {}).get("id")
        is_admin = is_superadmin(user_id, tenant_id) if user_id else False
        cert_query = supabase.table("certifications").select("*").eq("tenant_id", tenant_id)
        if not is_admin:
            cert_query = cert_query.eq("is_deleted", False)
        cert_resp = cert_query.execute()
        if getattr(cert_resp, "error", None):
            raise HTTPException(status_code=400, detail=f"Error fetching certifications: {str(cert_resp.error)}")
        certifications = cert_resp.data or []
        standards_count = len(certifications)
        controls_query = supabase.table("security_controls").select("*").eq("tenant_id", tenant_id)
        controls_resp = controls_query.execute()
        if getattr(controls_resp, "error", None):
            raise HTTPException(status_code=400, detail=f"Error fetching controls: {str(controls_resp.error)}")
        controls = controls_resp.data or []
        if not is_admin:
            filtered_controls = []
            for control in controls:
                is_deleted = control.get("is_deleted")
                if is_deleted is not True:
                    filtered_controls.append(control)
            controls = filtered_controls
        total_controls = len(controls)
        compliance_rate = 0
        if total_controls > 0:
            active_statuses = ["Active", "Implemented", "Complete", "Compliant"]
            active_count = sum(
                1 for control in controls
                if (control.get("Status") or "Unknown") in active_statuses
            )
            compliance_rate = round((active_count / total_controls) * 100, 1)
        tasks_query = supabase.table("tasks").select("*").eq("tenant_id", tenant_id)
        if not is_admin:
            tasks_query = tasks_query.eq("is_deleted", False)
        tasks_resp = tasks_query.execute()
        if getattr(tasks_resp, "error", None):
            error_str = str(tasks_resp.error)
            if "is_deleted" in error_str.lower() and ("column" in error_str.lower() or "does not exist" in error_str.lower()):
                tasks_query = supabase.table("tasks").select("*").eq("tenant_id", tenant_id)
                tasks_resp = tasks_query.execute()
                if getattr(tasks_resp, "error", None):
                    raise HTTPException(status_code=400, detail=f"Error fetching tasks: {str(tasks_resp.error)}")
            else:
                raise HTTPException(status_code=400, detail=f"Error fetching tasks: {str(tasks_resp.error)}")
        tasks = tasks_resp.data or []
        risk_tasks = [
            task for task in tasks
            if task.get("task_type") and task.get("task_type").lower() == "risk"
        ]
        total_risks = len(risk_tasks)
        open_statuses = ['open', 'inprogress', 'in progress', 'on hold', 'onhold']
        open_risks = sum(
            1 for task in risk_tasks
            if task.get("task_status") and task.get("task_status").lower() in [s.lower() for s in open_statuses]
        )
        closed_statuses = ['closed', 'completed', 'done', 'resolved']
        closed_risks = sum(
            1 for task in risk_tasks
            if task.get("task_status") and task.get("task_status").lower() in [s.lower() for s in closed_statuses]
        )
        risk_score = 0
        if total_risks > 0:
            risk_score = round((open_risks / total_risks) * 100, 1)
        return {
            "data": {
                "standards_count": standards_count,
                "total_controls": total_controls,
                "compliance_score": compliance_rate,
                "total_risks": total_risks,
                "open_risks": open_risks,
                "closed_risks": closed_risks,
                "risk_score": risk_score
            },
            "error": None
        }
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "get_kpi_metrics", return_dict=True, tenant_id=tenant_id)


from fastapi import APIRouter, HTTPException, UploadFile, File, Depends, Query, Body, Header
from typing import Optional, List, Dict, Any
from services.auth_service import get_user_from_token
from services.testcase_service import TestcaseService
from utils.error_handler import handle_endpoint_error
from services.rbac_service import require_permission
from services.auth_service import auth_guard
import psycopg2
from psycopg2 import errors, IntegrityError

router = APIRouter(prefix="/testcases", tags=["Testcases"])

@router.post("/")
@require_permission("testcases_create")
async def create_testcase(payload: Dict[str, Any] = Body(...), Authorization: Optional[str] = Header(None)):
    user = auth_guard(Authorization)
    try:
        tenant_id = user.get("tenant_id")
        TestcaseService.create_testcase(payload, tenant_id)
        return {"success": True, "message": "Testcase created successfully"}
    except Exception as e:
        return handle_endpoint_error(e, "/testcases/", return_dict=True)

@router.post("/upload")
@require_permission("testcases_create")
async def upload_testcases(file: UploadFile = File(...), Authorization: Optional[str] = Header(None)):
    user = auth_guard(Authorization)
    try:
        # Lazy import so the router loads even if pandas/openpyxl are not installed.
        try:
            from utils.testcase_validator import validate_excel_file
        except Exception as e:
            raise HTTPException(
                status_code=503,
                detail="Excel upload not available on this server (missing pandas/openpyxl)."
            ) from e
        
        content = await file.read()
        tenant_id = user.get("tenant_id")
        
        # 1. Fetch valid projects and users for validation
        valid_projects = TestcaseService.get_valid_projects_map(tenant_id)
        valid_users = TestcaseService.get_valid_users_list(tenant_id)
        
        # 2. Validate
        success, data, validation_errors = validate_excel_file(content, valid_projects, valid_users)
        
        if not success:
            return {"success": False, "errors": validation_errors}

        # 3. Check for duplicates (Internal and Database)
        duplicate_errors = []
        
        # 3a. Check for internal duplicates in the file
        seen_ids = {}
        for row in data:
            tid = row.get("test_case_id")
            if tid:
                if tid in seen_ids:
                    duplicate_errors.append({
                        "row": row.get("excel_row_num"),
                        "column": "Test Case ID",
                        "message": f"Duplicate Test Case ID '{tid}' found in file (also on row {seen_ids[tid]})"
                    })
                else:
                    seen_ids[tid] = row.get("excel_row_num")
        
        # 3b. Check for duplicates in Database
        # Only check if no internal duplicates to avoid confusion (or check anyway?)
        # Let's check DB even if internal duplicates exist? No, usually fix internal first.
        # But user wants to know ALL issues.
        
        # Get all IDs from the file to check against DB
        all_ids = list(seen_ids.keys())
        if all_ids:
            existing_ids = TestcaseService.check_existing_testcase_ids(all_ids, tenant_id)
            
            if existing_ids:
                existing_set = set(existing_ids)
                for row in data:
                    if row.get("test_case_id") in existing_set:
                        duplicate_errors.append({
                            "row": row.get("excel_row_num"),
                            "column": "Test Case ID",
                            "message": f"Test Case ID '{row.get('test_case_id')}' already exists in database"
                        })
        
        if duplicate_errors:
            return {"success": False, "errors": duplicate_errors}
            
        # 4. Insert
        # Must remove 'excel_row_num' before passing to create_bulk_testcases as it matches DB columns
        cleaned_data = []
        for row in data:
            new_row = {k: v for k, v in row.items() if k != "excel_row_num"}
            cleaned_data.append(new_row)

        TestcaseService.create_bulk_testcases(cleaned_data, tenant_id)
        
        return {"success": True, "message": f"{len(data)} Testcases uploaded successfully"}
        
    except (errors.UniqueViolation, IntegrityError) as e:
        # Extract duplicate ID if possible
        msg = "Duplicate testcase found. A testcase with the same ID already exists."
        if hasattr(e, 'diag') and e.diag and e.diag.message_detail:
             msg += f" {e.diag.message_detail}"
        elif str(e):
             # Fallback to string representation if diag is missing
             msg += f" Details: {str(e)}"
        return {"success": False, "message": msg}
    except Exception as e:
        # Return a JSON response compatible with frontend expectation
        error_info = handle_endpoint_error(e, "/testcases/upload", return_dict=True)
        # Extract message from error_info
        msg = error_info.get("error", {}).get("message", "An unexpected error occurred")
        return {"success": False, "message": msg}

@router.get("/projects")
@require_permission("testcases_retrieve")
async def get_projects_summary(Authorization: Optional[str] = Header(None)):
    user = auth_guard(Authorization)
    try:
        tenant_id = user.get("tenant_id")
        user_id = user.get("user_id") or user.get("id")
        
        from services.rbac_service import get_user_accessible_projects
        accessible_projects = get_user_accessible_projects(user_id, tenant_id)
        
        projects = TestcaseService.get_projects_with_testcases(tenant_id)
        
        if accessible_projects is not None:
            projects = [p for p in projects if p.get("project_id") in accessible_projects]
            
        return projects
    except Exception as e:
        return handle_endpoint_error(e, "/testcases/projects", return_dict=False)

@router.get("/project/{project_id}/filters")
@require_permission("testcases_retrieve")
async def get_project_filters(project_id: str, Authorization: Optional[str] = Header(None)):
    auth_guard(Authorization)
    try:
        return TestcaseService.get_project_filter_options(project_id)
    except Exception as e:
        return handle_endpoint_error(e, f"/testcases/project/{project_id}/filters", return_dict=False)


@router.get("/project/{project_id}")
@require_permission("testcases_retrieve")
async def get_project_testcases(
    project_id: str, 
    execution_status: Optional[str] = None,
    priority: Optional[str] = None,
    tester_email: Optional[str] = None,
    module: Optional[str] = None,
    date: Optional[str] = None,
    Authorization: Optional[str] = Header(None)
):
    auth_guard(Authorization)
    try:
        filters = {
            "execution_status": execution_status,
            "priority": priority,
            "tester_email": tester_email,
            "module": module,
            "date": date
        }
        return TestcaseService.get_project_testcases(project_id, filters)
    except Exception as e:
        return handle_endpoint_error(e, f"/testcases/project/{project_id}", return_dict=False)

@router.get("/{testcase_id}")
@require_permission("testcases_retrieve")
async def get_testcase_details(testcase_id: str, Authorization: Optional[str] = Header(None)):
    auth_guard(Authorization)
    try:
        tc = TestcaseService.get_testcase_details(testcase_id)
        if not tc:
            raise HTTPException(404, "Testcase not found")
        return tc
    except Exception as e:
        return handle_endpoint_error(e, f"/testcases/{testcase_id}", return_dict=False)

@router.put("/{testcase_id}")
@require_permission("testcases_update")
async def update_testcase(testcase_id: str, updates: Dict[str, Any] = Body(...), Authorization: Optional[str] = Header(None)):
    user = auth_guard(Authorization)
    try:
        TestcaseService.update_testcase(testcase_id, updates, user)
        return {"success": True, "message": "Testcase updated successfully"}
    except Exception as e:
        return handle_endpoint_error(e, f"/testcases/{testcase_id}", return_dict=True)

@router.delete("/{testcase_id}")
@require_permission("testcases_delete")
async def delete_testcase(testcase_id: str, Authorization: Optional[str] = Header(None)):
    auth_guard(Authorization)
    try:
        TestcaseService.delete_testcase(testcase_id)
        return {"success": True, "message": "Testcase deleted successfully"}
    except Exception as e:
        return handle_endpoint_error(e, f"/testcases/{testcase_id}", return_dict=True)

@router.get("/{testcase_id}/activity")
@require_permission("testcases_retrieve")
async def get_activity_logs(testcase_id: str, Authorization: Optional[str] = Header(None)):
    auth_guard(Authorization)
    try:
        return TestcaseService.get_activity_logs(testcase_id)
    except Exception as e:
        return handle_endpoint_error(e, f"/testcases/{testcase_id}/activity", return_dict=False)

@router.get("/{testcase_id}/comments")
@require_permission("testcases_retrieve")
async def get_comments(testcase_id: str, Authorization: Optional[str] = Header(None)):
    auth_guard(Authorization)
    try:
        return TestcaseService.get_comments(testcase_id)
    except Exception as e:
        return handle_endpoint_error(e, f"/testcases/{testcase_id}/comments", return_dict=False)

@router.post("/{testcase_id}/comments")
@require_permission("testcases_update")
async def add_comment(testcase_id: str, payload: Dict[str, str] = Body(...), Authorization: Optional[str] = Header(None)):
    user = auth_guard(Authorization)
    try:
        comment = payload.get("comment")
        if not comment:
            raise HTTPException(400, "Comment is required")
        TestcaseService.add_comment(testcase_id, user, comment)
        return {"success": True, "message": "Comment added"}
    except Exception as e:
        return handle_endpoint_error(e, f"/testcases/{testcase_id}/comments", return_dict=True)

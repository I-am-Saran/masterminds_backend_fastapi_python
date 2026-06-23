"""Workflow Engine API — Super Admin configuration + ticket execution."""

from typing import Optional

from fastapi import APIRouter, Header

from app.tasks.dependencies import get_auth_context
from app.workflows.dependencies import get_workflow_admin_context
from app.workflows.engine import advance_workflow, build_ticket_workflow_state, start_workflow_for_task
from app.workflows.schemas import WorkflowAdvance, WorkflowCreate, WorkflowMappingCreate, WorkflowUpdate
from app.workflows.service import WorkflowService
from services.rbac_service import require_permission

router = APIRouter(tags=["Workflows"])


@router.get("/workflows")
async def list_workflows(Authorization: Optional[str] = Header(None)):
    auth = get_workflow_admin_context(Authorization, action="retrieve")
    return WorkflowService.list_workflows(str(auth["tenant_id"]))


@router.get("/workflows/mappings")
async def list_workflow_mappings(Authorization: Optional[str] = Header(None)):
    auth = get_workflow_admin_context(Authorization, action="retrieve")
    return WorkflowService.list_mappings(str(auth["tenant_id"]))


@router.post("/workflows/mappings")
async def create_workflow_mapping(
    payload: WorkflowMappingCreate,
    Authorization: Optional[str] = Header(None),
):
    auth = get_workflow_admin_context(Authorization, action="update")
    return WorkflowService.save_mapping(
        str(auth["tenant_id"]), payload.ticket_category, payload.workflow_id
    )


@router.delete("/workflows/mappings/{mapping_id}")
async def delete_workflow_mapping(mapping_id: str, Authorization: Optional[str] = Header(None)):
    auth = get_workflow_admin_context(Authorization, action="delete")
    return WorkflowService.delete_mapping(mapping_id, str(auth["tenant_id"]))


@router.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: str, Authorization: Optional[str] = Header(None)):
    auth = get_workflow_admin_context(Authorization, action="retrieve")
    return WorkflowService.get_workflow(workflow_id, str(auth["tenant_id"]))


@router.post("/workflows")
async def create_workflow(payload: WorkflowCreate, Authorization: Optional[str] = Header(None)):
    auth = get_workflow_admin_context(Authorization, action="create")
    return WorkflowService.create_workflow(payload, auth)


@router.put("/workflows/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    payload: WorkflowUpdate,
    Authorization: Optional[str] = Header(None),
):
    auth = get_workflow_admin_context(Authorization, action="update")
    return WorkflowService.update_workflow(workflow_id, payload, auth)


@router.delete("/workflows/{workflow_id}")
async def delete_workflow(workflow_id: str, Authorization: Optional[str] = Header(None)):
    auth = get_workflow_admin_context(Authorization, action="delete")
    return WorkflowService.delete_workflow(workflow_id, str(auth["tenant_id"]))


@router.post("/workflows/{workflow_id}/activate")
async def activate_workflow(workflow_id: str, Authorization: Optional[str] = Header(None)):
    auth = get_workflow_admin_context(Authorization, action="update")
    return WorkflowService.set_active(workflow_id, str(auth["tenant_id"]), True)


@router.post("/workflows/{workflow_id}/deactivate")
async def deactivate_workflow(workflow_id: str, Authorization: Optional[str] = Header(None)):
    auth = get_workflow_admin_context(Authorization, action="update")
    return WorkflowService.set_active(workflow_id, str(auth["tenant_id"]), False)


@router.post("/workflows/{workflow_id}/clone")
async def clone_workflow(workflow_id: str, Authorization: Optional[str] = Header(None)):
    auth = get_workflow_admin_context(Authorization, action="create")
    return WorkflowService.clone_workflow(workflow_id, auth)


# --- Ticket workflow execution (kaizen_tasks permission) ---


@router.get("/tasks/{task_id}/workflow")
@require_permission("kaizen_tasks_retrieve")
async def get_task_workflow(task_id: str, Authorization: Optional[str] = Header(None)):
    auth = get_auth_context(Authorization)
    return {
        "success": True,
        "data": build_ticket_workflow_state(
            task_id,
            auth=auth,
            tenant_id=str(auth["tenant_id"]),
        ),
    }


@router.post("/tasks/{task_id}/workflow/advance")
@require_permission("kaizen_tasks_update")
async def advance_task_workflow(
    task_id: str,
    payload: WorkflowAdvance,
    Authorization: Optional[str] = Header(None),
):
    auth = get_auth_context(Authorization)
    from app.tasks import repository as task_repo

    task = task_repo.get_by_id(task_id, str(auth["tenant_id"]))
    if not task:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Task not found")

    performer = auth.get("user_id")
    return advance_workflow(
        task_id,
        str(auth["tenant_id"]),
        payload.action,
        payload.comments,
        performer,
        payload.reassign_user_id,
        performer_email=auth.get("email"),
    )

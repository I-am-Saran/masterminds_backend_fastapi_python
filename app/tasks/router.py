"""Kaizen Tasks API — /api/tasks/*"""

import asyncio
from typing import Optional

from fastapi import APIRouter, Header, Query

from app.tasks.dependencies import get_auth_context
from app.tasks.schemas import TaskCommentCreate, TaskCreate, TaskStatusPatch, TaskUpdate
from app.tasks.service import TaskService
from services.rbac_service import require_permission

router = APIRouter(tags=["Kaizen Tasks"])


# Reference + dashboard routes (before /{task_id})


@router.get("/tasks/reference")
@require_permission("kaizen_tasks_retrieve")
async def task_reference(Authorization: Optional[str] = Header(None)):
    auth = get_auth_context(Authorization)
    return TaskService.reference_data(auth["tenant_id"])


@router.get("/tasks/categories")
@require_permission("kaizen_tasks_retrieve")
async def task_active_categories(Authorization: Optional[str] = Header(None)):
    """Categories with an ACTIVE workflow mapping — for create-ticket UI (non-admin users)."""
    auth = get_auth_context(Authorization)
    return TaskService.active_ticket_categories(auth["tenant_id"])


@router.get("/tasks/dashboard/summary")
@require_permission("kaizen_tasks_retrieve")
async def dashboard_summary(Authorization: Optional[str] = Header(None)):
    from app.tasks import repository as repo

    auth = get_auth_context(Authorization)
    return {"success": True, "data": repo.dashboard_summary(str(auth["tenant_id"]))}


@router.get("/tasks/dashboard/overdue")
@require_permission("kaizen_tasks_retrieve")
async def dashboard_overdue(
    limit: int = Query(20, ge=1, le=100),
    Authorization: Optional[str] = Header(None),
):
    from app.tasks import repository as repo

    auth = get_auth_context(Authorization)
    return {"success": True, "data": repo.dashboard_overdue(str(auth["tenant_id"]), limit)}


@router.get("/tasks/dashboard/stale")
@require_permission("kaizen_tasks_retrieve")
async def dashboard_stale(
    limit: int = Query(20, ge=1, le=100),
    Authorization: Optional[str] = Header(None),
):
    from app.tasks import repository as repo

    auth = get_auth_context(Authorization)
    return {"success": True, "data": repo.dashboard_stale(str(auth["tenant_id"]), limit)}


@router.get("/tasks/dashboard/by-owner")
@require_permission("kaizen_tasks_retrieve")
async def dashboard_by_owner(Authorization: Optional[str] = Header(None)):
    from app.tasks import repository as repo

    auth = get_auth_context(Authorization)
    return {"success": True, "data": repo.dashboard_by_owner(str(auth["tenant_id"]))}


@router.get("/tasks/dashboard/by-category")
@require_permission("kaizen_tasks_retrieve")
async def dashboard_by_category(Authorization: Optional[str] = Header(None)):
    from app.tasks import repository as repo

    auth = get_auth_context(Authorization)
    return {"success": True, "data": repo.dashboard_by_category(str(auth["tenant_id"]))}


@router.get("/tasks/dashboard/recent-activity")
@require_permission("kaizen_tasks_retrieve")
async def dashboard_recent_activity(
    limit: int = Query(20, ge=1, le=100),
    Authorization: Optional[str] = Header(None),
):
    from app.tasks import repository as repo

    auth = get_auth_context(Authorization)
    return {"success": True, "data": repo.dashboard_recent_activity(str(auth["tenant_id"]), limit)}


@router.get("/tasks/status-transitions/{task_id}")
@require_permission("kaizen_tasks_retrieve")
async def status_transitions(task_id: str, Authorization: Optional[str] = Header(None)):
    auth = get_auth_context(Authorization)
    return TaskService.status_transitions(task_id, auth)


# CRUD


@router.get("/tasks")
@require_permission("kaizen_tasks_retrieve")
async def list_tasks(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    owner_email: Optional[str] = Query(None),
    meeting_id: Optional[int] = Query(None),
    source_type: Optional[str] = Query(None),
    overdue: Optional[bool] = Query(None),
    blocked: Optional[bool] = Query(None),
    category: Optional[str] = Query(None),
    mine: Optional[bool] = Query(None),
    raised_by_me: Optional[bool] = Query(None),
    stale: Optional[bool] = Query(None),
    sort_by: str = Query("due_date"),
    sort_desc: bool = Query(False),
    Authorization: Optional[str] = Header(None),
):
    auth = get_auth_context(Authorization)
    return TaskService.list_tasks(
        auth["tenant_id"],
        page=page,
        limit=limit,
        search=search,
        status=status,
        priority=priority,
        owner_email=owner_email,
        meeting_id=meeting_id,
        source_type=source_type,
        overdue=overdue,
        blocked=blocked,
        category=category,
        mine_email=auth["email"] if mine else None,
        raised_by_email=auth["email"] if raised_by_me else None,
        stale=stale,
        sort_by=sort_by,
        sort_desc=sort_desc,
    )


@router.get("/tasks/{task_id}")
@require_permission("kaizen_tasks_retrieve")
async def get_task(task_id: str, Authorization: Optional[str] = Header(None)):
    auth = get_auth_context(Authorization)
    return TaskService.get_task(task_id, auth["tenant_id"])


@router.post("/tasks")
@require_permission("kaizen_tasks_create")
async def create_task(payload: TaskCreate, Authorization: Optional[str] = Header(None)):
    auth = get_auth_context(Authorization)
    return await asyncio.to_thread(TaskService.create_task, payload, auth)


@router.put("/tasks/{task_id}")
@require_permission("kaizen_tasks_update")
async def update_task(
    task_id: str,
    payload: TaskUpdate,
    Authorization: Optional[str] = Header(None),
):
    auth = get_auth_context(Authorization)
    return TaskService.update_task(task_id, payload, auth)


@router.post("/tasks/{task_id}/start-work")
@require_permission("kaizen_tasks_update")
async def start_work(task_id: str, Authorization: Optional[str] = Header(None)):
    auth = get_auth_context(Authorization)
    return await asyncio.to_thread(TaskService.start_work, task_id, auth)


@router.patch("/tasks/{task_id}/status")
@require_permission("kaizen_tasks_update")
async def patch_status(
    task_id: str,
    payload: TaskStatusPatch,
    Authorization: Optional[str] = Header(None),
):
    auth = get_auth_context(Authorization)
    status_val = payload.status.value if hasattr(payload.status, "value") else payload.status
    return TaskService.patch_status(task_id, status_val, auth, payload.blocked_reason)


@router.delete("/tasks/{task_id}")
@require_permission("kaizen_tasks_delete")
async def delete_task(task_id: str, Authorization: Optional[str] = Header(None)):
    auth = get_auth_context(Authorization)
    return TaskService.delete_task(task_id, auth["tenant_id"])


@router.get("/tasks/{task_id}/comments")
@require_permission("kaizen_tasks_retrieve")
async def list_comments(task_id: str, Authorization: Optional[str] = Header(None)):
    auth = get_auth_context(Authorization)
    return TaskService.list_comments(task_id, auth["tenant_id"])


@router.post("/tasks/{task_id}/comments")
@require_permission("kaizen_tasks_comment")
async def add_comment(
    task_id: str,
    payload: TaskCommentCreate,
    Authorization: Optional[str] = Header(None),
):
    auth = get_auth_context(Authorization)
    return TaskService.add_comment(task_id, payload.comment, auth)


@router.get("/tasks/{task_id}/history")
@require_permission("kaizen_tasks_retrieve")
async def list_history(task_id: str, Authorization: Optional[str] = Header(None)):
    auth = get_auth_context(Authorization)
    return TaskService.list_history(task_id, auth["tenant_id"])

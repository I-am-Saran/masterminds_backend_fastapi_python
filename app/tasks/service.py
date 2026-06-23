"""Kaizen Tasks business logic."""

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException

from app.tasks import meeting_sync, repository as repo
from app.tasks.schemas import TaskCreate, TaskSourceType, TaskStatus, TaskUpdate
from app.tasks.status_engine import get_allowed_target_statuses, validate_status_transition
from app.tasks.validators import (
    normalize_email,
    validate_category,
    validate_priority,
    validate_source_type,
    validate_status,
)


def _actor_uuid(auth: Dict[str, Any]) -> Optional[str]:
    return repo.resolve_owner_uuid(auth.get("email"))


def _actor_email(auth: Dict[str, Any]) -> str:
    return (auth.get("email") or "").strip()


def _is_task_assignee(task: Dict[str, Any], auth: Dict[str, Any]) -> bool:
    owner = (task.get("owner_email") or "").strip().lower()
    actor = _actor_email(auth).lower()
    return bool(owner and actor and owner == actor)


def _schedule_email_notification(callback) -> None:
    """Run SMTP-heavy notification work off the request thread."""
    threading.Thread(target=callback, daemon=True).start()


class TaskService:
    @staticmethod
    def list_tasks(tenant_id: str, **filters) -> Dict[str, Any]:
        page = int(filters.pop("page", 1))
        limit = int(filters.pop("limit", 50))
        rows, total = repo.list_tasks(str(tenant_id), page=page, limit=limit, **filters)
        return {
            "success": True,
            "data": rows,
            "meta": {"total": total, "page": page, "limit": limit},
            "message": "Tasks retrieved successfully",
        }

    @staticmethod
    def get_task(task_id: str, tenant_id: str) -> Dict[str, Any]:
        row = repo.get_by_id(task_id, str(tenant_id))
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"success": True, "data": row, "message": "Task retrieved successfully"}

    @staticmethod
    def create_task(payload: TaskCreate, auth: Dict[str, Any]) -> Dict[str, Any]:
        tenant_id = str(auth["tenant_id"])
        meeting_id = payload.meeting_id
        source_type = validate_source_type(
            payload.source_type.value if hasattr(payload.source_type, "value") else payload.source_type,
            meeting_id,
        )
        if meeting_id and not meeting_sync.meeting_exists(meeting_id):
            raise HTTPException(status_code=404, detail="Meeting not found")

        status = validate_status(
            payload.status.value if hasattr(payload.status, "value") else payload.status
        )
        priority = validate_priority(
            payload.priority.value if hasattr(payload.priority, "value") else payload.priority
        )
        category = validate_category(payload.category, required=True)
        owner_email = normalize_email(payload.owner_email) if payload.owner_email else None

        data = {
            "tenant_id": tenant_id,
            "title": payload.title.strip(),
            "description": payload.description,
            "owner_email": owner_email,
            "owner_id": repo.resolve_owner_uuid(owner_email) if owner_email else None,
            "status": status,
            "priority": priority,
            "due_date": payload.due_date,
            "category": category,
            "meeting_id": meeting_id,
            "source_type": source_type,
            "is_blocked": payload.is_blocked or status == "BLOCKED",
            "blocked_reason": payload.blocked_reason,
            "created_by": _actor_uuid(auth),
        }
        if status == "DONE":
            data["completed_at"] = datetime.now(timezone.utc)

        created = repo.insert_task(data)
        if not created:
            raise HTTPException(status_code=500, detail="Failed to create task")

        task_id = created["id"]
        if payload.watcher_emails:
            repo.replace_watchers(task_id, payload.watcher_emails)

        repo.insert_history(
            task_id, "status", None, status,
            changed_by_email=auth.get("email"),
            changed_by_id=_actor_uuid(auth),
        )

        if payload.sync_mom_action and meeting_id:
            meeting_sync.create_mom_action_for_task(created)
            created = repo.get_by_id(task_id, tenant_id) or created

        from app.workflows.engine import start_workflow_for_task

        try:
            start_workflow_for_task(
                task_id,
                category,
                tenant_id,
                auth.get("user_id"),
            )
        except Exception:
            logging.exception("Workflow auto-start failed for task %s", task_id)
        created = repo.get_by_id(task_id, tenant_id) or created

        task_snapshot = dict(created)
        creator_email = auth.get("email")

        def _send_created_email() -> None:
            try:
                from app.email.notification_service import EmailNotificationService

                EmailNotificationService.notify_ticket_created(
                    tenant_id,
                    task_snapshot,
                    creator_email,
                )
            except Exception:
                logging.exception("Ticket created email notification failed")

        _schedule_email_notification(_send_created_email)

        return {"success": True, "data": created, "message": "Task created successfully"}

    @staticmethod
    def update_task(task_id: str, payload: TaskUpdate, auth: Dict[str, Any]) -> Dict[str, Any]:
        tenant_id = str(auth["tenant_id"])
        existing = repo.get_by_id(task_id, tenant_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Task not found")

        updates = payload.model_dump(exclude_unset=True)
        watcher_emails = updates.pop("watcher_emails", None)
        if not updates and watcher_emails is None:
            raise HTTPException(status_code=400, detail="No fields to update")

        data: Dict[str, Any] = {}

        if "title" in updates and updates["title"]:
            new_title = updates["title"].strip()
            if new_title != (existing.get("title") or "").strip():
                repo.insert_history(
                    task_id, "title", existing.get("title"), new_title,
                    changed_by_email=auth.get("email"), changed_by_id=_actor_uuid(auth),
                )
            data["title"] = new_title
        if "description" in updates:
            data["description"] = updates["description"]
        if "category" in updates:
            data["category"] = validate_category(
                updates["category"],
                existing=existing.get("category"),
            )
        if "due_date" in updates:
            repo.insert_history(
                task_id, "due_date", existing.get("due_date"), updates["due_date"],
                changed_by_email=auth.get("email"), changed_by_id=_actor_uuid(auth),
            )
            data["due_date"] = updates["due_date"]
        if "owner_email" in updates:
            new_email = normalize_email(updates["owner_email"])
            repo.insert_history(
                task_id, "owner_email", existing.get("owner_email"), new_email,
                changed_by_email=auth.get("email"), changed_by_id=_actor_uuid(auth),
            )
            data["owner_email"] = new_email
            data["owner_id"] = repo.resolve_owner_uuid(new_email)
        if "priority" in updates and updates["priority"] is not None:
            p = updates["priority"]
            new_priority = validate_priority(p.value if hasattr(p, "value") else p)
            if new_priority != (existing.get("priority") or "").upper():
                repo.insert_history(
                    task_id, "priority", existing.get("priority"), new_priority,
                    changed_by_email=auth.get("email"), changed_by_id=_actor_uuid(auth),
                )
            data["priority"] = new_priority
        if "is_blocked" in updates:
            data["is_blocked"] = updates["is_blocked"]
        if "blocked_reason" in updates:
            data["blocked_reason"] = updates["blocked_reason"]
        if "status" in updates and updates["status"] is not None:
            s = updates["status"]
            new_status = validate_status(s.value if hasattr(s, "value") else s)
            TaskService._apply_status(task_id, existing, new_status, auth, data, updates.get("blocked_reason"))

        if data:
            repo.update_task(task_id, tenant_id, data)

        if watcher_emails is not None:
            repo.replace_watchers(task_id, watcher_emails)

        row = repo.get_by_id(task_id, tenant_id)
        if row and row.get("legacy_mom_action_id"):
            meeting_sync.update_mom_action_from_task(row)

        return {"success": True, "data": row, "message": "Task updated successfully"}

    @staticmethod
    def patch_status(
        task_id: str,
        new_status: str,
        auth: Dict[str, Any],
        blocked_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        tenant_id = str(auth["tenant_id"])
        existing = repo.get_by_id(task_id, tenant_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Task not found")

        new_status = validate_status(new_status)
        data: Dict[str, Any] = {}
        TaskService._apply_status(task_id, existing, new_status, auth, data, blocked_reason)
        repo.update_task(task_id, tenant_id, data)

        row = repo.get_by_id(task_id, tenant_id)
        if row and row.get("legacy_mom_action_id"):
            meeting_sync.update_mom_action_from_task(row)

        return {"success": True, "data": row, "message": "Status updated successfully"}

    @staticmethod
    def _apply_status(
        task_id: str,
        existing: Dict[str, Any],
        new_status: str,
        auth: Dict[str, Any],
        data: Dict[str, Any],
        blocked_reason: Optional[str],
    ) -> None:
        old = existing.get("status")
        validate_status_transition(old, new_status, auth["user_id"], str(auth["tenant_id"]))
        repo.insert_history(
            task_id, "status", old, new_status,
            changed_by_email=auth.get("email"), changed_by_id=_actor_uuid(auth),
        )
        data["status"] = new_status
        if new_status == "BLOCKED":
            data["is_blocked"] = True
            if blocked_reason:
                data["blocked_reason"] = blocked_reason
        elif new_status == "DONE":
            data["completed_at"] = datetime.now(timezone.utc)
            data["is_blocked"] = False
        else:
            if old == "DONE":
                data["completed_at"] = None
            if new_status != "BLOCKED":
                data["is_blocked"] = False
        if old == "OPEN" and new_status == "IN_PROGRESS":
            data["work_started_at"] = datetime.now(timezone.utc)

    @staticmethod
    def start_work(task_id: str, auth: Dict[str, Any]) -> Dict[str, Any]:
        """Assignee acknowledges assignment and moves OPEN → IN_PROGRESS."""
        tenant_id = str(auth["tenant_id"])
        existing = repo.get_by_id(task_id, tenant_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Task not found")

        current = (existing.get("status") or "OPEN").upper()
        if current != "OPEN":
            raise HTTPException(
                status_code=400,
                detail=f"Start Work is only available when ticket status is OPEN (current: {current})",
            )

        if not _is_task_assignee(existing, auth):
            raise HTTPException(
                status_code=403,
                detail="Only the assigned workflow owner can start work on this ticket",
            )

        if not existing.get("owner_email"):
            raise HTTPException(
                status_code=400,
                detail="Ticket has no assignee. Assign an owner before starting work.",
            )

        data: Dict[str, Any] = {}
        TaskService._apply_status(task_id, existing, "IN_PROGRESS", auth, data, None)
        repo.update_task(task_id, tenant_id, data)

        actor = _actor_email(auth) or "User"
        repo.insert_activity(
            task_id,
            f"Work started by {actor}",
            changed_by_email=auth.get("email"),
            changed_by_id=_actor_uuid(auth),
        )

        row = repo.get_by_id(task_id, tenant_id)
        if row and row.get("legacy_mom_action_id"):
            meeting_sync.update_mom_action_from_task(row)

        task_snapshot = dict(row or existing)
        notifier_email = auth.get("email")

        def _send_work_started_email() -> None:
            try:
                from app.email.notification_service import EmailNotificationService

                EmailNotificationService.notify_work_started(
                    tenant_id, task_snapshot, notifier_email
                )
            except Exception:
                logging.exception("Work started email notification failed for task %s", task_id)

        _schedule_email_notification(_send_work_started_email)

        return {"success": True, "data": row, "message": "Work started successfully"}

    @staticmethod
    def delete_task(task_id: str, tenant_id: str) -> Dict[str, Any]:
        existing = repo.get_by_id(task_id, str(tenant_id))
        if not existing:
            raise HTTPException(status_code=404, detail="Task not found")
        legacy = existing.get("legacy_mom_action_id")
        if not repo.soft_delete(task_id, str(tenant_id)):
            raise HTTPException(status_code=500, detail="Failed to delete task")
        meeting_sync.delete_mom_action_for_task(legacy)
        return {"success": True, "message": "Task deleted successfully"}

    @staticmethod
    def list_comments(task_id: str, tenant_id: str) -> Dict[str, Any]:
        if not repo.get_by_id(task_id, str(tenant_id)):
            raise HTTPException(status_code=404, detail="Task not found")
        return {"success": True, "data": repo.list_comments(task_id)}

    @staticmethod
    def add_comment(task_id: str, comment: str, auth: Dict[str, Any]) -> Dict[str, Any]:
        tenant_id = str(auth["tenant_id"])
        if not repo.get_by_id(task_id, tenant_id):
            raise HTTPException(status_code=404, detail="Task not found")
        row = repo.insert_comment(
            task_id, comment,
            author_email=auth.get("email"),
            author_id=_actor_uuid(auth),
        )
        return {"success": True, "data": row, "message": "Comment added"}

    @staticmethod
    def list_history(task_id: str, tenant_id: str) -> Dict[str, Any]:
        if not repo.get_by_id(task_id, str(tenant_id)):
            raise HTTPException(status_code=404, detail="Task not found")
        return {"success": True, "data": repo.list_history(task_id)}

    @staticmethod
    def status_transitions(task_id: str, auth: Dict[str, Any]) -> Dict[str, Any]:
        tenant_id = str(auth["tenant_id"])
        existing = repo.get_by_id(task_id, tenant_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Task not found")
        targets = get_allowed_target_statuses(
            existing.get("status", "OPEN"), tenant_id, auth["user_id"]
        )
        return {
            "success": True,
            "data": {
                "task_id": task_id,
                "current_status": existing.get("status"),
                "allowed_statuses": targets,
            },
        }

    @staticmethod
    def reference_data(tenant_id: str) -> Dict[str, Any]:
        return {
            "success": True,
            "data": {
                "statuses": repo.list_reference_statuses(),
                "priorities": repo.list_reference_priorities(),
                "categories": repo.list_reference_categories(str(tenant_id)),
            },
        }

    @staticmethod
    def active_ticket_categories(tenant_id: str) -> Dict[str, Any]:
        from app.workflows import repository as wf_repo

        return {
            "success": True,
            "data": wf_repo.list_active_mapped_categories(str(tenant_id)),
        }

    @staticmethod
    def create_from_meeting(payload: Dict[str, Any], auth: Dict[str, Any]) -> Dict[str, Any]:
        tc = TaskCreate(
            title=payload.get("title") or payload.get("task_name") or "Untitled",
            description=payload.get("description"),
            owner_email=payload.get("owner_email") or payload.get("assignee") or payload.get("assignee_name"),
            status=TaskStatus(payload.get("status", "OPEN")),
            priority=payload.get("priority", "P3"),
            due_date=payload.get("due_date"),
            meeting_id=payload.get("meeting_id"),
            source_type=TaskSourceType.MEETING,
            is_blocked=(payload.get("status") == "BLOCKED"),
            blocked_reason=payload.get("blocked_reason"),
            sync_mom_action=True,
        )
        return TaskService.create_task(tc, auth)

    @staticmethod
    def normalize_for_mom(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": row.get("legacy_mom_action_id") or row.get("id"),
            "kaizen_task_id": row.get("id"),
            "meeting_id": row.get("meeting_id"),
            "title": row.get("title"),
            "description": row.get("description"),
            "assignee": row.get("owner_email"),
            "assignee_name": row.get("owner_email"),
            "due_date": row.get("due_date"),
            "status": row.get("status"),
            "priority": row.get("priority"),
            "meeting_title": row.get("meeting_title"),
            "meeting_date": row.get("meeting_date"),
            "comment_count": row.get("comment_count", 0),
            "updated_at": row.get("updated_at"),
            "created_at": row.get("created_at"),
        }

    @staticmethod
    def get_task_by_legacy_mom_id(legacy_id: int, tenant_id: str) -> Optional[Dict[str, Any]]:
        return repo.get_by_legacy_mom_action_id(legacy_id, str(tenant_id))

    @staticmethod
    def update_from_meeting_action(
        legacy_action_id: int,
        updates: Dict[str, Any],
        auth: Dict[str, Any],
    ) -> Dict[str, Any]:
        tenant_id = str(auth["tenant_id"])
        existing = repo.get_by_legacy_mom_action_id(legacy_action_id, tenant_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Task not found for action item")
        tu = TaskUpdate(**{k: v for k, v in updates.items() if v is not None})
        return TaskService.update_task(existing["id"], tu, auth)

    @staticmethod
    def delete_by_legacy_mom_id(legacy_action_id: int, tenant_id: str) -> Dict[str, Any]:
        existing = repo.get_by_legacy_mom_action_id(legacy_action_id, str(tenant_id))
        if existing:
            return TaskService.delete_task(existing["id"], str(tenant_id))
        meeting_sync.delete_mom_action_for_task(legacy_action_id)
        return {"success": True, "message": "Action item deleted successfully"}

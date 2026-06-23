"""Sync kaizen_tasks ↔ mom_action_items (meeting action items are tasks)."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from services.db_service import execute_query, insert_table, update_table


def meeting_exists(meeting_id: int) -> bool:
    row = execute_query(
        "SELECT 1 FROM mom_meetings WHERE id = %s LIMIT 1",
        (meeting_id,),
        fetch_one=True,
    )
    return bool(row)


def create_mom_action_for_task(task: Dict[str, Any]) -> Optional[int]:
    """Create mom_action_items row linked to kaizen_tasks.legacy_mom_action_id."""
    meeting_id = task.get("meeting_id")
    if not meeting_id:
        return None

    mom_data = {
        "meeting_id": meeting_id,
        "title": task.get("title"),
        "description": task.get("description"),
        "assignee_name": task.get("owner_email"),
        "due_date": task.get("due_date"),
        "status": task.get("status", "OPEN"),
        "priority": task.get("priority", "P3"),
    }
    if task.get("status") == "DONE":
        mom_data["completed_at"] = datetime.now(timezone.utc)

    created = insert_table("mom_action_items", mom_data)
    if not created:
        return None
    mom_id = created.get("id")
    if mom_id and task.get("id"):
        update_table(
            "kaizen_tasks",
            {"legacy_mom_action_id": mom_id, "updated_at": datetime.now(timezone.utc)},
            filters={"id": str(task["id"])},
        )
    return mom_id


def update_mom_action_from_task(task: Dict[str, Any]) -> None:
    mom_id = task.get("legacy_mom_action_id")
    if not mom_id:
        return
    data: Dict[str, Any] = {
        "title": task.get("title"),
        "description": task.get("description"),
        "assignee_name": task.get("owner_email"),
        "due_date": task.get("due_date"),
        "status": task.get("status"),
        "priority": task.get("priority"),
        "updated_at": datetime.now(timezone.utc),
    }
    if task.get("status") == "DONE":
        data["completed_at"] = task.get("completed_at") or datetime.now(timezone.utc)
    elif task.get("status") != "DONE":
        data["completed_at"] = None
    update_table("mom_action_items", data, filters={"id": mom_id})


def delete_mom_action_for_task(legacy_mom_action_id: Optional[int]) -> None:
    if not legacy_mom_action_id:
        return
    execute_query(
        "DELETE FROM mom_action_items WHERE id = %s",
        (legacy_mom_action_id,),
        fetch_all=False,
    )

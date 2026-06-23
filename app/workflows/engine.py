"""Workflow execution — ticket instances and level progression."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.workflows import repository as repo
from app.tasks import repository as task_repo

DEFAULT_TENANT = "00000000-0000-0000-0000-000000000001"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def start_workflow_for_task(
    ticket_id: str,
    category: Optional[str],
    tenant_id: str,
    performer_id: Optional[str],
    resolved_user_ids: Optional[Dict[str, Optional[str]]] = None,
    check_existing: bool = True,
) -> Optional[Dict[str, Any]]:
    if not category or not str(category).strip():
        return None

    if check_existing:
        existing = repo.get_instance_by_ticket(ticket_id)
        if existing:
            return existing

    workflow = repo.get_active_workflow_by_category(tenant_id, str(category))
    if not workflow:
        return None

    first_level = repo.get_first_level(workflow["id"])
    if not first_level:
        return None

    instance = repo.insert_instance(
        {
            "ticket_id": ticket_id,
            "workflow_id": workflow["id"],
            "current_level_id": first_level["id"],
            "workflow_status": "IN_PROGRESS",
        }
    )
    if not instance:
        return None

    repo.insert_history(
        {
            "workflow_instance_id": instance["id"],
            "level_id": first_level["id"],
            "action_taken": "STARTED",
            "comments": f"Workflow '{workflow.get('workflow_name')}' started at {first_level.get('level_name')}",
            "performed_by": performer_id,
        },
        normalize_performed_by=False,
    )

    owner_email = repo.resolve_owner_email(
        first_level.get("assignment_type"),
        first_level.get("assignment_value"),
        tenant_id,
    )
    # Assign workflow owner but keep ticket status OPEN until assignee clicks Start Work.
    if owner_email:
        normalized_owner_email = owner_email.strip().lower()
        owner_uuid = None
        if resolved_user_ids is not None:
            owner_uuid = resolved_user_ids.get(normalized_owner_email)
            if normalized_owner_email not in resolved_user_ids:
                resolved_user_ids.update(task_repo.resolve_owner_uuids([normalized_owner_email]))
                owner_uuid = resolved_user_ids.get(normalized_owner_email)
        else:
            owner_uuid = task_repo.resolve_owner_uuid(normalized_owner_email)
        task_repo.update_task(
            ticket_id,
            tenant_id,
            {"owner_email": normalized_owner_email, "owner_id": owner_uuid},
            refresh=False,
        )

    return instance


def build_ticket_workflow_state(
    ticket_id: str,
    auth: Optional[Dict[str, Any]] = None,
    tenant_id: Optional[str] = None,
) -> Dict[str, Any]:
    instance = repo.get_instance_by_ticket(ticket_id)
    if not instance:
        return {
            "instance_id": None,
            "workflow_id": None,
            "workflow_name": None,
            "workflow_status": None,
            "current_level_id": None,
            "current_level_name": None,
            "current_owner_email": None,
            "current_owner_label": None,
            "can_act": False,
            "can_reject": False,
            "can_reassign": False,
            "allow_skip": False,
            "levels": [],
            "history": [],
        }

    levels = repo.get_levels(instance["workflow_id"])
    history = repo.get_history(instance["id"])
    completed_level_ids = {
        h["level_id"]
        for h in history
        if h.get("level_id") and h.get("action_taken") in ("COMPLETED", "SKIPPED")
    }
    rejected = any(h.get("action_taken") == "REJECTED" for h in history)
    current_id = instance.get("current_level_id")
    wf_status = instance.get("workflow_status") or "IN_PROGRESS"

    progress: List[Dict[str, Any]] = []
    for lvl in levels:
        lid = str(lvl["id"])
        if wf_status == "COMPLETED" or lid in completed_level_ids:
            status = "SKIPPED" if any(
                h.get("level_id") == lvl["id"] and h.get("action_taken") == "SKIPPED" for h in history
            ) else "COMPLETED"
        elif rejected and lid == str(current_id):
            status = "REJECTED"
        elif lid == str(current_id) and wf_status == "IN_PROGRESS":
            status = "IN_PROGRESS"
        elif lvl["level_sequence"] < _level_sequence(levels, current_id):
            status = "COMPLETED"
        else:
            status = "PENDING"

        entry: Dict[str, Any] = {
                "level_id": lid,
                "level_sequence": lvl["level_sequence"],
                "level_name": lvl["level_name"],
                "status": status,
                "sla_hours": lvl.get("sla_hours"),
                "assignment_type": lvl.get("assignment_type"),
                "assignment_label": repo.resolve_assignment_label(
                    lvl.get("assignment_type"), lvl.get("assignment_value")
                ),
            }
        if status == "IN_PROGRESS":
            entry["can_reject"] = bool(lvl.get("can_reject"))
            entry["can_reassign"] = bool(lvl.get("can_reassign"))
            entry["allow_skip"] = bool(lvl.get("allow_skip"))
        progress.append(entry)

    current_level = repo.get_level_by_id(current_id) if current_id else None
    resolved_tenant = tenant_id
    if not resolved_tenant and auth:
        resolved_tenant = str(auth.get("tenant_id") or "")
    task = task_repo.get_by_id(ticket_id, resolved_tenant or str(instance.get("tenant_id") or DEFAULT_TENANT))
    if not resolved_tenant:
        resolved_tenant = str(task.get("tenant_id")) if task else DEFAULT_TENANT

    ticket_status = (task.get("status") or "OPEN").upper() if task else "OPEN"

    owner_email = None
    owner_label = None
    is_workflow_owner = False
    can_act = False
    requires_start_work = False
    if current_level and wf_status == "IN_PROGRESS" and resolved_tenant:
        display = repo.resolve_owner_display(
            current_level.get("assignment_type"),
            current_level.get("assignment_value"),
            resolved_tenant,
        )
        owner_email = display.get("email")
        owner_label = display.get("label")
        if auth:
            is_workflow_owner = repo.user_can_act_on_level(
                auth.get("email"),
                auth.get("user_id"),
                resolved_tenant,
                current_level,
            )
            if is_workflow_owner and ticket_status == "IN_PROGRESS":
                can_act = True
            elif is_workflow_owner and ticket_status == "OPEN":
                requires_start_work = True

    return {
        "instance_id": str(instance["id"]),
        "workflow_id": str(instance["workflow_id"]),
        "workflow_name": instance.get("workflow_name"),
        "workflow_status": wf_status,
        "ticket_status": ticket_status,
        "requires_start_work": requires_start_work,
        "current_level_id": str(current_id) if current_id else None,
        "current_level_name": current_level.get("level_name") if current_level else None,
        "current_owner_email": owner_email,
        "current_owner_label": owner_label,
        "can_act": can_act,
        "can_reject": bool(current_level.get("can_reject"))
        if current_level and wf_status == "IN_PROGRESS"
        else False,
        "can_reassign": bool(current_level.get("can_reassign"))
        if current_level and wf_status == "IN_PROGRESS"
        else False,
        "allow_skip": bool(current_level.get("allow_skip"))
        if current_level and wf_status == "IN_PROGRESS"
        else False,
        "levels": progress,
        "history": history,
    }


def _level_sequence(levels: List[Dict[str, Any]], level_id: Optional[str]) -> int:
    if not level_id:
        return 0
    for lvl in levels:
        if str(lvl["id"]) == str(level_id):
            return int(lvl["level_sequence"])
    return 0


def advance_workflow(
    ticket_id: str,
    tenant_id: str,
    action: str,
    comments: Optional[str],
    performer_id: Optional[str],
    reassign_user_id: Optional[str] = None,
    performer_email: Optional[str] = None,
) -> Dict[str, Any]:
    instance = repo.get_instance_by_ticket(ticket_id)
    if not instance:
        raise HTTPException(status_code=404, detail="No workflow instance for this ticket")

    task = task_repo.get_by_id(ticket_id, tenant_id)
    ticket_status = (task.get("status") or "OPEN").upper() if task else "OPEN"
    if ticket_status == "OPEN" and (action or "COMPLETE").upper() != "REASSIGN":
        raise HTTPException(
            status_code=400,
            detail="Start work on the ticket before completing workflow levels",
        )

    if instance.get("workflow_status") == "COMPLETED":
        raise HTTPException(status_code=400, detail="Workflow already completed")

    current = repo.get_level_by_id(instance.get("current_level_id"))
    if not current:
        raise HTTPException(status_code=400, detail="Current workflow level not found")

    if not repo.user_can_act_on_level(performer_email, performer_id, tenant_id, current):
        raise HTTPException(
            status_code=403,
            detail="Only the current workflow owner can complete, skip, or reject this level",
        )

    action = (action or "COMPLETE").upper()

    if current.get("mandatory_comments") and action == "COMPLETE" and not (comments or "").strip():
        raise HTTPException(status_code=400, detail="Comments are required for this level")

    if action == "REJECT" and not current.get("can_reject"):
        raise HTTPException(status_code=400, detail="Reject is not allowed at this level")

    if action == "SKIP" and not current.get("allow_skip"):
        raise HTTPException(status_code=400, detail="Skip is not allowed at this level")

    if action == "REASSIGN":
        if not current.get("can_reassign"):
            raise HTTPException(status_code=400, detail="Reassign is not allowed at this level")
        if not reassign_user_id:
            raise HTTPException(status_code=400, detail="reassign_user_id is required")
        email = repo.resolve_owner_email("USER", reassign_user_id, tenant_id)
        if email:
            task_repo.update_task(
                ticket_id,
                tenant_id,
                {"owner_email": email, "owner_id": task_repo.resolve_owner_uuid(email)},
            )
        repo.insert_history(
            {
                "workflow_instance_id": instance["id"],
                "level_id": current["id"],
                "action_taken": "REASSIGNED",
                "comments": comments,
                "performed_by": performer_id,
            }
        )
        return {"success": True, "data": build_ticket_workflow_state(ticket_id)}

    if action == "REJECT":
        old_status = (task.get("status") or "OPEN").upper() if task else "OPEN"
        repo.update_instance(instance["id"], {"workflow_status": "REJECTED"})
        repo.insert_history(
            {
                "workflow_instance_id": instance["id"],
                "level_id": current["id"],
                "action_taken": "REJECTED",
                "comments": comments,
                "performed_by": performer_id,
            }
        )
        task_repo.insert_history(
            ticket_id,
            "status",
            old_status,
            "CANCELLED",
            changed_by_email=performer_email,
            changed_by_id=performer_id,
        )
        actor = performer_email or "User"
        workflow_name = instance.get("workflow_name") or "Workflow"
        task_repo.insert_activity(
            ticket_id,
            f"Workflow '{workflow_name}' rejected by {actor} — ticket cancelled",
            changed_by_email=performer_email,
            changed_by_id=performer_id,
        )
        task_repo.update_task(ticket_id, tenant_id, {"status": "CANCELLED"})
        return {"success": True, "data": build_ticket_workflow_state(ticket_id)}

    history_action = "SKIPPED" if action == "SKIP" else "COMPLETED"
    repo.insert_history(
        {
            "workflow_instance_id": instance["id"],
            "level_id": current["id"],
            "action_taken": history_action,
            "comments": comments,
            "performed_by": performer_id,
        }
    )

    nxt = repo.get_next_level(instance["workflow_id"], int(current["level_sequence"]))
    if nxt:
        repo.update_instance(instance["id"], {"current_level_id": nxt["id"]})
        owner_email = repo.resolve_owner_email(
            nxt.get("assignment_type"), nxt.get("assignment_value"), tenant_id
        )
        if owner_email:
            task_repo.update_task(
                ticket_id,
                tenant_id,
                {"owner_email": owner_email, "owner_id": task_repo.resolve_owner_uuid(owner_email)},
            )
        repo.insert_history(
            {
                "workflow_instance_id": instance["id"],
                "level_id": nxt["id"],
                "action_taken": "LEVEL_ENTERED",
                "comments": f"Advanced to {nxt.get('level_name')}",
                "performed_by": performer_id,
            }
        )
    else:
        old_status = (task.get("status") or "OPEN").upper() if task else "IN_PROGRESS"
        workflow_name = instance.get("workflow_name") or "Workflow"
        level_name = current.get("level_name") or "final level"
        actor = performer_email or "User"

        repo.update_instance(
            instance["id"],
            {"workflow_status": "COMPLETED", "current_level_id": None, "completed_at": _now()},
        )
        task_repo.insert_history(
            ticket_id,
            "status",
            old_status,
            "DONE",
            changed_by_email=performer_email,
            changed_by_id=performer_id,
        )
        task_repo.insert_activity(
            ticket_id,
            f"Workflow '{workflow_name}' completed at '{level_name}' by {actor} — ticket marked as Resolved",
            changed_by_email=performer_email,
            changed_by_id=performer_id,
        )
        task_repo.update_task(
            ticket_id,
            tenant_id,
            {"status": "DONE", "completed_at": _now()},
        )

    return {"success": True, "data": build_ticket_workflow_state(ticket_id)}

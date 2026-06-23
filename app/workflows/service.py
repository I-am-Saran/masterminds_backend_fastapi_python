"""Workflow configuration business logic."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.workflows import repository as repo
from app.workflows.schemas import WorkflowCreate, WorkflowLevelCreate, WorkflowUpdate
from app.tasks.validators import validate_category


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _level_payload(level: WorkflowLevelCreate) -> Dict[str, Any]:
    return {
        "level_sequence": level.level_sequence,
        "level_name": level.level_name.strip(),
        "assignment_type": level.assignment_type.upper(),
        "assignment_value": level.assignment_value or None,
        "sla_hours": level.sla_hours,
        "escalation_enabled": level.escalation_enabled,
        "escalation_type": level.escalation_type.upper() if level.escalation_type else None,
        "escalation_value": level.escalation_value or None,
        "mandatory_comments": level.mandatory_comments,
        "mandatory_attachments": level.mandatory_attachments,
        "can_reject": level.can_reject,
        "can_reassign": level.can_reassign,
        "allow_skip": level.allow_skip,
    }


def _validate_levels(levels: List[WorkflowLevelCreate]) -> None:
    if not levels:
        raise HTTPException(status_code=400, detail="At least one workflow level is required")
    sequences = sorted(l.level_sequence for l in levels)
    if len(sequences) != len(set(sequences)):
        raise HTTPException(status_code=400, detail="Level sequences must be unique")
    for lvl in levels:
        if not lvl.assignment_value:
            raise HTTPException(
                status_code=400,
                detail=f"Assignment value required for level '{lvl.level_name}'",
            )


def _status_fields(status: str) -> Dict[str, Any]:
    s = (status or "DRAFT").upper()
    if s not in ("DRAFT", "ACTIVE", "INACTIVE"):
        s = "DRAFT"
    return {"workflow_status": s, "is_active": s == "ACTIVE"}


def _resolve_status(payload_status: Optional[str], is_active: Optional[bool], existing: Optional[Dict] = None) -> str:
    if payload_status:
        return payload_status.upper()
    if is_active is not None:
        return "ACTIVE" if is_active else "INACTIVE"
    if existing:
        return existing.get("workflow_status") or ("ACTIVE" if existing.get("is_active") else "DRAFT")
    return "DRAFT"


def _enrich_levels(levels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for lvl in levels:
        row = dict(lvl)
        row["assignment_label"] = repo.resolve_assignment_label(
            row.get("assignment_type"), row.get("assignment_value")
        )
        row["escalation_label"] = (
            repo.resolve_assignment_label(row.get("escalation_type"), row.get("escalation_value"))
            if row.get("escalation_enabled")
            else None
        )
        out.append(row)
    return out


class WorkflowService:
    @staticmethod
    def list_workflows(tenant_id: str) -> Dict[str, Any]:
        rows = repo.list_workflows(tenant_id)
        return {"success": True, "data": rows}

    @staticmethod
    def get_workflow(workflow_id: str, tenant_id: str) -> Dict[str, Any]:
        master = repo.get_workflow(workflow_id, tenant_id)
        if not master:
            raise HTTPException(status_code=404, detail="Workflow not found")
        levels = _enrich_levels(repo.get_levels(workflow_id))
        return {"success": True, "data": {**master, "levels": levels}}

    @staticmethod
    def create_workflow(payload: WorkflowCreate, auth: Dict[str, Any]) -> Dict[str, Any]:
        tenant_id = str(auth["tenant_id"])
        _validate_levels(payload.levels)
        status = _resolve_status(payload.workflow_status, payload.is_active)
        data = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "workflow_name": payload.workflow_name.strip(),
            "description": payload.description,
            "ticket_category": payload.ticket_category.strip() if payload.ticket_category else None,
            "version": 1,
            "created_by": auth.get("user_id"),
            "created_at": _now(),
            "updated_at": _now(),
            **_status_fields(status),
        }
        created = repo.insert_workflow(data)
        if not created:
            raise HTTPException(status_code=500, detail="Failed to create workflow")
        levels = [_level_payload(l) for l in sorted(payload.levels, key=lambda x: x.level_sequence)]
        repo.replace_levels(created["id"], levels)
        return WorkflowService.get_workflow(created["id"], tenant_id)

    @staticmethod
    def update_workflow(workflow_id: str, payload: WorkflowUpdate, auth: Dict[str, Any]) -> Dict[str, Any]:
        tenant_id = str(auth["tenant_id"])
        existing = repo.get_workflow(workflow_id, tenant_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Workflow not found")

        updates: Dict[str, Any] = {}
        if payload.workflow_name is not None:
            updates["workflow_name"] = payload.workflow_name.strip()
        if payload.description is not None:
            updates["description"] = payload.description
        if payload.ticket_category is not None:
            updates["ticket_category"] = payload.ticket_category.strip() or None
        status = _resolve_status(payload.workflow_status, payload.is_active, existing)
        if payload.workflow_status is not None or payload.is_active is not None:
            updates.update(_status_fields(status))

        if updates:
            repo.update_workflow(workflow_id, tenant_id, updates)

        if payload.levels is not None:
            _validate_levels(payload.levels)
            levels = [_level_payload(l) for l in sorted(payload.levels, key=lambda x: x.level_sequence)]
            repo.replace_levels(workflow_id, levels)

        return WorkflowService.get_workflow(workflow_id, tenant_id)

    @staticmethod
    def delete_workflow(workflow_id: str, tenant_id: str) -> Dict[str, Any]:
        existing = repo.get_workflow(workflow_id, tenant_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Workflow not found")
        repo.delete_workflow(workflow_id, tenant_id)
        return {"success": True, "message": "Workflow deleted"}

    @staticmethod
    def set_active(workflow_id: str, tenant_id: str, active: bool) -> Dict[str, Any]:
        existing = repo.get_workflow(workflow_id, tenant_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Workflow not found")
        status = "ACTIVE" if active else "INACTIVE"
        repo.update_workflow(workflow_id, tenant_id, _status_fields(status))
        return WorkflowService.get_workflow(workflow_id, tenant_id)

    @staticmethod
    def list_mappings(tenant_id: str) -> Dict[str, Any]:
        return {"success": True, "data": repo.list_category_mappings(tenant_id)}

    @staticmethod
    def save_mapping(tenant_id: str, ticket_category: str, workflow_id: str) -> Dict[str, Any]:
        wf = repo.get_workflow(workflow_id, tenant_id)
        if not wf:
            raise HTTPException(status_code=404, detail="Workflow not found")
        category = validate_category(ticket_category, required=True)
        row = repo.upsert_category_mapping(tenant_id, category, workflow_id)
        return {"success": True, "data": row}

    @staticmethod
    def delete_mapping(mapping_id: str, tenant_id: str) -> Dict[str, Any]:
        repo.delete_category_mapping(mapping_id, tenant_id)
        return {"success": True, "message": "Mapping removed"}

    @staticmethod
    def clone_workflow(workflow_id: str, auth: Dict[str, Any]) -> Dict[str, Any]:
        tenant_id = str(auth["tenant_id"])
        source = WorkflowService.get_workflow(workflow_id, tenant_id)["data"]
        levels = [
            WorkflowLevelCreate(
                level_sequence=l["level_sequence"],
                level_name=l["level_name"],
                assignment_type=l["assignment_type"],
                assignment_value=str(l["assignment_value"]) if l.get("assignment_value") else None,
                sla_hours=l.get("sla_hours"),
                escalation_enabled=bool(l.get("escalation_enabled")),
                escalation_type=l.get("escalation_type"),
                escalation_value=str(l["escalation_value"]) if l.get("escalation_value") else None,
                mandatory_comments=bool(l.get("mandatory_comments")),
                mandatory_attachments=bool(l.get("mandatory_attachments")),
                can_reject=bool(l.get("can_reject")),
                can_reassign=bool(l.get("can_reassign")),
                allow_skip=bool(l.get("allow_skip")),
            )
            for l in source.get("levels") or []
        ]
        payload = WorkflowCreate(
            workflow_name=f"{source['workflow_name']} (Copy)",
            description=source.get("description"),
            workflow_status="DRAFT",
            levels=levels,
        )
        return WorkflowService.create_workflow(payload, auth)

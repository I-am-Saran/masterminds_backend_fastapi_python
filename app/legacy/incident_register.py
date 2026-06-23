# REFERENCE_ONLY_MODULE — legacy Kaizen module; preserved for compatibility.
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from uuid import UUID
from services.db_service import select_table, insert_table, update_table, delete_table
from services.rbac_service import require_permission
from services.auth_service import get_user_from_token, auth_guard
from fastapi import Header


router = APIRouter(prefix="/incidents", tags=["Incident Register"])

# Allowed values for incident_type (must match DB check constraint incident_registers_incident_type_check)
ALLOWED_INCIDENT_TYPES = {"Security", "Privacy", "Operational", "Physical"}


def normalize_incident_type(value: Optional[str], default: Optional[str] = "Operational") -> Optional[str]:
    """Return value if in allowed list; else default so DB check constraint is satisfied."""
    if not value or not str(value).strip():
        return default if default in ALLOWED_INCIDENT_TYPES else None
    v = str(value).strip()
    if v in ALLOWED_INCIDENT_TYPES:
        return v
    return default if default in ALLOWED_INCIDENT_TYPES else None


class IncidentBase(BaseModel):
    organization_id: UUID
    incident_title: str
    incident_date: datetime
    incident_type: Optional[str] = None
    severity: Optional[str] = None
    description: Optional[str] = None
    immediate_action: Optional[str] = None
    root_cause: Optional[str] = None
    corrective_action: Optional[str] = None
    status: Optional[str] = "Open"
    incident_owner: Optional[str] = None
    incident_assignee: Optional[str] = None
    incident_closed_date: Optional[datetime] = None
    created_by: Optional[str] = None
    tenant_id: Optional[str] = None

class IncidentCreate(IncidentBase):
    pass

class IncidentUpdate(BaseModel):
    incident_title: Optional[str] = None
    incident_date: Optional[datetime] = None
    incident_type: Optional[str] = None
    severity: Optional[str] = None
    description: Optional[str] = None
    immediate_action: Optional[str] = None
    root_cause: Optional[str] = None
    corrective_action: Optional[str] = None
    status: Optional[str] = None
    incident_owner: Optional[str] = None
    incident_assignee: Optional[str] = None
    incident_closed_date: Optional[datetime] = None

@router.get("/", response_model=dict)
@require_permission("incident_registers_retrieve")
async def list_incidents(
    organization_id: Optional[UUID] = None,
    tenant_id: Optional[str] = Query(None),
    Authorization: Optional[str] = Header(None)
):
    try:
        user = auth_guard(Authorization)
        effective_tenant_id = user.get("tenant_id") or tenant_id or "00000000-0000-0000-0000-000000000001"
        
        filters = {"tenant_id": effective_tenant_id}
        if organization_id:
            filters["organization_id"] = str(organization_id)
        
        # Add soft delete filter
        filters["is_deleted"] = "n"
        
        incidents = select_table("incident_registers", filters=filters, order_by="incident_date DESC")
        return {"success": True, "data": incidents, "message": "Incidents retrieved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/", response_model=dict)
@require_permission("incident_registers_create")
async def create_incident(incident: IncidentCreate, Authorization: Optional[str] = Header(None)):
    try:
        user = auth_guard(Authorization)
        effective_tenant_id = user.get("tenant_id") or "00000000-0000-0000-0000-000000000001"
        
        data = incident.model_dump()
        data["tenant_id"] = effective_tenant_id
        data["incident_type"] = normalize_incident_type(data.get("incident_type"))
        # Ensure is_deleted is explicitly 'n' for new records
        data["is_deleted"] = "n"
        
        new_incident = insert_table("incident_registers", data)
        if not new_incident:
            raise HTTPException(status_code=500, detail="Failed to create incident")
        return {"success": True, "data": new_incident, "message": "Incident created successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{id}", response_model=dict)
@require_permission("incident_registers_retrieve")
async def get_incident(
    id: UUID,
    tenant_id: Optional[str] = Query(None),
    Authorization: Optional[str] = Header(None)
):
    try:
        user = auth_guard(Authorization)
        effective_tenant_id = user.get("tenant_id") or tenant_id or "00000000-0000-0000-0000-000000000001"
        
        # Add soft delete filter
        filters = {"id": str(id), "tenant_id": effective_tenant_id, "is_deleted": "n"}
        incidents = select_table("incident_registers", filters=filters)
        if not incidents:
            raise HTTPException(status_code=404, detail="Incident not found")
        return {"success": True, "data": incidents[0], "message": "Incident retrieved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{id}", response_model=dict)
@require_permission("incident_registers_update")
async def update_incident(
    id: UUID, 
    incident: IncidentUpdate,
    tenant_id: Optional[str] = Query(None),
    Authorization: Optional[str] = Header(None)
):
    try:
        user = auth_guard(Authorization)
        effective_tenant_id = user.get("tenant_id") or tenant_id or "00000000-0000-0000-0000-000000000001"
        
        data = incident.model_dump(exclude_unset=True)
        if not data:
            raise HTTPException(status_code=400, detail="No fields to update")
        if "incident_type" in data:
            data["incident_type"] = normalize_incident_type(data.get("incident_type"))
        # Add soft delete filter to ensure we don't update deleted records
        filters = {"id": str(id), "tenant_id": effective_tenant_id, "is_deleted": "n"}
        # Check if exists first
        existing = select_table("incident_registers", filters=filters)
        if not existing:
             raise HTTPException(status_code=404, detail="Incident not found")

        updated_incident = update_table("incident_registers", data, filters=filters)
            
        return {"success": True, "data": updated_incident, "message": "Incident updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{id}", response_model=dict)
@require_permission("incident_registers_delete")
async def delete_incident(
    id: UUID,
    tenant_id: Optional[str] = Query(None),
    Authorization: Optional[str] = Header(None)
):
    try:
        user = auth_guard(Authorization)
        effective_tenant_id = user.get("tenant_id") or tenant_id or "00000000-0000-0000-0000-000000000001"
        
        filters = {"id": str(id), "tenant_id": effective_tenant_id}
        
        # Check if exists first (we can look for even deleted ones to be safe, but typically we want to return 404 if not found)
        # But for delete idempotency on soft delete, we can check if it exists at all
        existing = select_table("incident_registers", filters=filters)
        if not existing:
             raise HTTPException(status_code=404, detail="Incident not found")

        # Soft delete
        data = {"is_deleted": "y"}
        updated_incident = update_table("incident_registers", data, filters=filters)
        
        if not updated_incident:
             raise HTTPException(status_code=500, detail="Failed to delete incident")

        return {"success": True, "message": "Incident deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

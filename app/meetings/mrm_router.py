from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import date
from uuid import UUID
from services.db_service import select_table, insert_table, update_table, delete_table, execute_query
from services.rbac_service import require_permission
from services.auth_service import get_user_from_token, auth_guard
from fastapi import Header


router = APIRouter(prefix="/mrm", tags=["Management Review Meeting"])


def ensure_mrm_table_schema():
    """Ensure management_review_meetings has optional project_id column."""
    try:
        execute_query(
            "ALTER TABLE public.management_review_meetings ADD COLUMN IF NOT EXISTS project_id UUID",
            fetch_all=False,
        )
    except Exception as e:
        print(f"MRM schema check (project_id): {e}")


class MRMBase(BaseModel):
    organization_id: UUID
    meeting_title: str
    meeting_date: date
    participants: Optional[str] = None
    agenda: Optional[str] = None
    key_discussions: Optional[str] = None
    decisions: Optional[str] = None
    action_items: Optional[str] = None
    next_meeting_date: Optional[date] = None
    created_by: Optional[str] = None
    tenant_id: Optional[str] = None
    project_id: Optional[UUID] = None

class MRMCreate(MRMBase):
    pass

class MRMUpdate(BaseModel):
    meeting_title: Optional[str] = None
    meeting_date: Optional[date] = None
    participants: Optional[str] = None
    agenda: Optional[str] = None
    key_discussions: Optional[str] = None
    decisions: Optional[str] = None
    action_items: Optional[str] = None
    next_meeting_date: Optional[date] = None
    project_id: Optional[UUID] = None

@router.get("", response_model=dict)
@require_permission("management_review_meetings_retrieve")
async def list_meetings(
    organization_id: Optional[UUID] = None,
    tenant_id: Optional[str] = Query(None),
    Authorization: Optional[str] = Header(None)
):
    try:
        user = auth_guard(Authorization)
        effective_tenant_id = user.get("tenant_id") or tenant_id or "00000000-0000-0000-0000-000000000001"
        
        ensure_mrm_table_schema()
        filters = {"tenant_id": effective_tenant_id}
        if organization_id:
            filters["organization_id"] = str(organization_id)
        
        # Add soft delete filter
        filters["is_deleted"] = "n"
        
        meetings = select_table("management_review_meetings", filters=filters, order_by="meeting_date DESC")
        return {"success": True, "data": meetings, "message": "Meetings retrieved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("", response_model=dict)
@require_permission("management_review_meetings_create")
async def create_meeting(meeting: MRMCreate, Authorization: Optional[str] = Header(None)):
    try:
        user = auth_guard(Authorization)
        effective_tenant_id = user.get("tenant_id") or "00000000-0000-0000-0000-000000000001"
        
        ensure_mrm_table_schema()
        data = meeting.model_dump()
        data["tenant_id"] = effective_tenant_id
        if data.get("project_id") is None:
            data.pop("project_id", None)
        # Ensure is_deleted is explicitly 'n' for new records
        data["is_deleted"] = "n"
        
        new_meeting = insert_table("management_review_meetings", data)
        if not new_meeting:
            raise HTTPException(status_code=500, detail="Failed to create meeting")
        return {"success": True, "data": new_meeting, "message": "Meeting created successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{id}", response_model=dict)
@require_permission("management_review_meetings_retrieve")
async def get_meeting(
    id: UUID, 
    tenant_id: Optional[str] = Query(None),
    Authorization: Optional[str] = Header(None)
):
    try:
        user = auth_guard(Authorization)
        effective_tenant_id = user.get("tenant_id") or tenant_id or "00000000-0000-0000-0000-000000000001"
        ensure_mrm_table_schema()
        # Add soft delete filter
        filters = {"id": str(id), "tenant_id": effective_tenant_id, "is_deleted": "n"}
        meetings = select_table("management_review_meetings", filters=filters)
        if not meetings:
            raise HTTPException(status_code=404, detail="Meeting not found")
        return {"success": True, "data": meetings[0], "message": "Meeting retrieved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{id}", response_model=dict)
@require_permission("management_review_meetings_update")
async def update_meeting(
    id: UUID, 
    meeting: MRMUpdate,
    tenant_id: Optional[str] = Query(None),
    Authorization: Optional[str] = Header(None)
):
    try:
        user = auth_guard(Authorization)
        effective_tenant_id = user.get("tenant_id") or tenant_id or "00000000-0000-0000-0000-000000000001"
        ensure_mrm_table_schema()
        data = meeting.model_dump(exclude_unset=True)
        if not data:
            raise HTTPException(status_code=400, detail="No fields to update")
            
        # Add soft delete filter to ensure we don't update deleted records
        filters = {"id": str(id), "tenant_id": effective_tenant_id, "is_deleted": "n"}
        
        # Check if exists first
        existing = select_table("management_review_meetings", filters=filters)
        if not existing:
             raise HTTPException(status_code=404, detail="Meeting not found")

        updated_meeting = update_table("management_review_meetings", data, filters=filters)
            
        return {"success": True, "data": updated_meeting, "message": "Meeting updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{id}", response_model=dict)
@require_permission("management_review_meetings_delete")
async def delete_meeting(
    id: UUID,
    tenant_id: Optional[str] = Query(None),
    Authorization: Optional[str] = Header(None)
):
    try:
        user = auth_guard(Authorization)
        effective_tenant_id = user.get("tenant_id") or tenant_id or "00000000-0000-0000-0000-000000000001"
        
        filters = {"id": str(id), "tenant_id": effective_tenant_id}
        
        # Check if exists first
        existing = select_table("management_review_meetings", filters=filters)
        if not existing:
             raise HTTPException(status_code=404, detail="Meeting not found")

        # Soft delete
        data = {"is_deleted": "y"}
        updated_meeting = update_table("management_review_meetings", data, filters=filters)
        
        if not updated_meeting:
             raise HTTPException(status_code=500, detail="Failed to delete meeting")

        return {"success": True, "message": "Meeting deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

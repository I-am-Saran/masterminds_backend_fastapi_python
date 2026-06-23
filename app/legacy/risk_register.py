# REFERENCE_ONLY_MODULE — legacy Kaizen module; preserved for compatibility.
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import date
from uuid import UUID
import uuid
from services.db_service import select_table, insert_table, update_table, delete_table
from services.rbac_service import require_permission
from services.auth_service import get_user_from_token, auth_guard
from fastapi import Header


router = APIRouter(prefix="/risk-register", tags=["Risk Register"])

class RiskBase(BaseModel):
    organization_id: UUID
    risk_title: str
    risk_description: Optional[str] = None
    category: Optional[str] = None
    likelihood: int = Field(..., ge=1, le=5)
    impact: int = Field(..., ge=1, le=5)
    mitigation_plan: Optional[str] = None
    owner: Optional[str] = None
    status: Optional[str] = "Open"
    target_date: Optional[date] = None
    due_date: Optional[date] = None
    revised_due_date: Optional[date] = None
    created_by: Optional[str] = None
    tenant_id: Optional[str] = None

class RiskCreate(RiskBase):
    pass

class RiskUpdate(BaseModel):
    risk_title: Optional[str] = None
    risk_description: Optional[str] = None
    category: Optional[str] = None
    likelihood: Optional[int] = Field(None, ge=1, le=5)
    impact: Optional[int] = Field(None, ge=1, le=5)
    mitigation_plan: Optional[str] = None
    owner: Optional[str] = None
    status: Optional[str] = None
    target_date: Optional[date] = None
    due_date: Optional[date] = None
    revised_due_date: Optional[date] = None


# New model for response, implied by the Code Edit
class RiskResponse(RiskBase):
    id: UUID
    created_at: Optional[date] = None
    updated_at: Optional[date] = None
    risk_score: Optional[int] = None
    is_deleted: Optional[str] = "n"

@router.get("/", response_model=dict)
@require_permission("risk_register_retrieve")
async def get_risk_registers(
    tenant_id: Optional[str] = Query(None),
    organization_id: Optional[str] = Query(None),
    Authorization: Optional[str] = Header(None)
):
    """
    Get all risk registers for a tenant.
    """
    try:
        user = auth_guard(Authorization)
        effective_tenant_id = user.get("tenant_id") or tenant_id or "00000000-0000-0000-0000-000000000001"
        
        filters = {"tenant_id": effective_tenant_id, "is_deleted": "n"}
        if organization_id:
            filters["organization_id"] = organization_id
            
        records = select_table("risk_registers", filters)
        return {"success": True, "data": records, "message": "Risks retrieved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{id}", response_model=dict)
@require_permission("risk_register_retrieve")
async def get_risk_register(
    id: str,
    tenant_id: Optional[str] = Query(None),
    Authorization: Optional[str] = Header(None)
):
    """
    Get a specific risk register by ID.
    """
    try:
        user = auth_guard(Authorization)
        effective_tenant_id = user.get("tenant_id") or tenant_id or "00000000-0000-0000-0000-000000000001"
        
        filters = {"id": id, "tenant_id": effective_tenant_id, "is_deleted": "n"}
        records = select_table("risk_registers", filters)
        if not records:
            raise HTTPException(status_code=404, detail="Risk register not found")
        return {"success": True, "data": records[0], "message": "Risk retrieved successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=dict)
@require_permission("risk_register_create")
async def create_risk(risk: RiskCreate, Authorization: Optional[str] = Header(None)):
    """
    Create a new risk register entry.
    """
    try:
        user = auth_guard(Authorization)
        effective_tenant_id = user.get("tenant_id") or "00000000-0000-0000-0000-000000000001"
        
        # Generate ID
        new_id = str(uuid.uuid4())
        
        # Prepare data
        data = risk.model_dump() 
        data["id"] = new_id
        data["tenant_id"] = effective_tenant_id
        # Ensure is_deleted is explicitly 'n' for new records
        data["is_deleted"] = "n"
        
        # Insert into database
        insert_table("risk_registers", data)
        
        # Fetch the newly created record to ensure all fields (including dates) are returned
        created_record = select_table("risk_registers", {"id": new_id})
        
        return {"success": True, "data": created_record[0] if created_record else data, "message": "Risk created successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{id}", response_model=dict)
@require_permission("risk_register_update")
async def update_risk(
    id: str, 
    risk: RiskUpdate,
    tenant_id: Optional[str] = Query(None),
    Authorization: Optional[str] = Header(None)
):
    """
    Update a risk register entry.
    """
    try:
        user = auth_guard(Authorization)
        effective_tenant_id = user.get("tenant_id") or tenant_id or "00000000-0000-0000-0000-000000000001"
        
        # Check if exists
        filters = {"id": id, "tenant_id": effective_tenant_id, "is_deleted": "n"}
        existing = select_table("risk_registers", filters)
        if not existing:
            raise HTTPException(status_code=404, detail="Risk register not found")
            
        # Update
        data = risk.model_dump(exclude_unset=True) # Changed .dict() to .model_dump() for Pydantic v2 compatibility
        result = update_table("risk_registers", data, filters)
        return {"success": True, "data": result, "message": "Risk updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{id}")
@require_permission("risk_register_delete")
async def delete_risk(
    id: str,
    tenant_id: Optional[str] = Query(None),
    Authorization: Optional[str] = Header(None)
):
    """
    Soft delete a risk register entry.
    """
    try:
        user = auth_guard(Authorization)
        effective_tenant_id = user.get("tenant_id") or tenant_id or "00000000-0000-0000-0000-000000000001"
        
        # Check if exists
        filters = {"id": id, "tenant_id": effective_tenant_id}
        # We don't necessarily need to check is_deleted for deletion, but let's check if it exists first
        existing = select_table("risk_registers", filters)
        if not existing:
            raise HTTPException(status_code=404, detail="Risk register not found")
            
        # Soft delete
        data = {"is_deleted": "y"}
        result = update_table("risk_registers", data, filters)
        return {"success": True, "message": "Risk register deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

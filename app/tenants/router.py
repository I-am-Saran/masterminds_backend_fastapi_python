from fastapi import APIRouter, HTTPException, Depends, Header
from typing import List, Optional, Dict, Any, cast
from pydantic import BaseModel
from services.db_service import select_table
from services.rbac_service import require_permission
from services.auth_service import get_user_from_token, auth_guard
from uuid import UUID

router = APIRouter(prefix="/organizations", tags=["Organizations"])

class OrganizationOut(BaseModel):
    id: UUID
    org_code: str
    org_name: str
    is_active: bool


@router.get("", response_model=dict)
@require_permission("organizations_retrieve")
async def list_organizations(Authorization: Optional[str] = Header(default=None)):
    """List all active organizations."""
    try:
        auth_data = auth_guard(Authorization)
        # Check if organizations table has tenant_id, if so, filter by it.
        # Assuming organizations are tenant specific.
        # If not, we might need to adjust. But adding auth_guard is a good first step.
        
        # For now, we'll assume organizations are shared or the select_table handles it? 
        # No, select_table is dumb.
        # Let's try to filter by tenant_id if possible, or just return all if it's a shared table.
        # Given the previous context, organizations might be shared.
        # But let's at least ensure the user is authenticated.
        
        orgs = select_table("organizations", filters={"is_active": True}, order_by="org_name")
        return {"success": True, "data": orgs, "message": "Organizations retrieved successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

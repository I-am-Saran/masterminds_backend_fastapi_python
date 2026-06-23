# REFERENCE_ONLY_MODULE — legacy Kaizen module; preserved for compatibility.
from fastapi import APIRouter, HTTPException, Depends, Header
from typing import List, Optional, Dict, Any, cast
from services.db_service import select_table, execute_query
from services.auth_service import get_user_from_token, auth_guard
from services.rbac_service import require_permission

router = APIRouter(prefix="/certifications", tags=["Certifications"])


@router.get("", response_model=Dict[str, Any])
@require_permission("certifications_retrieve")
async def list_certifications(Authorization: Optional[str] = Header(default=None)):
    """List all certifications."""
    try:
        auth_data = auth_guard(Authorization)
        tenant_id = auth_data.get("tenant_id")
        
        # Prefer tenant-scoped data, but many deployments keep master certifications without tenant_id.
        # 1) Try with tenant filter (if column exists)
        try:
            filters = {"tenant_id": tenant_id} if tenant_id else {}
            certs = select_table("certifications", filters=filters, order_by="name")
            if certs:
                return {"status": "success", "data": certs}
        except Exception as e:
            err = str(e).lower()
            # Fall through if tenant_id column does not exist or similar
            if "column" not in err and "does not exist" not in err and "undefinedcolumn" not in err:
                # Unknown error, re-raise
                raise
        
        # 2) Fallback to global list (no tenant filter), only Active
        try:
            sql = """
                SELECT * FROM certifications
                WHERE (status ILIKE 'active' OR status IS NULL)
                ORDER BY name
            """
            rows = execute_query(sql, (), fetch_all=True) or []
            return {"status": "success", "data": rows}
        except Exception as e:
            print(f"Error fetching certifications (fallback): {e}")
            return {"status": "error", "data": [], "error": str(e)}
    except Exception as e:
        # Fallback if table doesn't exist or other error, return empty list or handle gracefully
        print(f"Error fetching certifications: {e}")
        return {"status": "error", "data": [], "error": str(e)}

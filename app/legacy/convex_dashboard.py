# REFERENCE_ONLY_MODULE — legacy Kaizen module; preserved for compatibility.
from fastapi import APIRouter, HTTPException, Query, Body, Header
import os
import requests
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from services.rbac_service import require_permission
from services.auth_service import auth_guard

router = APIRouter(prefix="/convex", tags=["Convex Dashboard"])

EXTERNAL_API_BASE = "https://zuul.convexpro.in/waterfall"

def _get_token() -> str:
    for key in ("CONVEX_API_TOKEN", "VITE_CONVEX_API_TOKEN", "CONVEX_TOKEN"):
        token = (os.getenv(key) or "").strip()
        if token:
            return token
    raise HTTPException(
        status_code=500,
        detail="Server configuration error: CONVEX_API_TOKEN not set",
    )

def _waterfall_start_date() -> str:
    """First day of current calendar month at 00:00:00 UTC. e.g. 2026-05-01T00:00:00"""
    now = datetime.now(timezone.utc)
    dt = datetime(now.year, now.month, 1, 0, 0, 0, tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _build_convex_waterfall_body(start_date: Optional[str] = None) -> Dict[str, Any]:
    """Payload shape expected by zuul.convexpro.in/waterfall/json (no page/limit)."""
    start = (start_date or "").strip() or _waterfall_start_date()
    return {
        "projects": [],
        "startDate": start,
        "endDate": "",
        "milestones": False,
        "tasks": False,
        "tasklists": False,
        "separateSheet": False,
        "businessUnit": "",
        "businessVertical": "",
        "projectOwner": "",
        "projectManager": "",
        "businessFunction": [],
    }


def _extract_waterfall_items(raw: Any) -> List[Any]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        candidate = (
            raw.get("items")
            or raw.get("data")
            or raw.get("projects")
            or raw.get("content")
            or raw.get("records")
        )
        if isinstance(candidate, list):
            return candidate
    return []


def _normalize_waterfall_response(raw: Any, page: int, limit: int) -> Dict[str, Any]:
    items: List[Any] = []
    total: Optional[int] = None
    total_pages: Optional[int] = None

    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        candidate = (
            raw.get("items")
            or raw.get("data")
            or raw.get("projects")
            or raw.get("content")
            or raw.get("records")
        )
        if isinstance(candidate, list):
            items = candidate
        t = raw.get("total") or raw.get("totalCount") or raw.get("totalElements") or raw.get("totalProjects") or raw.get("count")
        if t is not None:
            try:
                total = int(t)
            except (TypeError, ValueError):
                total = None
        tp = raw.get("totalPages") or raw.get("pages") or raw.get("pageCount")
        if tp is not None:
            try:
                total_pages = int(tp)
            except (TypeError, ValueError):
                total_pages = None

    loaded = len(items)
    has_more = False
    if total_pages is not None and total_pages > 0:
        has_more = page < total_pages
    elif total is not None and total > 0:
        has_more = page * limit < total
    else:
        has_more = loaded >= limit

    resolved_total = total if total is not None and total > 0 else (page - 1) * limit + loaded
    if total_pages is not None and total_pages > 0:
        resolved_pages = total_pages
    elif has_more:
        resolved_pages = max(page + 1, (resolved_total + limit - 1) // limit if resolved_total else page + 1)
    else:
        resolved_pages = max(page, 1)

    return {
        "items": items,
        "page": page,
        "limit": limit,
        "total": resolved_total,
        "totalPages": resolved_pages,
        "hasMore": has_more,
        "loadedCount": loaded,
    }


class WaterfallPayload(BaseModel):
    updatedAfter: Optional[str] = None
    projects: List[str] = []
    startDate: str = ""
    endDate: str = ""
    milestones: bool = False
    tasklists: bool = False
    tasks: bool = False
    separateSheet: bool = False
    projectOwner: str = ""
    projectManager: str = ""
    businessUnit: str = ""
    businessVertical: str = ""
    businessFunction: List[str] = []
    page: int = Field(1, ge=1)
    limit: int = Field(50, ge=1, le=200)

@router.post("/waterfall/json")
@require_permission("convex_dashboard_retrieve")
def get_waterfall_json(payload: WaterfallPayload, Authorization: Optional[str] = Header(None)):
    """
    Proxy to https://zuul.convexpro.in/waterfall/json
    """
    auth_guard(Authorization)
    try:
        token = _get_token()
        url = f"{EXTERNAL_API_BASE}/json"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        start_date = (payload.startDate or "").strip() or _waterfall_start_date()
        data = _build_convex_waterfall_body(start_date)

        resp = requests.post(url, json=data, headers=headers, timeout=180)

        if not resp.ok:
            msg = resp.text
            try:
                body = resp.json()
                msg = body.get("message") or body.get("detail") or msg
            except Exception:
                pass
            raise HTTPException(status_code=resp.status_code, detail=msg or "Failed to fetch waterfall json")

        raw = resp.json()
        items = _extract_waterfall_items(raw)
        return {
            "items": items,
            "total": len(items),
            "hasMore": False,
            "page": 1,
            "limit": len(items),
            "totalPages": 1,
            "loadedCount": len(items),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects")
@require_permission("convex_dashboard_retrieve")
def get_projects(
    option: str | None = Query(None),
    statusId: str | None = Query(None),
    search: str = Query("", description="Search text"),
    pageNo: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=200),
    column: str = Query(""),
    value: str = Query(""),
    Authorization: Optional[str] = Header(None),
):
    """
    Proxy Convex 'projects' API with server-side filtering and pagination.
    """
    auth_guard(Authorization)
    try:
        token = _get_token()
        url = f"{EXTERNAL_API_BASE}/projects"
        params = {
            "option": option if option is not None else "null",
            "statusId": statusId if statusId is not None else "null",
            "search": search or "",
            "pageNo": pageNo - 1,
            "pageSize": pageSize,
            "column": column or "",
            "value": value or "",
        }
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        ct = resp.headers.get("content-type", "")
        if not resp.ok:
            msg = resp.text
            if "application/json" in ct:
                try:
                    body = resp.json()
                    msg = body.get("message") or body.get("detail") or msg
                except Exception:
                    pass
            raise HTTPException(status_code=resp.status_code, detail=msg or "Failed to fetch Convex projects")
        data = resp.json()
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

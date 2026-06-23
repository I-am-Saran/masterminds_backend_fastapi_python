"""Minutes of Meeting (MoM) module — lightweight CRUD APIs."""

import json
from datetime import date, datetime, time
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from services.auth_service import auth_guard
from services.db_service import execute_query, insert_table, update_table
from services.rbac_service import require_permission

router = APIRouter(prefix="/mom", tags=["Minutes of Meeting"])


# ---------------------------------------------------------------------------
# Enums & validation
# ---------------------------------------------------------------------------

class ActionStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    DONE = "DONE"


class ActionPriority(str, Enum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


MEETING_SORT_FIELDS = {
    "title", "meeting_date", "status", "organizer_name", "updated_at", "created_at"
}
ACTION_SORT_FIELDS = {
    "title", "due_date", "status", "priority", "assignee_name", "updated_at", "created_at"
}


def _user_display(user: Dict[str, Any]) -> str:
    return user.get("full_name") or user.get("email") or "Unknown"


def _serialize_row(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    out = dict(row)
    for key, val in out.items():
        if isinstance(val, datetime):
            out[key] = val.isoformat()
        elif isinstance(val, date):
            out[key] = val.isoformat()
        elif isinstance(val, time):
            out[key] = val.isoformat()
    return out


def _serialize_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [_serialize_row(r) for r in rows]


def _normalize_meeting(row: Dict[str, Any]) -> Dict[str, Any]:
    data = _serialize_row(row)
    data["organizer"] = data.pop("organizer_name", None)
    data.pop("organizer_id", None)
    participants = data.get("participants")
    if isinstance(participants, str):
        try:
            data["participants"] = json.loads(participants)
        except json.JSONDecodeError:
            data["participants"] = []
    elif participants is None:
        data["participants"] = []
    return data


def _normalize_action(row: Dict[str, Any]) -> Dict[str, Any]:
    data = _serialize_row(row)
    data["assignee"] = data.pop("assignee_name", None)
    data.pop("assignee_id", None)
    return data


def _parse_time_value(value: Any, meeting_date: Optional[date] = None) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, time):
        base = meeting_date or date.today()
        return datetime.combine(base, value)
    if isinstance(value, str):
        raw = value.strip()
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                t = datetime.strptime(raw, fmt).time()
                base = meeting_date or date.today()
                return datetime.combine(base, t)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid time format: {value}")
    raise HTTPException(status_code=400, detail=f"Invalid time value: {value}")


def _track_history(
    action_item_id: int,
    field_name: str,
    old_value: Any,
    new_value: Any,
    user: Dict[str, Any],
) -> None:
    old_str = "" if old_value is None else str(old_value)
    new_str = "" if new_value is None else str(new_value)
    if old_str == new_str:
        return
    insert_table(
        "mom_action_history",
        {
            "action_item_id": action_item_id,
            "field_name": field_name,
            "old_value": old_str or None,
            "new_value": new_str or None,
            "changed_by_name": _user_display(user),
        },
    )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class MeetingCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    meeting_type: Optional[str] = None
    meeting_date: date
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    organizer: Optional[str] = None
    client_email: Optional[str] = None
    participants: Optional[List[str]] = None
    notes: Optional[str] = None
    status: Optional[str] = "OPEN"


class MeetingUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    meeting_type: Optional[str] = None
    meeting_date: Optional[date] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    organizer: Optional[str] = None
    client_email: Optional[str] = None
    participants: Optional[List[str]] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class ActionItemCreate(BaseModel):
    meeting_id: int
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    assignee: Optional[str] = None
    due_date: Optional[date] = None
    status: ActionStatus = ActionStatus.OPEN
    priority: ActionPriority = ActionPriority.P3

    @field_validator("due_date")
    @classmethod
    def validate_due_date(cls, v: Optional[date]) -> Optional[date]:
        return v


class ActionItemUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    assignee: Optional[str] = None
    due_date: Optional[date] = None
    status: Optional[ActionStatus] = None
    priority: Optional[ActionPriority] = None
    sort_order: Optional[int] = None


class CommentCreate(BaseModel):
    comment: str = Field(..., min_length=1)


MOM_OPEN_STATUSES = ("OPEN", "IN_PROGRESS", "BLOCKED")
MOM_AGE_BUCKETS = [
    {"id": "0-2", "label": "0–2 Days", "min": 0, "max": 2},
    {"id": "3-7", "label": "3–7 Days", "min": 3, "max": 7},
    {"id": "8-14", "label": "8–14 Days", "min": 8, "max": 14},
    {"id": "15-30", "label": "15–30 Days", "min": 15, "max": 30},
    {"id": "30+", "label": "30+ Days", "min": 31, "max": 99999},
]


def _team_member_emails(team_id: str, tenant_id: str) -> List[str]:
    rows = execute_query(
        """
        SELECT DISTINCT LOWER(TRIM(u.email)) AS email
        FROM team_users tu
        JOIN users u ON tu.user_id::text = u.id::text OR LOWER(TRIM(tu.user_id::text)) = LOWER(TRIM(u.email))
        WHERE tu.team_id = %s AND tu.tenant_id = %s AND u.email IS NOT NULL AND TRIM(u.email) <> ''
        """,
        (team_id, tenant_id),
        fetch_all=True,
    ) or []
    return [r["email"] for r in rows if r.get("email")]


def _team_filter_sql(team_id: Optional[str], tenant_id: str, alias: str = "ai") -> tuple:
    """Return (sql_fragment, params) for filtering action items by team assignees."""
    if not team_id:
        return "", []
    emails = _team_member_emails(team_id, tenant_id)
    if not emails:
        return " AND 1=0", []
    placeholders = ", ".join(["%s"] * len(emails))
    return f" AND LOWER(TRIM({alias}.assignee_name)) IN ({placeholders})", emails


def _meetings_team_filter_sql(team_id: Optional[str], tenant_id: str) -> tuple:
    if not team_id:
        return "", []
    emails = _team_member_emails(team_id, tenant_id)
    if not emails:
        return " AND 1=0", []
    placeholders = ", ".join(["%s"] * len(emails))
    return (
        f"""
        AND (
            LOWER(TRIM(m.organizer_name)) IN ({placeholders})
            OR m.id IN (
                SELECT DISTINCT ai.meeting_id
                FROM mom_action_items ai
                WHERE LOWER(TRIM(ai.assignee_name)) IN ({placeholders})
            )
        )
        """,
        emails + emails,
    )


def _action_age_days(created_at: Any) -> int:
    if not created_at:
        return 0
    if isinstance(created_at, datetime):
        dt = created_at
    elif isinstance(created_at, date):
        dt = datetime.combine(created_at, datetime.min.time())
    else:
        try:
            dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        except ValueError:
            return 0
    if dt.tzinfo:
        dt = dt.replace(tzinfo=None)
    delta = datetime.utcnow() - dt
    return max(0, delta.days)


def _age_bucket_label(age_days: int) -> str:
    for b in MOM_AGE_BUCKETS:
        if b["min"] <= age_days <= b["max"]:
            return b["label"]
    return MOM_AGE_BUCKETS[-1]["label"]


# ---------------------------------------------------------------------------
# Dashboard metrics
# ---------------------------------------------------------------------------

@router.get("/dashboard-metrics")
@require_permission("mom_retrieve")
async def dashboard_metrics(
    team_id: Optional[str] = Query(None),
    mine: Optional[bool] = Query(False),
    Authorization: Optional[str] = Header(None),
):
    user_ctx = auth_guard(Authorization)
    user = user_ctx.get("user") or {}
    tenant_id = user.get("tenant_id") or "00000000-0000-0000-0000-000000000001"

    action_conds = ["1=1"]
    action_params: List[Any] = []
    meeting_conds = ["1=1"]
    meeting_params: List[Any] = []

    team_sql, team_params = _team_filter_sql(team_id, tenant_id, "ai")
    if team_sql:
        action_conds.append(team_sql.replace(" AND ", "", 1).strip())
        action_params.extend(team_params)

    meet_team_sql, meet_team_params = _meetings_team_filter_sql(team_id, tenant_id)
    if meet_team_sql:
        meeting_conds.append(f"({meet_team_sql.replace(' AND ', '', 1).strip()})")
        meeting_params.extend(meet_team_params)

    if mine:
        email = (user.get("email") or "").strip().lower()
        if not email:
            action_conds.append("1=0")
        else:
            action_conds.append("LOWER(TRIM(ai.assignee_name)) = %s")
            action_params.append(email)

    action_where = " AND ".join(action_conds)
    meeting_where = " AND ".join(meeting_conds)

    status_rows = execute_query(
        f"""
        SELECT ai.status, COUNT(*) AS cnt
        FROM mom_action_items ai
        WHERE {action_where}
        GROUP BY ai.status
        """,
        tuple(action_params),
        fetch_all=True,
    ) or []

    by_status = {s.value: 0 for s in ActionStatus}
    total_actions = 0
    for row in status_rows:
        key = (row.get("status") or "OPEN").upper()
        cnt = int(row.get("cnt") or 0)
        by_status[key] = by_status.get(key, 0) + cnt
        total_actions += cnt

    if mine:
        meeting_count_row = execute_query(
            f"""
            SELECT COUNT(DISTINCT m.id) AS total
            FROM mom_meetings m
            JOIN mom_action_items ai ON ai.meeting_id = m.id
            WHERE {action_where}
            """,
            tuple(action_params),
            fetch_one=True,
        )
    else:
        meeting_count_row = execute_query(
            f"SELECT COUNT(*) AS total FROM mom_meetings m WHERE {meeting_where}",
            tuple(meeting_params),
            fetch_one=True,
        )
    total_meetings = int(meeting_count_row["total"] or 0) if meeting_count_row else 0

    open_rows = execute_query(
        f"""
        SELECT ai.priority, ai.created_at
        FROM mom_action_items ai
        WHERE {action_where} AND ai.status IN ('OPEN', 'IN_PROGRESS', 'BLOCKED')
        """,
        tuple(action_params),
        fetch_all=True,
    ) or []

    ageing = {
        b["label"]: {"name": b["label"], "bucketId": b["id"], "P1": 0, "P2": 0, "P3": 0, "total": 0}
        for b in MOM_AGE_BUCKETS
    }
    for row in open_rows:
        age = _action_age_days(row.get("created_at"))
        label = _age_bucket_label(age)
        bucket = ageing.get(label)
        if not bucket:
            continue
        pr = (row.get("priority") or "P3").upper()
        if pr not in ("P1", "P2", "P3"):
            pr = "P3"
        bucket[pr] += 1
        bucket["total"] += 1

    ageing_chart = [ageing[b["label"]] for b in MOM_AGE_BUCKETS]

    return {
        "success": True,
        "data": {
            "total_meetings": total_meetings,
            "total_action_items": total_actions,
            "by_status": by_status,
            "open_count": sum(by_status.get(s, 0) for s in MOM_OPEN_STATUSES),
            "ageing_by_priority": ageing_chart,
        },
        "message": "Dashboard metrics retrieved successfully",
    }


# ---------------------------------------------------------------------------
# Meetings
# ---------------------------------------------------------------------------

@router.get("/meetings")
@require_permission("mom_retrieve")
async def list_meetings(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    team_id: Optional[str] = Query(None),
    sort_by: str = Query("meeting_date"),
    sort_desc: bool = Query(True),
    Authorization: Optional[str] = Header(None),
):
    user_ctx = auth_guard(Authorization)
    user = user_ctx.get("user") or {}
    tenant_id = user.get("tenant_id") or "00000000-0000-0000-0000-000000000001"

    sort_col = sort_by if sort_by in MEETING_SORT_FIELDS else "meeting_date"
    direction = "DESC" if sort_desc else "ASC"

    conditions = ["1=1"]
    params: List[Any] = []

    meet_team_sql, meet_team_params = _meetings_team_filter_sql(team_id, tenant_id)
    if meet_team_sql:
        conditions.append(f"({meet_team_sql.replace(' AND ', '', 1).strip()})")
        params.extend(meet_team_params)

    if search:
        conditions.append("m.title ILIKE %s")
        params.append(f"%{search.strip()}%")
    if status:
        conditions.append("m.status = %s")
        params.append(status)
    if date_from:
        conditions.append("m.meeting_date >= %s")
        params.append(date_from)
    if date_to:
        conditions.append("m.meeting_date <= %s")
        params.append(date_to)

    where = " AND ".join(conditions)
    offset = (page - 1) * limit

    count_row = execute_query(
        f"SELECT COUNT(*) AS total FROM mom_meetings m WHERE {where}",
        tuple(params),
        fetch_one=True,
    )
    total = count_row["total"] if count_row else 0

    rows = execute_query(
        f"""
        SELECT m.*,
               COALESCE(p.pending_count, 0) AS pending_actions
        FROM mom_meetings m
        LEFT JOIN (
            SELECT meeting_id, COUNT(*) AS pending_count
            FROM mom_action_items
            WHERE status != 'DONE'
            GROUP BY meeting_id
        ) p ON p.meeting_id = m.id
        WHERE {where}
        ORDER BY m.{sort_col} {direction}
        LIMIT %s OFFSET %s
        """,
        tuple(params + [limit, offset]),
        fetch_all=True,
    ) or []

    data = [_normalize_meeting(r) for r in rows]
    return {
        "success": True,
        "data": data,
        "meta": {"total": total, "page": page, "limit": limit},
        "message": "Meetings retrieved successfully",
    }


@router.get("/meetings/{meeting_id}")
@require_permission("mom_retrieve")
async def get_meeting(
    meeting_id: int,
    Authorization: Optional[str] = Header(None),
):
    auth_guard(Authorization)

    rows = execute_query(
        "SELECT * FROM mom_meetings WHERE id = %s",
        (meeting_id,),
        fetch_all=True,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Meeting not found")

    action_rows = execute_query(
        """
        SELECT ai.*, COALESCE(c.comment_count, 0) AS comment_count
        FROM mom_action_items ai
        LEFT JOIN (
            SELECT action_item_id, COUNT(*) AS comment_count
            FROM mom_action_comments
            GROUP BY action_item_id
        ) c ON c.action_item_id = ai.id
        WHERE ai.meeting_id = %s
        ORDER BY ai.sort_order ASC, ai.id ASC
        """,
        (meeting_id,),
        fetch_all=True,
    ) or []

    meeting = _normalize_meeting(rows[0])
    meeting["action_items"] = [_normalize_action(r) for r in action_rows]
    return {"success": True, "data": meeting, "message": "Meeting retrieved successfully"}


@router.post("/meetings")
@require_permission("mom_create")
async def create_meeting(
    payload: MeetingCreate,
    Authorization: Optional[str] = Header(None),
):
    user_ctx = auth_guard(Authorization)
    user = user_ctx.get("user") or {}

    meeting_date = payload.meeting_date
    data = {
        "title": payload.title.strip(),
        "meeting_type": payload.meeting_type,
        "meeting_date": meeting_date,
        "start_time": _parse_time_value(payload.start_time, meeting_date),
        "end_time": _parse_time_value(payload.end_time, meeting_date),
        "organizer_name": payload.organizer or _user_display(user),
        "client_email": (payload.client_email or "").strip() or None,
        "participants": json.dumps(payload.participants or []),
        "notes": payload.notes,
        "status": payload.status or "OPEN",
    }

    created = insert_table("mom_meetings", data)
    if not created:
        raise HTTPException(status_code=500, detail="Failed to create meeting")
    return {
        "success": True,
        "data": _normalize_meeting(created),
        "message": "Meeting created successfully",
    }


@router.put("/meetings/{meeting_id}")
@require_permission("mom_update")
async def update_meeting(
    meeting_id: int,
    payload: MeetingUpdate,
    Authorization: Optional[str] = Header(None),
):
    auth_guard(Authorization)

    existing_rows = execute_query(
        "SELECT * FROM mom_meetings WHERE id = %s",
        (meeting_id,),
        fetch_all=True,
    )
    if not existing_rows:
        raise HTTPException(status_code=404, detail="Meeting not found")

    existing = existing_rows[0]
    immutable_on_update = {"title", "meeting_type", "meeting_date", "start_time", "end_time"}
    updates = {
        k: v
        for k, v in payload.model_dump(exclude_unset=True).items()
        if k not in immutable_on_update
    }
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    data: Dict[str, Any] = {}
    meeting_date = existing["meeting_date"]
    if "organizer" in updates:
        data["organizer_name"] = updates["organizer"]
    if "client_email" in updates:
        data["client_email"] = (updates["client_email"] or "").strip() or None
    if "participants" in updates:
        data["participants"] = json.dumps(updates["participants"] or [])
    if "notes" in updates:
        data["notes"] = updates["notes"]
    if "status" in updates:
        data["status"] = updates["status"]

    data["updated_at"] = datetime.utcnow()

    updated = update_table("mom_meetings", data, filters={"id": meeting_id})
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update meeting")
    return {
        "success": True,
        "data": _normalize_meeting(updated),
        "message": "Meeting updated successfully",
    }


@router.delete("/meetings/{meeting_id}")
@require_permission("mom_delete")
async def delete_meeting(
    meeting_id: int,
    Authorization: Optional[str] = Header(None),
):
    auth_guard(Authorization)

    existing = execute_query(
        "SELECT id FROM mom_meetings WHERE id = %s",
        (meeting_id,),
        fetch_one=True,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Meeting not found")

    execute_query(
        "DELETE FROM mom_meetings WHERE id = %s",
        (meeting_id,),
        fetch_all=False,
    )
    return {"success": True, "message": "Meeting deleted successfully"}


# ---------------------------------------------------------------------------
# Action items
# ---------------------------------------------------------------------------

@router.get("/action-items")
@require_permission("mom_retrieve")
async def list_action_items(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    meeting_id: Optional[int] = Query(None),
    assignee: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    overdue: Optional[bool] = Query(None),
    pending: Optional[bool] = Query(None),
    mine: Optional[bool] = Query(None),
    team_id: Optional[str] = Query(None),
    sort_by: str = Query("due_date"),
    sort_desc: bool = Query(False),
    Authorization: Optional[str] = Header(None),
):
    from app.tasks.dependencies import get_auth_context
    from app.tasks.service import TaskService

    auth = get_auth_context(Authorization)
    tenant_id = auth["tenant_id"]

    kaizen_result = TaskService.list_tasks(
        tenant_id,
        page=page,
        limit=limit,
        meeting_id=meeting_id,
        source_type="meeting",
        status=status,
        priority=priority,
        overdue=overdue,
        mine_email=auth["email"] if mine else None,
        sort_by=sort_by if sort_by in {"due_date", "status", "priority", "title", "updated_at", "created_at", "owner_email"} else "due_date",
        sort_desc=sort_desc,
    )
    if kaizen_result.get("meta", {}).get("total", 0) > 0 or not team_id:
        data = [TaskService.normalize_for_mom(r) for r in kaizen_result.get("data", [])]
        if assignee:
            needle = assignee.strip().lower()
            data = [d for d in data if needle in (d.get("assignee") or "").lower()]
        if pending:
            data = [d for d in data if d.get("status") in ("OPEN", "IN_PROGRESS", "BLOCKED")]
        return {
            "success": True,
            "data": data,
            "meta": kaizen_result.get("meta", {}),
            "message": "Action items retrieved successfully",
        }

    user_ctx = auth_guard(Authorization)
    user = user_ctx.get("user") or {}

    sort_col = sort_by if sort_by in ACTION_SORT_FIELDS else "due_date"
    direction = "DESC" if sort_desc else "ASC"

    conditions = ["1=1"]
    params: List[Any] = []

    team_sql, team_params = _team_filter_sql(team_id, tenant_id, "ai")
    if team_sql:
        conditions.append(team_sql.replace(" AND ", "", 1).strip())
        params.extend(team_params)

    if meeting_id is not None:
        conditions.append("ai.meeting_id = %s")
        params.append(meeting_id)
    if assignee:
        conditions.append("ai.assignee_name ILIKE %s")
        params.append(f"%{assignee.strip()}%")
    if status:
        conditions.append("ai.status = %s")
        params.append(status)
    if priority:
        conditions.append("ai.priority = %s")
        params.append(priority)
    if overdue:
        conditions.append("ai.due_date < CURRENT_DATE AND ai.status != 'DONE'")
    if pending:
        conditions.append("ai.status IN ('OPEN', 'IN_PROGRESS', 'BLOCKED')")
    if mine:
        email = (user.get("email") or "").strip()
        if not email:
            conditions.append("1=0")
        else:
            conditions.append("LOWER(TRIM(ai.assignee_name)) = LOWER(%s)")
            params.append(email)

    where = " AND ".join(conditions)
    offset = (page - 1) * limit

    count_row = execute_query(
        f"SELECT COUNT(*) AS total FROM mom_action_items ai WHERE {where}",
        tuple(params),
        fetch_one=True,
    )
    total = count_row["total"] if count_row else 0

    rows = execute_query(
        f"""
        SELECT ai.*,
               m.title AS meeting_title,
               m.meeting_date,
               COALESCE(c.comment_count, 0) AS comment_count
        FROM mom_action_items ai
        JOIN mom_meetings m ON m.id = ai.meeting_id
        LEFT JOIN (
            SELECT action_item_id, COUNT(*) AS comment_count
            FROM mom_action_comments
            GROUP BY action_item_id
        ) c ON c.action_item_id = ai.id
        WHERE {where}
        ORDER BY ai.{sort_col} {direction} NULLS LAST, ai.id ASC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [limit, offset]),
        fetch_all=True,
    ) or []

    data = [_normalize_action(r) for r in rows]
    return {
        "success": True,
        "data": data,
        "meta": {"total": total, "page": page, "limit": limit},
        "message": "Action items retrieved successfully",
    }


@router.post("/action-items")
@require_permission("mom_create")
async def create_action_item(
    payload: ActionItemCreate,
    Authorization: Optional[str] = Header(None),
):
    from app.tasks.dependencies import get_auth_context
    from app.tasks.service import TaskService

    auth = get_auth_context(Authorization)
    result = TaskService.create_from_meeting(
        {
            "meeting_id": payload.meeting_id,
            "title": payload.title.strip(),
            "description": payload.description,
            "assignee": payload.assignee,
            "due_date": payload.due_date,
            "status": payload.status.value,
            "priority": payload.priority.value,
        },
        auth,
    )
    return {
        "success": True,
        "data": TaskService.normalize_for_mom(result["data"]),
        "message": "Action item created successfully",
    }


@router.put("/action-items/{action_id}")
@require_permission("mom_update")
async def update_action_item(
    action_id: int,
    payload: ActionItemUpdate,
    Authorization: Optional[str] = Header(None),
):
    from app.tasks.dependencies import get_auth_context
    from app.tasks.schemas import TaskUpdate
    from app.tasks.service import TaskService

    auth = get_auth_context(Authorization)
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    task_updates: Dict[str, Any] = {}
    if "title" in updates:
        task_updates["title"] = updates["title"]
    if "description" in updates:
        task_updates["description"] = updates["description"]
    if "assignee" in updates:
        task_updates["owner_email"] = updates["assignee"]
    if "due_date" in updates:
        task_updates["due_date"] = updates["due_date"]
    if "status" in updates:
        task_updates["status"] = updates["status"]
    if "priority" in updates:
        task_updates["priority"] = updates["priority"]

    existing = TaskService.get_task_by_legacy_mom_id(action_id, auth["tenant_id"])
    if existing:
        result = TaskService.update_task(existing["id"], TaskUpdate(**task_updates), auth)
        return {
            "success": True,
            "data": TaskService.normalize_for_mom(result["data"]),
            "message": "Action item updated successfully",
        }

    # Legacy row without kaizen_tasks link — update mom_action_items only
    user_ctx = auth_guard(Authorization)
    user = user_ctx.get("user") or {}
    existing_rows = execute_query(
        "SELECT * FROM mom_action_items WHERE id = %s",
        (action_id,),
        fetch_all=True,
    )
    if not existing_rows:
        raise HTTPException(status_code=404, detail="Action item not found")
    existing = existing_rows[0]
    data: Dict[str, Any] = {"updated_at": datetime.utcnow()}
    if "title" in updates:
        data["title"] = updates["title"].strip()
    if "description" in updates:
        data["description"] = updates["description"]
    if "assignee" in updates:
        data["assignee_name"] = updates["assignee"]
    if "due_date" in updates:
        data["due_date"] = updates["due_date"]
    if "status" in updates:
        data["status"] = (
            updates["status"].value if hasattr(updates["status"], "value") else updates["status"]
        )
    if "priority" in updates:
        data["priority"] = (
            updates["priority"].value if hasattr(updates["priority"], "value") else updates["priority"]
        )
    updated = update_table("mom_action_items", data, filters={"id": action_id})
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update action item")
    return {
        "success": True,
        "data": _normalize_action(updated),
        "message": "Action item updated successfully",
    }


@router.delete("/action-items/{action_id}")
@require_permission("mom_delete")
async def delete_action_item(
    action_id: int,
    Authorization: Optional[str] = Header(None),
):
    from app.tasks.dependencies import get_auth_context
    from app.tasks.service import TaskService

    auth = get_auth_context(Authorization)
    return TaskService.delete_by_legacy_mom_id(action_id, auth["tenant_id"])


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

@router.get("/action-items/{action_id}/comments")
@require_permission("mom_retrieve")
async def list_comments(
    action_id: int,
    Authorization: Optional[str] = Header(None),
):
    auth_guard(Authorization)

    action = execute_query(
        "SELECT id FROM mom_action_items WHERE id = %s",
        (action_id,),
        fetch_one=True,
    )
    if not action:
        raise HTTPException(status_code=404, detail="Action item not found")

    rows = execute_query(
        """
        SELECT id, action_item_id, comment, commented_by_name, created_at
        FROM mom_action_comments
        WHERE action_item_id = %s
        ORDER BY created_at DESC
        """,
        (action_id,),
        fetch_all=True,
    ) or []

    return {
        "success": True,
        "data": _serialize_rows(rows),
        "message": "Comments retrieved successfully",
    }


@router.post("/action-items/{action_id}/comments")
@require_permission("mom_create")
async def create_comment(
    action_id: int,
    payload: CommentCreate,
    Authorization: Optional[str] = Header(None),
):
    user_ctx = auth_guard(Authorization)
    user = user_ctx.get("user") or {}

    action = execute_query(
        "SELECT id FROM mom_action_items WHERE id = %s",
        (action_id,),
        fetch_one=True,
    )
    if not action:
        raise HTTPException(status_code=404, detail="Action item not found")

    created = insert_table(
        "mom_action_comments",
        {
            "action_item_id": action_id,
            "comment": payload.comment.strip(),
            "commented_by_name": _user_display(user),
        },
    )
    if not created:
        raise HTTPException(status_code=500, detail="Failed to create comment")

    return {
        "success": True,
        "data": _serialize_row(created),
        "message": "Comment added successfully",
    }

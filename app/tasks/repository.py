"""Repository — kaizen_tasks and related tables."""

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import uuid

from services.db_service import execute_query, insert_table, update_table

from app.tasks.constants import (
    SORT_FIELDS,
    STALE_DAYS,
    TABLE_COMMENTS,
    TABLE_HISTORY,
    TABLE_PRIORITIES,
    TABLE_STATUSES,
    TABLE_TASKS,
    TABLE_WATCHERS,
    TERMINAL_STATUSES,
    TICKET_CATEGORIES,
)
from app.tasks.models import KAIZEN_TASK_COLUMNS


def _serialize(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    out = dict(row)
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        elif isinstance(v, date):
            out[k] = v.isoformat()
        elif isinstance(v, uuid.UUID):
            out[k] = str(v)

    due = out.get("due_date")
    status = (out.get("status") or "").upper()
    if due and status not in TERMINAL_STATUSES:
        try:
            due_d = date.fromisoformat(str(due)[:10]) if not isinstance(due, date) else due
            out["ageing_days"] = (date.today() - due_d).days
        except (TypeError, ValueError):
            pass
    return out


def _base_select() -> str:
    return f"""
        SELECT t.*,
               m.title AS meeting_title,
               COALESCE(c.cnt, 0)::int AS comment_count,
               reporter.email AS created_by_email,
               wi.workflow_status AS workflow_instance_status,
               wl.level_sequence AS workflow_level_sequence
        FROM {TABLE_TASKS} t
        LEFT JOIN mom_meetings m ON m.id = t.meeting_id
        LEFT JOIN users reporter ON reporter.uuid_id = t.created_by
        LEFT JOIN (
            SELECT task_id, COUNT(*) AS cnt
            FROM {TABLE_COMMENTS}
            GROUP BY task_id
        ) c ON c.task_id = t.id
        LEFT JOIN workflow_ticket_instances wi ON wi.ticket_id = t.id
        LEFT JOIN workflow_levels wl ON wl.id = wi.current_level_id
    """


def _not_deleted() -> str:
    return "t.is_deleted = FALSE"


def _normalize_email(email: Optional[str]) -> Optional[str]:
    if not email:
        return None
    normalized = email.strip().lower()
    return normalized or None


def resolve_owner_uuids(emails: List[str]) -> Dict[str, Optional[str]]:
    normalized_emails = []
    seen = set()
    for email in emails:
        normalized = _normalize_email(email)
        if normalized and normalized not in seen:
            seen.add(normalized)
            normalized_emails.append(normalized)

    if not normalized_emails:
        return {}

    placeholders = ", ".join(["%s"] * len(normalized_emails))
    rows = execute_query(
        f"""
        SELECT LOWER(email) AS email_key, uuid_id
        FROM users
        WHERE LOWER(email) IN ({placeholders})
        """,
        tuple(normalized_emails),
        fetch_all=True,
    ) or []

    resolved = {email: None for email in normalized_emails}
    for row in rows:
        email_key = row.get("email_key")
        if email_key:
            resolved[str(email_key)] = str(row["uuid_id"]) if row.get("uuid_id") else None
    return resolved


def resolve_owner_uuid(email: Optional[str]) -> Optional[str]:
    normalized = _normalize_email(email)
    if not normalized:
        return None
    return resolve_owner_uuids([normalized]).get(normalized)


def _load_watchers(task_id: str) -> List[str]:
    watchers = execute_query(
        f"SELECT user_email FROM {TABLE_WATCHERS} WHERE task_id = %s ORDER BY user_email",
        (task_id,),
        fetch_all=True,
    ) or []
    return [w["user_email"] for w in watchers]


def list_tasks(
    tenant_id: str,
    *,
    page: int = 1,
    limit: int = 50,
    search: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    owner_email: Optional[str] = None,
    meeting_id: Optional[int] = None,
    overdue: Optional[bool] = None,
    blocked: Optional[bool] = None,
    mine_email: Optional[str] = None,
    raised_by_email: Optional[str] = None,
    stale: Optional[bool] = None,
    source_type: Optional[str] = None,
    category: Optional[str] = None,
    sort_by: str = "due_date",
    sort_desc: bool = False,
) -> Tuple[List[Dict[str, Any]], int]:
    conds = [_not_deleted(), "t.tenant_id = %s"]
    params: List[Any] = [tenant_id]

    if search:
        q = f"%{search.strip()}%"
        conds.append("(t.title ILIKE %s OR t.description ILIKE %s OR t.owner_email ILIKE %s)")
        params.extend([q, q, q])
    if status:
        conds.append("t.status = %s")
        params.append(status.upper())
    if priority:
        conds.append("t.priority = %s")
        params.append(priority.upper())
    if owner_email:
        conds.append("LOWER(t.owner_email) = LOWER(%s)")
        params.append(owner_email.strip())
    if meeting_id is not None:
        conds.append("t.meeting_id = %s")
        params.append(meeting_id)
    if source_type:
        conds.append("t.source_type = %s")
        params.append(source_type.lower())
    if category:
        conds.append("t.category = %s")
        params.append(category.strip())
    if overdue:
        conds.append("t.due_date < CURRENT_DATE AND t.status NOT IN ('DONE', 'CANCELLED')")
    if blocked is True:
        conds.append("(t.is_blocked = TRUE OR t.status = 'BLOCKED')")
    elif blocked is False:
        conds.append("t.is_blocked = FALSE AND t.status != 'BLOCKED'")
    if mine_email:
        conds.append("LOWER(t.owner_email) = LOWER(%s)")
        params.append(mine_email)
    if raised_by_email:
        # created_by stores users.uuid_id, not users.id from the JWT
        conds.append(
            """EXISTS (
                SELECT 1 FROM users u
                WHERE u.uuid_id = t.created_by
                  AND LOWER(u.email) = LOWER(%s)
            )"""
        )
        params.append(raised_by_email.strip())
    if stale:
        conds.append(
            f"t.status NOT IN ('DONE', 'CANCELLED') "
            f"AND t.last_activity_at < NOW() - INTERVAL '{STALE_DAYS} days'"
        )

    where = " AND ".join(conds)
    sort_col = sort_by if sort_by in SORT_FIELDS else "due_date"
    order_col = f"t.{sort_col}"
    direction = "DESC" if sort_desc else "ASC"
    offset = (page - 1) * limit

    total_row = execute_query(
        f"SELECT COUNT(*) AS total FROM {TABLE_TASKS} t WHERE {where}",
        tuple(params),
        fetch_one=True,
    )
    total = int(total_row["total"]) if total_row else 0

    rows = execute_query(
        f"""
        {_base_select()}
        WHERE {where}
        ORDER BY {order_col} {direction} NULLS LAST, t.created_at DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [limit, offset]),
        fetch_all=True,
    ) or []
    return [_serialize(r) for r in rows], total


def get_by_legacy_mom_action_id(
    legacy_id: int, tenant_id: str, *, include_watchers: bool = True
) -> Optional[Dict[str, Any]]:
    row = execute_query(
        f"""
        {_base_select()}
        WHERE t.legacy_mom_action_id = %s AND t.tenant_id = %s AND {_not_deleted()}
        LIMIT 1
        """,
        (legacy_id, tenant_id),
        fetch_one=True,
    )
    if not row:
        return None
    data = _serialize(row)
    if include_watchers and data:
        data["watchers"] = _load_watchers(str(data["id"]))
    return data


def get_by_id(task_id: str, tenant_id: str, *, include_watchers: bool = True) -> Optional[Dict[str, Any]]:
    row = execute_query(
        f"""
        {_base_select()}
        WHERE t.id = %s AND t.tenant_id = %s AND {_not_deleted()}
        LIMIT 1
        """,
        (task_id, tenant_id),
        fetch_one=True,
    )
    if not row:
        return None
    data = _serialize(row)
    if include_watchers and data:
        data["watchers"] = _load_watchers(task_id)
    return data


def insert_task(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    payload = {k: v for k, v in data.items() if k in KAIZEN_TASK_COLUMNS and v is not None}
    payload.setdefault("id", str(uuid.uuid4()))
    payload.setdefault("created_at", now)
    payload.setdefault("updated_at", now)
    payload.setdefault("last_activity_at", now)
    created = insert_table(TABLE_TASKS, payload)
    if not created:
        return None
    return _serialize(created)


def update_task(
    task_id: str,
    tenant_id: str,
    data: Dict[str, Any],
    *,
    refresh: bool = True,
    include_watchers: bool = True,
) -> Optional[Dict[str, Any]]:
    payload = {k: v for k, v in data.items() if k in KAIZEN_TASK_COLUMNS and k not in ("id", "tenant_id")}
    payload["updated_at"] = datetime.now(timezone.utc)
    payload["last_activity_at"] = payload["updated_at"]
    if not payload:
        return get_by_id(task_id, tenant_id, include_watchers=include_watchers)
    updated = update_table(TABLE_TASKS, payload, filters={"id": task_id, "tenant_id": tenant_id})
    if not updated:
        return None
    if not refresh:
        return _serialize(updated)
    return get_by_id(task_id, tenant_id, include_watchers=include_watchers)


def soft_delete(task_id: str, tenant_id: str) -> bool:
    updated = update_table(
        TABLE_TASKS,
        {"is_deleted": True, "updated_at": datetime.now(timezone.utc)},
        filters={"id": task_id, "tenant_id": tenant_id},
    )
    return bool(updated)


def insert_activity(
    task_id: str,
    message: str,
    *,
    changed_by_email: Optional[str],
    changed_by_id: Optional[str],
) -> None:
    """Record a human-readable activity line in ticket history."""
    insert_history(
        task_id,
        "activity",
        None,
        message,
        changed_by_email=changed_by_email,
        changed_by_id=changed_by_id,
    )


def insert_history(
    task_id: str,
    field_name: str,
    old_value: Any,
    new_value: Any,
    *,
    changed_by_email: Optional[str],
    changed_by_id: Optional[str],
) -> None:
    old_s = "" if old_value is None else str(old_value)
    new_s = "" if new_value is None else str(new_value)
    if old_s == new_s:
        return
    insert_table(
        TABLE_HISTORY,
        {
            "task_id": task_id,
            "field_name": field_name,
            "old_value": old_s,
            "new_value": new_s,
            "changed_by_email": changed_by_email,
            "changed_by_id": changed_by_id,
        },
    )


def list_history(task_id: str) -> List[Dict[str, Any]]:
    rows = execute_query(
        f"SELECT * FROM {TABLE_HISTORY} WHERE task_id = %s ORDER BY created_at DESC, id DESC",
        (task_id,),
        fetch_all=True,
    ) or []
    return [_serialize(r) for r in rows]


def list_comments(task_id: str) -> List[Dict[str, Any]]:
    rows = execute_query(
        f"SELECT * FROM {TABLE_COMMENTS} WHERE task_id = %s ORDER BY created_at ASC, id ASC",
        (task_id,),
        fetch_all=True,
    ) or []
    return [_serialize(r) for r in rows]


def insert_comment(
    task_id: str,
    comment: str,
    *,
    author_email: Optional[str],
    author_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    row = insert_table(
        TABLE_COMMENTS,
        {
            "task_id": task_id,
            "comment": comment,
            "author_email": author_email,
            "author_id": author_id,
        },
    )
    update_table(
        TABLE_TASKS,
        {"last_activity_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)},
        filters={"id": task_id},
    )
    return _serialize(row)


def replace_watchers(
    task_id: str,
    emails: List[str],
    *,
    resolved_user_ids: Optional[Dict[str, Optional[str]]] = None,
) -> None:
    execute_query(f"DELETE FROM {TABLE_WATCHERS} WHERE task_id = %s", (task_id,), fetch_all=False)
    normalized_watchers = []
    seen = set()
    for raw in emails:
        em = _normalize_email(raw)
        if em and em not in seen:
            seen.add(em)
            normalized_watchers.append(em)

    watcher_ids = dict(resolved_user_ids or {})
    missing = [email for email in normalized_watchers if email not in watcher_ids]
    if missing:
        watcher_ids.update(resolve_owner_uuids(missing))

    for em in normalized_watchers:
            insert_table(
                TABLE_WATCHERS,
                {"task_id": task_id, "user_email": em, "user_id": watcher_ids.get(em)},
            )


def list_reference_statuses() -> List[Dict[str, Any]]:
    rows = execute_query(
        f"SELECT id, code, label, color, is_terminal, sort_order FROM {TABLE_STATUSES} WHERE is_active = TRUE ORDER BY sort_order",
        fetch_all=True,
    ) or []
    return [_serialize(r) for r in rows]


def list_reference_priorities() -> List[Dict[str, Any]]:
    rows = execute_query(
        f"SELECT id, code, label, sort_order FROM {TABLE_PRIORITIES} ORDER BY sort_order",
        fetch_all=True,
    ) or []
    return [_serialize(r) for r in rows]


def list_reference_categories(tenant_id: str) -> List[Dict[str, Any]]:
    return [{"code": c, "label": c} for c in TICKET_CATEGORIES]


def dashboard_summary(tenant_id: str) -> Dict[str, Any]:
    row = execute_query(
        f"""
        SELECT
            COUNT(*) AS total_count,
            COUNT(*) FILTER (WHERE status = 'OPEN') AS open_count,
            COUNT(*) FILTER (WHERE status = 'IN_PROGRESS') AS in_progress_count,
            COUNT(*) FILTER (WHERE status = 'DONE') AS resolved_count,
            COUNT(*) FILTER (WHERE status = 'CANCELLED') AS closed_count,
            COUNT(*) FILTER (WHERE due_date < CURRENT_DATE AND status NOT IN ('DONE', 'CANCELLED')) AS overdue_count,
            COUNT(*) FILTER (WHERE (is_blocked OR status = 'BLOCKED') AND status NOT IN ('DONE', 'CANCELLED')) AS blocked_count,
            COUNT(*) FILTER (
                WHERE status NOT IN ('DONE', 'CANCELLED')
                  AND last_activity_at < NOW() - INTERVAL '{STALE_DAYS} days'
            ) AS stale_count,
            COUNT(*) FILTER (WHERE status = 'DONE' AND completed_at >= NOW() - INTERVAL '7 days') AS closed_last_7d
        FROM {TABLE_TASKS}
        WHERE tenant_id = %s AND is_deleted = FALSE
        """,
        (tenant_id,),
        fetch_one=True,
    )
    return dict(row) if row else {}


def dashboard_overdue(tenant_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    rows = execute_query(
        f"""
        {_base_select()}
        WHERE t.tenant_id = %s AND {_not_deleted()}
          AND t.due_date < CURRENT_DATE AND t.status NOT IN ('DONE', 'CANCELLED')
        ORDER BY t.due_date ASC NULLS LAST
        LIMIT %s
        """,
        (tenant_id, limit),
        fetch_all=True,
    ) or []
    return [_serialize(r) for r in rows]


def dashboard_stale(tenant_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    rows = execute_query(
        f"""
        {_base_select()}
        WHERE t.tenant_id = %s AND {_not_deleted()}
          AND t.status NOT IN ('DONE', 'CANCELLED')
          AND t.last_activity_at < NOW() - INTERVAL '{STALE_DAYS} days'
        ORDER BY t.last_activity_at ASC NULLS FIRST
        LIMIT %s
        """,
        (tenant_id, limit),
        fetch_all=True,
    ) or []
    return [_serialize(r) for r in rows]


def dashboard_by_owner(tenant_id: str) -> List[Dict[str, Any]]:
    rows = execute_query(
        f"""
        SELECT COALESCE(NULLIF(TRIM(owner_email), ''), 'Unassigned') AS owner_email,
               COUNT(*) AS total_count,
               COUNT(*) FILTER (WHERE status = 'OPEN') AS open_status_count,
               COUNT(*) FILTER (WHERE status = 'IN_PROGRESS') AS in_progress_count,
               COUNT(*) FILTER (WHERE status NOT IN ('DONE', 'CANCELLED')) AS open_count,
               COUNT(*) FILTER (
                   WHERE due_date < CURRENT_DATE AND status NOT IN ('DONE', 'CANCELLED')
               ) AS overdue_count
        FROM {TABLE_TASKS}
        WHERE tenant_id = %s AND is_deleted = FALSE
        GROUP BY 1
        ORDER BY open_count DESC
        LIMIT 50
        """,
        (tenant_id,),
        fetch_all=True,
    ) or []
    return [dict(r) for r in rows]


def dashboard_by_category(tenant_id: str) -> List[Dict[str, Any]]:
    rows = execute_query(
        f"""
        SELECT COALESCE(NULLIF(TRIM(category), ''), 'Unknown') AS category,
               COUNT(*) AS count
        FROM {TABLE_TASKS}
        WHERE tenant_id = %s AND is_deleted = FALSE
        GROUP BY 1
        ORDER BY count DESC, category ASC
        """,
        (tenant_id,),
        fetch_all=True,
    ) or []
    return [dict(r) for r in rows]


def dashboard_recent_activity(tenant_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    rows = execute_query(
        f"""
        SELECT
            h.id,
            h.task_id,
            h.field_name,
            h.old_value,
            h.new_value,
            h.changed_by_email,
            h.changed_by_id,
            h.created_at,
            t.title AS task_title
        FROM {TABLE_HISTORY} h
        INNER JOIN {TABLE_TASKS} t ON t.id = h.task_id
        WHERE t.tenant_id = %s AND t.is_deleted = FALSE
        ORDER BY h.created_at DESC, h.id DESC
        LIMIT %s
        """,
        (tenant_id, limit),
        fetch_all=True,
    ) or []
    return [_serialize(r) for r in rows]

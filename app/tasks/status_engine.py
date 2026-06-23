"""Status transition engine — task_status_transitions + task_statuses (no hardcoded graph)."""

from typing import Any, Dict, List, Set

from fastapi import HTTPException

from services.db_service import execute_query
from services.rbac_service import check_permission, get_user_roles, is_global_superadmin

from app.tasks.constants import (
    MODULE_NAME,
    STATUS_API_TO_DB,
    STATUS_DB_TO_API,
    TABLE_STATUSES,
    TABLE_TRANSITIONS,
)


def _role_ids_for_user(user_id: str, tenant_id: str) -> List[str]:
    roles = get_user_roles(user_id, tenant_id) or []
    return [str(r.get("role_id") or r.get("id")) for r in roles if r.get("role_id") or r.get("id")]


def _status_id_for_code(code: str) -> str:
    db_code = STATUS_API_TO_DB.get((code or "").upper(), (code or "open").lower())
    row = execute_query(
        f"SELECT id FROM {TABLE_STATUSES} WHERE code = %s AND is_active = TRUE LIMIT 1",
        (db_code,),
        fetch_one=True,
    )
    if not row:
        raise HTTPException(status_code=400, detail=f"Unknown status: {code}")
    return str(row["id"])


def fetch_allowed_transitions(
    from_status_api: str,
    tenant_id: str,
    role_ids: List[str],
) -> List[Dict[str, Any]]:
    from_id = _status_id_for_code(from_status_api)
    if not role_ids:
        return []

    placeholders = ", ".join(["%s"] * len(role_ids))
    params: List[Any] = [from_id, tenant_id] + role_ids

    rows = execute_query(
        f"""
        SELECT DISTINCT ON (tst.to_status_id)
            tst.id,
            fs.code AS from_code,
            ts.code AS to_code,
            tst.role_id
        FROM {TABLE_TRANSITIONS} tst
        JOIN {TABLE_STATUSES} fs ON fs.id = tst.from_status_id
        JOIN {TABLE_STATUSES} ts ON ts.id = tst.to_status_id
        WHERE tst.from_status_id = %s
          AND (tst.tenant_id IS NULL OR tst.tenant_id = %s)
          AND tst.role_id IN ({placeholders})
        ORDER BY tst.to_status_id
        """,
        tuple(params),
        fetch_all=True,
    ) or []
    return rows


def get_allowed_target_statuses(
    from_status: str,
    tenant_id: str,
    user_id: str,
) -> List[str]:
    if is_global_superadmin(user_id):
        from_id = _status_id_for_code(from_status)
        rows = execute_query(
            f"""
            SELECT ts.code
            FROM {TABLE_TRANSITIONS} tst
            JOIN {TABLE_STATUSES} ts ON ts.id = tst.to_status_id
            WHERE tst.from_status_id = %s
            ORDER BY ts.sort_order
            """,
            (from_id,),
            fetch_all=True,
        ) or []
        if rows:
            return [STATUS_DB_TO_API.get(r["code"], r["code"].upper()) for r in rows]

    role_ids = _role_ids_for_user(user_id, tenant_id)
    rows = fetch_allowed_transitions(from_status, tenant_id, role_ids)
    return [STATUS_DB_TO_API.get(r["to_code"], r["to_code"].upper()) for r in rows]


def validate_status_transition(
    from_status: str,
    to_status: str,
    user_id: str,
    tenant_id: str,
) -> None:
    from_api = (from_status or "OPEN").upper()
    to_api = (to_status or "").upper()
    if from_api == to_api:
        return

    if is_global_superadmin(user_id):
        from_id = _status_id_for_code(from_api)
        to_id = _status_id_for_code(to_api)
        row = execute_query(
            f"""
            SELECT 1 FROM {TABLE_TRANSITIONS}
            WHERE from_status_id = %s AND to_status_id = %s
            LIMIT 1
            """,
            (from_id, to_id),
            fetch_one=True,
        )
        if not row:
            raise HTTPException(
                status_code=400,
                detail=f"Transition {from_api} → {to_api} is not configured",
            )
        return

    role_ids = _role_ids_for_user(user_id, tenant_id)
    allowed = fetch_allowed_transitions(from_api, tenant_id, role_ids)
    allowed_targets: Set[str] = {
        STATUS_DB_TO_API.get(r["to_code"], r["to_code"].upper()) for r in allowed
    }
    if to_api not in allowed_targets:
        raise HTTPException(
            status_code=403,
            detail=f"Status transition {from_api} → {to_api} is not allowed for your role",
        )
    if not check_permission(user_id, tenant_id, MODULE_NAME, "update"):
        if not check_permission(user_id, tenant_id, "tasks", "update"):
            raise HTTPException(status_code=403, detail="Missing update permission")

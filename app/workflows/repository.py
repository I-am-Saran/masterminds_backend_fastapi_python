"""Workflow data access."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from services.db_service import execute_query, insert_table, update_table, local_db as db

DEFAULT_TENANT = "00000000-0000-0000-0000-000000000001"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_workflows(tenant_id: str) -> List[Dict[str, Any]]:
    rows = execute_query(
        """
        SELECT wm.*,
               COALESCE(u.full_name, u.email, '') AS created_by_name,
               COALESCE(wm.workflow_status,
                        CASE WHEN wm.is_active THEN 'ACTIVE' ELSE 'INACTIVE' END) AS workflow_status,
               (SELECT COUNT(*)::int FROM workflow_levels wl WHERE wl.workflow_id = wm.id) AS total_levels,
               (SELECT string_agg(DISTINCT m.ticket_category, ', ')
                FROM workflow_category_mappings m WHERE m.workflow_id = wm.id) AS mapped_categories
        FROM workflow_master wm
        LEFT JOIN users u ON u.id = wm.created_by
        WHERE wm.tenant_id = %s
        ORDER BY wm.updated_at DESC NULLS LAST, wm.created_at DESC
        """,
        (tenant_id,),
        fetch_all=True,
    )
    return rows or []


def get_workflow(workflow_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    rows = execute_query(
        """
        SELECT wm.*,
               COALESCE(u.full_name, u.email, '') AS created_by_name,
               COALESCE(wm.workflow_status,
                        CASE WHEN wm.is_active THEN 'ACTIVE' ELSE 'INACTIVE' END) AS workflow_status,
               (SELECT string_agg(m.ticket_category, ', ' ORDER BY m.ticket_category)
                FROM workflow_category_mappings m WHERE m.workflow_id = wm.id) AS mapped_categories
        FROM workflow_master wm
        LEFT JOIN users u ON u.id = wm.created_by
        WHERE wm.id = %s AND wm.tenant_id = %s
        """,
        (workflow_id, tenant_id),
        fetch_all=True,
    )
    return rows[0] if rows else None


def get_levels(workflow_id: str) -> List[Dict[str, Any]]:
    rows = execute_query(
        """
        SELECT wl.*
        FROM workflow_levels wl
        WHERE wl.workflow_id = %s
        ORDER BY wl.level_sequence ASC
        """,
        (workflow_id,),
        fetch_all=True,
    )
    return rows or []


def get_active_workflow_by_category(tenant_id: str, category: str) -> Optional[Dict[str, Any]]:
    cat = category.strip()
    rows = execute_query(
        """
        SELECT wm.*
        FROM workflow_category_mappings m
        JOIN workflow_master wm ON wm.id = m.workflow_id
        WHERE m.tenant_id = %s
          AND LOWER(m.ticket_category) = LOWER(%s)
          AND COALESCE(wm.workflow_status, CASE WHEN wm.is_active THEN 'ACTIVE' ELSE 'INACTIVE' END) = 'ACTIVE'
        ORDER BY wm.version DESC, wm.updated_at DESC
        LIMIT 1
        """,
        (tenant_id, cat),
        fetch_all=True,
    )
    if rows:
        return rows[0]
    rows = execute_query(
        """
        SELECT *
        FROM workflow_master
        WHERE tenant_id = %s
          AND ticket_category IS NOT NULL
          AND LOWER(ticket_category) = LOWER(%s)
          AND COALESCE(workflow_status, CASE WHEN is_active THEN 'ACTIVE' ELSE 'INACTIVE' END) = 'ACTIVE'
        ORDER BY version DESC, updated_at DESC
        LIMIT 1
        """,
        (tenant_id, cat),
        fetch_all=True,
    )
    return rows[0] if rows else None


def list_active_mapped_categories(tenant_id: str) -> List[str]:
    """Distinct ticket categories that have an ACTIVE workflow mapping (ticket creators)."""
    rows = execute_query(
        """
        SELECT DISTINCT m.ticket_category
        FROM workflow_category_mappings m
        JOIN workflow_master wm ON wm.id = m.workflow_id
        WHERE m.tenant_id = %s
          AND COALESCE(wm.workflow_status,
                       CASE WHEN wm.is_active THEN 'ACTIVE' ELSE 'INACTIVE' END) = 'ACTIVE'
        ORDER BY m.ticket_category ASC
        """,
        (tenant_id,),
        fetch_all=True,
    )
    return [str(r["ticket_category"]).strip() for r in (rows or []) if r.get("ticket_category")]


def list_category_mappings(tenant_id: str) -> List[Dict[str, Any]]:
    rows = execute_query(
        """
        SELECT m.*, wm.workflow_name,
               COALESCE(wm.workflow_status,
                        CASE WHEN wm.is_active THEN 'ACTIVE' ELSE 'INACTIVE' END) AS workflow_status
        FROM workflow_category_mappings m
        JOIN workflow_master wm ON wm.id = m.workflow_id
        WHERE m.tenant_id = %s
        ORDER BY m.ticket_category ASC
        """,
        (tenant_id,),
        fetch_all=True,
    )
    return rows or []


def upsert_category_mapping(tenant_id: str, ticket_category: str, workflow_id: str) -> Optional[Dict[str, Any]]:
    existing = execute_query(
        """
        SELECT id FROM workflow_category_mappings
        WHERE tenant_id = %s AND LOWER(ticket_category) = LOWER(%s)
        """,
        (tenant_id, ticket_category.strip()),
        fetch_all=True,
    )
    if existing:
        return update_table(
            "workflow_category_mappings",
            {"workflow_id": workflow_id},
            {"id": existing[0]["id"]},
        )
    return insert_table(
        "workflow_category_mappings",
        {
            "tenant_id": tenant_id,
            "ticket_category": ticket_category.strip(),
            "workflow_id": workflow_id,
        },
    )


def delete_category_mapping(mapping_id: str, tenant_id: str) -> None:
    execute_query(
        "DELETE FROM workflow_category_mappings WHERE id = %s AND tenant_id = %s",
        (mapping_id, tenant_id),
    )


def insert_workflow(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return insert_table("workflow_master", data)


def update_workflow(workflow_id: str, tenant_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    data["updated_at"] = _now()
    return update_table("workflow_master", data, {"id": workflow_id, "tenant_id": tenant_id})


def delete_workflow(workflow_id: str, tenant_id: str) -> bool:
    execute_query(
        "DELETE FROM workflow_master WHERE id = %s AND tenant_id = %s",
        (workflow_id, tenant_id),
    )
    return True


def replace_levels(workflow_id: str, levels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # History and active instances reference workflow_levels without ON DELETE CASCADE.
    execute_query(
        """
        UPDATE workflow_ticket_history h
        SET level_id = NULL
        WHERE h.level_id IN (
            SELECT id FROM workflow_levels WHERE workflow_id = %s
        )
        """,
        (workflow_id,),
    )
    execute_query(
        """
        UPDATE workflow_ticket_instances wi
        SET current_level_id = NULL
        WHERE wi.workflow_id = %s
          AND wi.current_level_id IN (
            SELECT id FROM workflow_levels WHERE workflow_id = %s
          )
        """,
        (workflow_id, workflow_id),
    )
    execute_query("DELETE FROM workflow_levels WHERE workflow_id = %s", (workflow_id,))
    saved: List[Dict[str, Any]] = []
    for level in levels:
        row = insert_table(
            "workflow_levels",
            {"workflow_id": workflow_id, **level},
        )
        if row:
            _sync_level_assignment(row)
            saved.append(row)
    return saved


def _sync_level_assignment(level: Dict[str, Any]) -> None:
    level_id = level.get("id")
    if not level_id:
        return
    execute_query("DELETE FROM workflow_level_assignments WHERE workflow_level_id = %s", (level_id,))
    atype = (level.get("assignment_type") or "").upper()
    val = level.get("assignment_value")
    if not val:
        return
    payload: Dict[str, Any] = {
        "workflow_level_id": level_id,
        "assignment_type": atype,
        "team_id": val if atype == "TEAM" else None,
        "role_id": val if atype == "ROLE" else None,
        "user_id": val if atype == "USER" else None,
    }
    insert_table("workflow_level_assignments", payload)


def resolve_assignment_label(assignment_type: str, assignment_value: Optional[str]) -> str:
    if not assignment_value:
        return "—"
    atype = (assignment_type or "").upper()
    if atype == "TEAM":
        r = execute_query("SELECT name FROM teams WHERE id = %s", (assignment_value,), fetch_all=True)
        return r[0]["name"] if r else assignment_value
    if atype == "ROLE":
        r = execute_query("SELECT role_name FROM roles WHERE id = %s", (assignment_value,), fetch_all=True)
        return r[0]["role_name"] if r else assignment_value
    if atype == "USER":
        r = execute_query(
            "SELECT COALESCE(full_name, email) AS label FROM users WHERE id = %s",
            (assignment_value,),
            fetch_all=True,
        )
        return r[0]["label"] if r else assignment_value
    return assignment_value


def get_instance_by_ticket(ticket_id: str) -> Optional[Dict[str, Any]]:
    rows = execute_query(
        """
        SELECT wi.*, wm.workflow_name, wm.ticket_category
        FROM workflow_ticket_instances wi
        JOIN workflow_master wm ON wm.id = wi.workflow_id
        WHERE wi.ticket_id = %s
        """,
        (ticket_id,),
        fetch_all=True,
    )
    return rows[0] if rows else None


def insert_instance(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return insert_table("workflow_ticket_instances", data)


def update_instance(instance_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return update_table("workflow_ticket_instances", data, {"id": instance_id})


def insert_history(data: Dict[str, Any], *, normalize_performed_by: bool = True) -> Optional[Dict[str, Any]]:
    payload = dict(data)
    # performed_by FK references users.id (TEXT), not users.uuid_id
    if normalize_performed_by and payload.get("performed_by") is not None:
        pb = str(payload["performed_by"])
        row = execute_query(
            "SELECT id FROM users WHERE id = %s OR uuid_id::text = %s LIMIT 1",
            (pb, pb),
            fetch_one=True,
        )
        payload["performed_by"] = row["id"] if row else None
    return insert_table("workflow_ticket_history", payload)


def get_history(instance_id: str) -> List[Dict[str, Any]]:
    rows = execute_query(
        """
        SELECT h.*, COALESCE(u.full_name, u.email) AS performer_name
        FROM workflow_ticket_history h
        LEFT JOIN users u ON u.id = h.performed_by
        WHERE h.workflow_instance_id = %s
        ORDER BY h.performed_at ASC
        """,
        (instance_id,),
        fetch_all=True,
    )
    return rows or []


def get_level_by_id(level_id: str) -> Optional[Dict[str, Any]]:
    rows = execute_query("SELECT * FROM workflow_levels WHERE id = %s", (level_id,), fetch_all=True)
    return rows[0] if rows else None


def get_first_level(workflow_id: str) -> Optional[Dict[str, Any]]:
    rows = execute_query(
        """
        SELECT * FROM workflow_levels
        WHERE workflow_id = %s
        ORDER BY level_sequence ASC
        LIMIT 1
        """,
        (workflow_id,),
        fetch_all=True,
    )
    return rows[0] if rows else None


def get_next_level(workflow_id: str, current_sequence: int) -> Optional[Dict[str, Any]]:
    rows = execute_query(
        """
        SELECT * FROM workflow_levels
        WHERE workflow_id = %s AND level_sequence > %s
        ORDER BY level_sequence ASC
        LIMIT 1
        """,
        (workflow_id, current_sequence),
        fetch_all=True,
    )
    return rows[0] if rows else None


def resolve_owner_email(assignment_type: str, assignment_value: Optional[str], tenant_id: str) -> Optional[str]:
    if not assignment_value:
        return None
    atype = (assignment_type or "").upper()
    if atype == "USER":
        rows = execute_query(
            "SELECT email FROM users WHERE id = %s",
            (assignment_value,),
            fetch_all=True,
        )
        return rows[0]["email"] if rows else None
    if atype == "ROLE":
        rows = execute_query(
            """
            SELECT u.email
            FROM user_roles ur
            JOIN users u ON u.id = ur.user_id
            WHERE ur.role_id = %s AND ur.tenant_id = %s
            LIMIT 1
            """,
            (assignment_value, tenant_id),
            fetch_all=True,
        )
        return rows[0]["email"] if rows else None
    if atype == "TEAM":
        rows = execute_query(
            """
            SELECT u.email
            FROM team_users tu
            JOIN users u ON tu.user_id = u.id OR tu.user_id = u.email
            WHERE tu.team_id = %s AND tu.tenant_id = %s
            LIMIT 1
            """,
            (assignment_value, tenant_id),
            fetch_all=True,
        )
        return rows[0]["email"] if rows else None
    return None


def user_can_act_on_level(
    user_email: Optional[str],
    user_id: Optional[str],
    tenant_id: str,
    level: Dict[str, Any],
) -> bool:
    """True when the user matches the level assignment (USER, ROLE, or TEAM member)."""
    if not level:
        return False
    atype = (level.get("assignment_type") or "").upper()
    val = level.get("assignment_value")
    if not val:
        return False

    email = (user_email or "").strip().lower()
    uid = str(user_id) if user_id else ""

    if atype == "USER":
        row = execute_query(
            """
            SELECT id, email FROM users
            WHERE id = %s OR uuid_id::text = %s OR LOWER(TRIM(email)) = LOWER(TRIM(%s))
            LIMIT 1
            """,
            (val, val, val),
            fetch_one=True,
        )
        if not row:
            return False
        return uid == str(row["id"]) or email == (row.get("email") or "").strip().lower()

    if atype == "ROLE":
        row = execute_query(
            """
            SELECT 1 FROM user_roles ur
            JOIN users u ON u.id = ur.user_id
            WHERE ur.role_id = %s AND ur.tenant_id = %s
              AND (u.id = %s OR LOWER(TRIM(u.email)) = LOWER(%s))
            LIMIT 1
            """,
            (val, tenant_id, uid, email),
            fetch_one=True,
        )
        return bool(row)

    if atype == "TEAM":
        row = execute_query(
            """
            SELECT 1 FROM team_users tu
            WHERE tu.team_id = %s AND tu.tenant_id = %s
              AND (
                LOWER(btrim(tu.user_id)) = LOWER(btrim(%s))
                OR LOWER(btrim(tu.user_id)) = LOWER(btrim(%s))
              )
            LIMIT 1
            """,
            (val, tenant_id, uid, email),
            fetch_one=True,
        )
        return bool(row)

    return False


def resolve_owner_display(
    assignment_type: str,
    assignment_value: Optional[str],
    tenant_id: str,
) -> Dict[str, Optional[str]]:
    """Human-readable owner label and primary contact email for a workflow level."""
    label = resolve_assignment_label(assignment_type, assignment_value)
    email = resolve_owner_email(assignment_type, assignment_value, tenant_id)
    atype = (assignment_type or "").upper()
    if atype == "USER" and assignment_value:
        row = execute_query(
            """
            SELECT COALESCE(full_name, email) AS name, email FROM users
            WHERE id = %s OR uuid_id::text = %s LIMIT 1
            """,
            (assignment_value, assignment_value),
            fetch_one=True,
        )
        if row:
            return {"label": row.get("name") or label, "email": row.get("email") or email}
    if atype in ("TEAM", "ROLE") and label:
        return {"label": f"{atype.title()} → {label}", "email": email}
    return {"label": label or email, "email": email}

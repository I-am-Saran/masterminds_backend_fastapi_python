"""Table/column definitions for kaizen_tasks (psycopg2 layer — no ORM)."""

from app.tasks.constants import (
    TABLE_COMMENTS,
    TABLE_HISTORY,
    TABLE_TASKS,
    TABLE_TRANSITIONS,
    TABLE_WATCHERS,
)

__all__ = [
    "TABLE_TASKS",
    "TABLE_COMMENTS",
    "TABLE_HISTORY",
    "TABLE_WATCHERS",
    "TABLE_TRANSITIONS",
    "KAIZEN_TASK_COLUMNS",
]

KAIZEN_TASK_COLUMNS = (
    "id",
    "tenant_id",
    "title",
    "description",
    "owner_email",
    "owner_id",
    "status",
    "priority",
    "due_date",
    "category",
    "meeting_id",
    "source_type",
    "is_blocked",
    "blocked_reason",
    "legacy_mom_action_id",
    "last_activity_at",
    "created_by",
    "created_at",
    "updated_at",
    "completed_at",
    "work_started_at",
    "is_deleted",
)

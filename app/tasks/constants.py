"""Kaizen operational tasks — constants (kaizen_db_schema 2026-05-23)."""

TABLE_TASKS = "kaizen_tasks"
TABLE_COMMENTS = "kaizen_task_comments"
TABLE_HISTORY = "kaizen_task_history"
TABLE_WATCHERS = "kaizen_task_watchers"
TABLE_STATUSES = "task_statuses"
TABLE_PRIORITIES = "task_priorities"
TABLE_CATEGORIES = "task_categories"
TABLE_TRANSITIONS = "task_status_transitions"

DEFAULT_TENANT = "00000000-0000-0000-0000-000000000001"
MODULE_NAME = "kaizen_tasks"

STATUSES = frozenset({"OPEN", "IN_PROGRESS", "BLOCKED", "DONE", "CANCELLED"})
TERMINAL_STATUSES = frozenset({"DONE", "CANCELLED"})
PRIORITIES = frozenset({"P1", "P2", "P3"})
SOURCE_TYPES = frozenset({"manual", "meeting"})

STATUS_API_TO_DB = {
    "OPEN": "open",
    "IN_PROGRESS": "in_progress",
    "BLOCKED": "blocked",
    "DONE": "done",
    "CANCELLED": "cancelled",
}

STATUS_DB_TO_API = {v: k for k, v in STATUS_API_TO_DB.items()}

PRIORITY_API_TO_DB = {
    "P1": "critical",
    "P2": "high",
    "P3": "medium",
}

PRIORITY_DB_TO_API = {
    "critical": "P1",
    "high": "P2",
    "medium": "P3",
}

SORT_FIELDS = {
    "title",
    "status",
    "priority",
    "due_date",
    "updated_at",
    "created_at",
    "last_activity_at",
    "owner_email",
}

STALE_DAYS = 7

# Kaizen ticket categories — alphabetically sorted; keep in sync with frontend workflowConstants.js
TICKET_CATEGORIES: tuple[str, ...] = (
    "Application",
    "Automation",
    "CKPL Functional Agent",
    "CKPL Generic Agent",
    "Data",
    "External",
    "Functional Agent",
    "HEPL Functional Agent",
    "HEPL Generic Agent",
    "Immersive Technology",
    "IOT - Hardware",
    "Mobile Application",
    "One MIS",
    "POC - Research",
    "Process Re-engineering",
    "SAP",
    "Technology",
    "Vending Machine",
    "Web Portal/Automation",
    "Website",
)

TICKET_CATEGORIES_SET = frozenset(TICKET_CATEGORIES)

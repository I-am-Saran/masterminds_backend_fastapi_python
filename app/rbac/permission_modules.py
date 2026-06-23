"""Curated RBAC modules for the Masterminds application."""

from __future__ import annotations

from typing import Any, Dict, List, Set

from services.rbac_service import REGISTERED_PERMISSIONS

# Legacy modules from the previous QA/compliance platform — not used in Masterminds UI.
LEGACY_PERMISSION_MODULES: Set[str] = {
    "actions",
    "audits",
    "bugs",
    "builds",
    "build_reports",
    "build_tasks",
    "certifications",
    "convex_dashboard",
    "cybersecurity_reports",
    "dashboard",
    "functional_test_reports",
    "home",
    "incident_registers",
    "management_review_meetings",
    "masters",
    "mom",
    "organizations",
    "projects",
    "qa_dashboard",
    "risk_register",
    "security_controls",
    "tasks",
    "testcases",
}

ACTION_TO_COLUMN = {
    "create": "can_create",
    "retrieve": "can_retrieve",
    "update": "can_update",
    "delete": "can_delete",
    "comment": "can_comment",
    "create_task": "can_create_task",
}

# Active Masterminds modules shown on Roles → Permissions.
PERMISSION_MODULE_REGISTRY: List[Dict[str, Any]] = [
    {
        "module_name": "kaizen_tasks",
        "display_name": "Tickets",
        "description": "Kaizen tickets, comments, and ticket dashboard",
        "sort_order": 10,
        "actions": ["create", "retrieve", "update", "delete", "comment"],
    },
    {
        "module_name": "teams",
        "display_name": "Teams",
        "description": "Team management and membership",
        "sort_order": 20,
        "actions": ["create", "retrieve", "update", "delete"],
    },
    {
        "module_name": "users",
        "display_name": "Users",
        "description": "User accounts and profiles",
        "sort_order": 30,
        "actions": ["create", "retrieve", "update", "delete"],
    },
    {
        "module_name": "roles",
        "display_name": "Roles",
        "description": "Role definitions and permission assignment",
        "sort_order": 40,
        "actions": ["create", "retrieve", "update"],
    },
    {
        "module_name": "workflows",
        "display_name": "Workflow Definitions",
        "description": "Workflow templates, mappings, and activation",
        "sort_order": 50,
        "actions": ["create", "retrieve", "update", "delete"],
    },
    {
        "module_name": "email",
        "display_name": "Email Notifications",
        "description": "SMTP configuration, notification toggles, and templates",
        "sort_order": 60,
        "actions": ["create", "retrieve", "update", "delete"],
    },
]

ACTIVE_PERMISSION_MODULES: Set[str] = {
    entry["module_name"] for entry in PERMISSION_MODULE_REGISTRY
}


def register_app_permission_modules() -> None:
    """Ensure active modules are present in the decorator registry."""
    for entry in PERMISSION_MODULE_REGISTRY:
        module_name = entry["module_name"]
        for action in entry.get("actions", []):
            REGISTERED_PERMISSIONS.add((module_name, action))


def get_permission_module_catalog() -> List[Dict[str, Any]]:
    register_app_permission_modules()
    return sorted(
        PERMISSION_MODULE_REGISTRY,
        key=lambda item: (item.get("sort_order", 999), item.get("display_name", "")),
    )


def get_all_matrix_actions() -> List[str]:
    actions: List[str] = []
    seen: Set[str] = set()
    for entry in PERMISSION_MODULE_REGISTRY:
        for action in entry.get("actions", []):
            if action not in seen:
                seen.add(action)
                actions.append(action)
    return actions


def normalize_module_permissions(
    module_name: str,
    permissions: Dict[str, Any] | None,
) -> Dict[str, bool]:
    """Map UI/API permission flags to DB columns for a single module."""
    entry = next(
        (item for item in PERMISSION_MODULE_REGISTRY if item["module_name"] == module_name),
        None,
    )
    allowed_actions = set(entry.get("actions", [])) if entry else set()
    source = permissions or {}
    normalized: Dict[str, bool] = {
        column: False
        for column in ACTION_TO_COLUMN.values()
    }
    for action, column in ACTION_TO_COLUMN.items():
        if action in allowed_actions:
            normalized[column] = bool(source.get(column, False))
    return normalized

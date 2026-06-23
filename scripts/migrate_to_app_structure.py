#!/usr/bin/env python3
"""One-time migration: move routers into app/ domain modules with legacy shims."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REFERENCE_MARKER = "# REFERENCE_ONLY_MODULE — legacy Kaizen module; preserved for compatibility.\n"

# source filename in routers/ -> (package path under app/, shim module name, is_reference)
ROUTER_MAP: dict[str, tuple[str, str, bool]] = {
    "tasks.py": ("app/tasks", "tasks", False),
    "mom.py": ("app/meetings", "mom", False),
    "management_review_meeting.py": ("app/meetings", "management_review_meeting", False),
    "dashboard.py": ("app/dashboards", "dashboard", False),
    "efforttracker_dashboard.py": ("app/dashboards", "efforttracker_dashboard", False),
    "roles.py": ("app/roles", "roles", False),
    "users.py": ("app/users", "users", False),
    "organizations.py": ("app/tenants", "organizations", False),
    "teams.py": ("app/admin", "teams", False),
    "controls.py": ("app/audit", "controls", False),
    "audits.py": ("app/audit", "audits", False),
    "projects.py": ("app/admin", "projects", False),
    "build_tracker.py": ("app/admin", "build_tracker", False),
    "testcase_router.py": ("app/admin", "testcase_router", False),
    "qa_dashboard.py": ("app/reference_architecture/qa_dashboard", "qa_dashboard", True),
    "convex_dashboard.py": ("app/reference_architecture/convex_dashboard", "convex_dashboard", True),
    "incident_register.py": ("app/reference_architecture/incident_register", "incident_register", True),
    "risk_register.py": ("app/reference_architecture/risk_register", "risk_register", True),
    "certifications.py": ("app/reference_architecture/certifications", "certifications", True),
    "Bug_main.py": ("app/reference_architecture/bugs", "Bug_main", True),
    "QA_master_main.py": ("app/reference_architecture/qa_master", "QA_master_main", True),
}

SHARED_UTILS = {
    "error_handler.py": "app/shared/error_handler.py",
    "api_wrapper.py": "app/shared/api_wrapper.py",
    "permission_checker.py": "app/shared/permission_checker.py",
    "application_enum.py": "app/shared/application_enum.py",
    "bugs_enum.py": "app/shared/bugs_enum.py",
    "testcase_validator.py": "app/admin/testcase_validator.py",
}


def ensure_init(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    init = path / "__init__.py"
    if not init.exists():
        init.write_text('"""Kaizen app package."""\n', encoding="utf-8")


def router_target_name(src: str, pkg: str) -> str:
    if pkg.endswith("meetings") and src == "management_review_meeting.py":
        return "mrm_router.py"
    if pkg.endswith("dashboards") and src == "efforttracker_dashboard.py":
        return "efforttracker_router.py"
    if pkg.endswith("audit") and src == "controls.py":
        return "controls_router.py"
    if pkg.endswith("admin"):
        base = src.replace(".py", "")
        if base == "testcase_router":
            return "testcase_router.py"
        return f"{base}_router.py"
    return "router.py"


def write_shim(routers_dir: Path, shim_name: str, import_path: str) -> None:
    content = f'''"""Legacy shim — import from {import_path}."""
from {import_path} import *  # noqa: F403
from {import_path} import router  # noqa: F401

__all__ = ["router"]
'''
    (routers_dir / f"{shim_name}.py").write_text(content, encoding="utf-8")


def migrate_routers() -> list[str]:
    moved: list[str] = []
    routers_dir = ROOT / "routers"
    for src_name, (pkg, shim_name, is_ref) in ROUTER_MAP.items():
        src = routers_dir / src_name
        if not src.exists():
            print(f"SKIP missing: {src}")
            continue
        pkg_path = ROOT / pkg
        ensure_init(pkg_path)
        target_name = router_target_name(src_name, pkg)
        dest = pkg_path / target_name
        if dest.exists():
            print(f"SKIP exists: {dest}")
        else:
            shutil.copy2(src, dest)
            text = dest.read_text(encoding="utf-8")
            if is_ref and REFERENCE_MARKER not in text:
                dest.write_text(REFERENCE_MARKER + text, encoding="utf-8")
            moved.append(f"{src_name} -> {dest.relative_to(ROOT)}")
        import_mod = pkg.replace("/", ".") + "." + target_name.replace(".py", "")
        write_shim(routers_dir, shim_name, import_mod)
    return moved


def migrate_shared_utils() -> list[str]:
    moved: list[str] = []
    utils_dir = ROOT / "utils"
    for src_name, dest_rel in SHARED_UTILS.items():
        src = utils_dir / src_name
        dest = ROOT / dest_rel
        ensure_init(dest.parent)
        if not src.exists():
            continue
        if not dest.exists():
            shutil.copy2(src, dest)
            moved.append(f"utils/{src_name} -> {dest_rel}")
        mod = dest_rel.replace("/", ".").replace(".py", "")
        shim = f'"""Legacy shim — use {mod}."""\nfrom {mod} import *  # noqa: F403\n'
        (utils_dir / src_name).write_text(shim, encoding="utf-8")
    # utils __init__ may import application_enum
    init = utils_dir / "__init__.py"
    if init.exists():
        init.write_text(
            '"""Legacy utils package — prefer app.shared."""\n'
            "from app.shared.application_enum import ApplicationName  # noqa: F401\n",
            encoding="utf-8",
        )
    return moved


def migrate_config() -> None:
    core = ROOT / "app" / "core"
    ensure_init(core)
    src = ROOT / "config.py"
    dest = core / "config.py"
    if dest.exists():
        return
    text = src.read_text(encoding="utf-8")
    text = text.replace(
        "CONFIG_DIR = Path(__file__).parent",
        "CONFIG_DIR = Path(__file__).resolve().parent.parent.parent",
    )
    dest.write_text(text, encoding="utf-8")
    src.write_text(
        '"""Legacy config shim — settings live in app.core.config."""\n'
        "from app.core.config import *  # noqa: F403\n",
        encoding="utf-8",
    )


def create_core_stubs() -> None:
    core = ROOT / "app" / "core"
    stubs = {
        "database.py": '"""DB access — re-exports services.db_service (migration phase)."""\n'
        "from services.db_service import (  # noqa: F401\n"
        "    local_db,\n"
        "    execute_query,\n"
        "    select_table,\n"
        "    insert_table,\n"
        "    update_table,\n"
        "    delete_table,\n"
        "    get_connection,\n"
        ")\n",
        "security.py": '"""Security helpers — re-exports auth_service (migration phase)."""\n'
        "from services.auth_service import (  # noqa: F401\n"
        "    auth_guard,\n"
        "    authenticate_user,\n"
        "    verify_jwt_token,\n"
        "    get_user_from_token,\n"
        "    hash_password,\n"
        "    verify_password,\n"
        "    validate_password_strength,\n"
        ")\n",
        "exceptions.py": '"""Shared exceptions — re-export error helpers."""\n'
        "from app.shared.error_handler import (  # noqa: F401\n"
        "    handle_api_error,\n"
        "    handle_endpoint_error,\n"
        "    log_error,\n"
        "    format_error_response,\n"
        ")\n",
    }
    for name, body in stubs.items():
        p = core / name
        if not p.exists():
            p.write_text(body, encoding="utf-8")


def create_infrastructure_stub() -> None:
    infra = ROOT / "app" / "infrastructure"
    ensure_init(infra)
    email = infra / "email"
    ensure_init(email)
    (email / "__init__.py").write_text(
        '"""Email infrastructure placeholder — SMTP logic remains in main.py during migration."""\n',
        encoding="utf-8",
    )


def create_app_router_registry() -> None:
    reg = ROOT / "app" / "router_registry.py"
    if reg.exists():
        return
    lines = [
        '"""Central router registration for Kaizen (WIMS-style app package)."""',
        "from fastapi import FastAPI",
        "",
        "# Domain routers",
        "from app.tasks.router import router as tasks_router",
        "from app.meetings.router import router as mom_router",
        "from app.meetings.mrm_router import router as mrm_router",
        "from app.dashboards.router import router as dashboard_router",
        "from app.dashboards.efforttracker_router import router as efforttracker_router",
        "from app.roles.router import router as roles_router",
        "from app.users.router import router as users_router",
        "from app.tenants.router import router as organizations_router",
        "from app.admin.teams_router import router as teams_router",
        "from app.audit.controls_router import router as controls_router",
        "from app.audit.router import router as audits_router",
        "from app.admin.projects_router import router as projects_router",
        "from app.admin.build_tracker_router import router as build_tracker_router",
        "from app.admin.testcase_router import router as testcase_router",
        "",
        "# Reference / legacy modules",
        "from app.reference_architecture.qa_dashboard.router import router as qa_dashboard_router",
        "from app.reference_architecture.convex_dashboard.router import router as convex_router",
        "from app.reference_architecture.incident_register.router import router as incident_router",
        "from app.reference_architecture.risk_register.router import router as risk_register_router",
        "from app.reference_architecture.certifications.router import router as certifications_router",
        "from app.reference_architecture.bugs.router import router as bug_router",
        "from app.reference_architecture.qa_master.router import router as qa_master_router",
        "",
        "",
        "def register_routers(app: FastAPI) -> None:",
        '    """Mount all API routers with the same prefixes as legacy main.py."""',
        '    app.include_router(controls_router, prefix="/api")',
        '    app.include_router(tasks_router, prefix="/api")',
        '    app.include_router(audits_router, prefix="/api")',
        '    app.include_router(users_router, prefix="/api")',
        '    app.include_router(roles_router, prefix="/api")',
        '    app.include_router(dashboard_router, prefix="/api")',
        '    app.include_router(qa_dashboard_router, prefix="/api")',
        '    app.include_router(bug_router, prefix="/api")',
        '    app.include_router(qa_master_router, prefix="/api")',
        '    app.include_router(convex_router, prefix="/api")',
        '    app.include_router(projects_router, prefix="/api")',
        '    app.include_router(build_tracker_router, prefix="/api")',
        '    app.include_router(efforttracker_router, prefix="/api")',
        '    app.include_router(organizations_router, prefix="/api")',
        '    app.include_router(risk_register_router, prefix="/api")',
        '    app.include_router(mrm_router, prefix="/api")',
        '    app.include_router(incident_router, prefix="/api")',
        '    app.include_router(mom_router, prefix="/api")',
        '    app.include_router(certifications_router, prefix="/api")',
        '    app.include_router(teams_router, prefix="/api/teams")',
        '    app.include_router(testcase_router, prefix="/api")',
        "",
    ]
    reg.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    ensure_init(ROOT / "app")
    moved_r = migrate_routers()
    moved_u = migrate_shared_utils()
    migrate_config()
    create_core_stubs()
    create_infrastructure_stub()
    create_app_router_registry()
    print("Routers moved:", len(moved_r))
    for m in moved_r:
        print(" ", m)
    print("Utils moved:", len(moved_u))
    for m in moved_u:
        print(" ", m)

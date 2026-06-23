"""Register all API routers — single place to see the API surface."""
from fastapi import FastAPI

from app.compliance_tasks.router import router as compliance_tasks_router
from app.tasks import router as kaizen_tasks_router
from app.meetings.router import router as mom_router
from app.meetings.mrm_router import router as mrm_router
from app.dashboards.router import router as dashboard_router
from app.dashboards.efforttracker_router import router as efforttracker_router
from app.roles.router import router as roles_router
from app.users.router import router as users_router
from app.tenants.router import router as organizations_router
from app.admin.teams_router import router as teams_router
from app.workflows.router import router as workflows_router
# Legacy compliance module — not used by Masterminds UI; table may be absent in dev DB.
# from app.audit.controls_router import router as controls_router
from app.audit.router import router as audits_router
from app.admin.projects_router import router as projects_router
from app.admin.build_tracker_router import router as build_tracker_router
from app.admin.testcase_router import router as testcase_router
from app.email.router import router as email_router

# Legacy modules (stable; prefer tasks/meetings/dashboards for new work)
from app.legacy.qa_dashboard import router as qa_dashboard_router
from app.legacy.convex_dashboard import router as convex_router
from app.legacy.incident_register import router as incident_router
from app.legacy.risk_register import router as risk_register_router
from app.legacy.certifications import router as certifications_router
from app.legacy.bugs import router as bug_router
from app.legacy.qa_master import router as qa_master_router


def register_routers(app: FastAPI) -> None:
    # controls_router omitted — legacy security_controls compliance API (see LEGACY_PERMISSION_MODULES)
    app.include_router(compliance_tasks_router, prefix="/api")
    app.include_router(kaizen_tasks_router, prefix="/api")
    app.include_router(audits_router, prefix="/api")
    app.include_router(users_router, prefix="/api")
    app.include_router(roles_router, prefix="/api")
    app.include_router(dashboard_router, prefix="/api")
    app.include_router(qa_dashboard_router, prefix="/api")
    app.include_router(bug_router, prefix="/api")
    app.include_router(qa_master_router, prefix="/api")
    app.include_router(convex_router, prefix="/api")
    app.include_router(projects_router, prefix="/api")
    app.include_router(build_tracker_router, prefix="/api")
    app.include_router(efforttracker_router, prefix="/api")
    app.include_router(organizations_router, prefix="/api")
    app.include_router(risk_register_router, prefix="/api")
    app.include_router(mrm_router, prefix="/api")
    app.include_router(incident_router, prefix="/api")
    app.include_router(mom_router, prefix="/api")
    app.include_router(certifications_router, prefix="/api")
    app.include_router(teams_router, prefix="/api/teams")
    app.include_router(workflows_router, prefix="/api")
    app.include_router(testcase_router, prefix="/api")
    app.include_router(email_router, prefix="/api")

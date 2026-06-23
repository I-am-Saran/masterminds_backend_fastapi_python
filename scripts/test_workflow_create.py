#!/usr/bin/env python3
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from services.db_service import execute_query
from app.workflows.service import WorkflowService
from app.workflows.schemas import WorkflowCreate, WorkflowLevelCreate

cols = execute_query(
    """
    SELECT column_name, is_nullable
    FROM information_schema.columns
    WHERE table_name = 'workflow_master'
      AND column_name IN ('ticket_category', 'workflow_status')
    ORDER BY column_name
    """
)
print("Columns:", cols)

teams = execute_query("SELECT id FROM teams LIMIT 1")
if not teams:
    print("No teams in DB — skipping create test")
    sys.exit(0)
team_id = str(teams[0]["id"])

payload = WorkflowCreate(
    workflow_name="Test WF",
    description="test",
    workflow_status="DRAFT",
    levels=[
        WorkflowLevelCreate(
            level_sequence=1,
            level_name="Level 1",
            assignment_type="TEAM",
            assignment_value=team_id,
        )
    ],
)
auth = {"tenant_id": "00000000-0000-0000-0000-000000000001", "user_id": None}
r = WorkflowService.create_workflow(payload, auth)
print("Create OK:", r.get("success"), r["data"]["workflow_name"])
execute_query(
    "DELETE FROM workflow_master WHERE workflow_name = %s",
    ("Test WF",),
    fetch_all=False,
)
print("Cleaned up test row")

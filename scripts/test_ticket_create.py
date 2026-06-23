#!/usr/bin/env python3
"""Smoke-test ticket create + workflow auto-start."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.tasks.schemas import TaskCreate
from app.tasks.service import TaskService
from services.db_service import execute_query

# Use a real user text id from DB
user = execute_query("SELECT id, email FROM users WHERE is_active = TRUE LIMIT 1", fetch_one=True)
if not user:
    print("No active user — skip")
    sys.exit(0)

auth = {
    "tenant_id": "00000000-0000-0000-0000-000000000001",
    "user_id": user["id"],
    "email": user["email"],
}

payload = TaskCreate(
    title="Workflow FK smoke test",
    description="auto-delete",
    category="Automation",
    status="OPEN",
    priority="P3",
)

r = TaskService.create_task(payload, auth)
task_id = r["data"]["id"]
print("Create OK:", task_id)

execute_query(
    "DELETE FROM workflow_ticket_history WHERE workflow_instance_id IN (SELECT id FROM workflow_ticket_instances WHERE ticket_id = %s)",
    (task_id,),
    fetch_all=False,
)
execute_query("DELETE FROM workflow_ticket_instances WHERE ticket_id = %s", (task_id,), fetch_all=False)
execute_query("DELETE FROM kaizen_task_history WHERE task_id = %s", (task_id,), fetch_all=False)
execute_query("DELETE FROM kaizen_tasks WHERE id = %s", (task_id,), fetch_all=False)
print("Cleaned up")

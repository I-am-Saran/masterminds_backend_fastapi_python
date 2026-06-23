# Kaizen Tasks Backend — Implementation Summary

Schema: `scripts/db/kaizen_db_schema_2026-05-23_12-20-12.sql`

## Data layer (psycopg2 — matches existing Kaizen/Alchemy stack)

| Table | Usage |
|-------|--------|
| `kaizen_tasks` | Primary operational tasks |
| `kaizen_task_comments` | Comments |
| `kaizen_task_history` | Field-level audit |
| `kaizen_task_watchers` | Watcher emails |
| `task_statuses` | Reference + transition mapping |
| `task_status_transitions` | RBAC-gated status graph |
| `task_priorities` / `task_categories` | Reference lookups |
| `mom_meetings` / `mom_action_items` | Meeting sync via `legacy_mom_action_id` |

## API (`/api/tasks`)

| Method | Path |
|--------|------|
| GET | `/tasks/reference` |
| GET | `/tasks` |
| GET | `/tasks/{id}` |
| POST | `/tasks` |
| PUT | `/tasks/{id}` |
| PATCH | `/tasks/{id}/status` |
| DELETE | `/tasks/{id}` |
| GET/POST | `/tasks/{id}/comments` |
| GET | `/tasks/{id}/history` |
| GET | `/tasks/status-transitions/{id}` |
| GET | `/tasks/dashboard/summary` |
| GET | `/tasks/dashboard/overdue` |
| GET | `/tasks/dashboard/stale` |
| GET | `/tasks/dashboard/by-owner` |

## Permissions

Module: `kaizen_tasks` — `kaizen_tasks_retrieve`, `_create`, `_update`, `_delete`, `_comment`

Seed: `psql -d kaizen_dev -f scripts/sql/kaizen_tasks_seed.sql`

## Meetings

MoM `/mom/action-items` create/update/delete delegates to `TaskService` (source of truth = `kaizen_tasks`).

## Compliance (unchanged)

GRC tasks: `/api/compliance-tasks/*` → `tasks` table (`app/compliance_tasks/`).

## Module layout

```
app/tasks/
├── router.py
├── service.py
├── repository.py
├── status_engine.py
├── meeting_sync.py
├── schemas.py
├── models.py
├── constants.py
├── validators.py
├── permissions.py
└── dependencies.py
```

Frontend (`src/features/tasks/`) — deferred per product plan.

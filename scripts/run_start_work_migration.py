#!/usr/bin/env python3
"""Apply kaizen_tasks_start_work.sql migration."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.db_service import execute_query

SQL = (ROOT / "scripts" / "sql" / "kaizen_tasks_start_work.sql").read_text(encoding="utf-8")

for stmt in SQL.split(";"):
    lines = [ln for ln in stmt.strip().splitlines() if ln.strip() and not ln.strip().startswith("--")]
    s = "\n".join(lines).strip()
    if not s:
        continue
    execute_query(s, fetch_all=False)
    print("OK:", s.split("\n")[0][:70])

print("Migration complete.")

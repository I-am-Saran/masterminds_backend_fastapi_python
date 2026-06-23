"""
Daily QA bug snapshot generation (login-triggered, once per day).

Uses PostgreSQL generate_daily_bug_snapshot() which must read from "bugs"
with quoted columns ("Project", "Status", etc.). See:
scripts/sql/fix_generate_daily_bug_snapshot_production.sql
"""

import asyncio
import logging

from services.db_service import execute_query

logger = logging.getLogger(__name__)


def today_snapshot_row_count() -> int:
    row = execute_query(
        """
        SELECT COUNT(*)::int AS row_count
        FROM qa_bug_snapshot_daily
        WHERE snapshot_date = CURRENT_DATE
        """,
        fetch_one=True,
    )
    return int((row or {}).get("row_count") or 0)


def generate_daily_bug_snapshot() -> None:
    """Invoke DB function; idempotent when today already has rows."""
    execute_query("SELECT generate_daily_bug_snapshot()", fetch_all=False)


def ensure_daily_bug_snapshot() -> None:
    """
    Ensure today's snapshot exists. Errors are logged but do not block login.
    """
    try:
        existing = today_snapshot_row_count()
        if existing > 0:
            logger.debug("[qa_snapshot] today already has %s rows, skipping", existing)
            return

        generate_daily_bug_snapshot()
        created = today_snapshot_row_count()
        if created > 0:
            logger.info("[qa_snapshot] daily bug snapshot created (%s rows)", created)
        else:
            logger.error(
                "[qa_snapshot] snapshot function ran but inserted 0 rows for today. "
                "Production may be using a broken generate_daily_bug_snapshot() "
                "(wrong bugs column names). Run scripts/sql/fix_generate_daily_bug_snapshot_production.sql"
            )
    except Exception as exc:
        logger.error(
            "[qa_snapshot] daily bug snapshot failed after login: %s. "
            "Apply fix_generate_daily_bug_snapshot_production.sql if function references "
            "bugs.project_name / bugs.status.",
            exc,
            exc_info=True,
        )


async def ensure_daily_bug_snapshot_async() -> None:
    """Non-blocking wrapper for async FastAPI handlers (sync DB driver)."""
    await asyncio.to_thread(ensure_daily_bug_snapshot)


def force_regenerate_today_snapshot() -> int:
    """Delete today's rows and regenerate. Returns row count for today."""
    execute_query(
        "DELETE FROM qa_bug_snapshot_daily WHERE snapshot_date = CURRENT_DATE",
        fetch_all=False,
    )
    generate_daily_bug_snapshot()
    return today_snapshot_row_count()

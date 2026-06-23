#!/usr/bin/env python3
"""Upgrade CREATE_TICKET email template to latest HTML (CID inline logo)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.email.html_templates import default_create_ticket_html_template
from services.db_service import execute_query


def main() -> None:
    body = default_create_ticket_html_template()
    row = execute_query(
        """
        UPDATE email_templates
        SET body = %s,
            subject = COALESCE(NULLIF(TRIM(subject), ''), 'Ticket Created - {{ticket_id}}'),
            updated_at = NOW()
        WHERE event_code = 'CREATE_TICKET'
          AND is_active = TRUE
        RETURNING id, template_name
        """,
        (body,),
        fetch_one=True,
    )
    if row:
        print(f"Updated template: {row.get('template_name')} ({row.get('id')})")
    else:
        print("No active CREATE_TICKET template found to upgrade.")


if __name__ == "__main__":
    main()

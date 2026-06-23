"""Orchestrates event-based email notifications."""

from __future__ import annotations



import logging

from typing import Any, Dict, List, Optional



from app.email import repository as repo

from app.email.email_service import EmailService, build_context



logger = logging.getLogger(__name__)





class EmailNotificationService:

    @staticmethod

    def is_event_enabled(tenant_id: str, event_code: str) -> bool:

        row = repo.get_notification_by_event(tenant_id, event_code)

        return bool(row and row.get("email_enabled"))



    @staticmethod

    def send_for_event(

        event_code: str,

        tenant_id: str,

        recipient_emails: List[str],

        *,

        ticket: Optional[Dict[str, Any]] = None,

        user: Optional[Dict[str, Any]] = None,

        extra_context: Optional[Dict[str, Any]] = None,

    ) -> Dict[str, Any]:

        if not EmailNotificationService.is_event_enabled(tenant_id, event_code):

            return {"success": True, "skipped": True, "message": "Event notification disabled"}



        smtp_config = repo.get_active_configuration(tenant_id)

        if not smtp_config:

            return {"success": False, "message": "No active SMTP configuration"}



        template = repo.get_active_template_for_event(tenant_id, event_code)

        if not template:

            return {"success": False, "message": f"No active template for event {event_code}"}



        unique_recipients = sorted({e.strip().lower() for e in recipient_emails if e and e.strip()})

        if not unique_recipients:

            return {"success": False, "message": "No valid recipient emails"}



        last_result: Dict[str, Any] = {"success": True, "message": "No recipients"}

        for recipient in unique_recipients:

            recipient_user = user

            if not recipient_user or recipient_user.get("email", "").lower() != recipient:

                recipient_user = repo.resolve_user_by_email(recipient, tenant_id)



            context = build_context(

                ticket=ticket,

                user=recipient_user,

                extra=extra_context,

            )

            last_result = EmailService.send_email(

                smtp_config,

                [recipient],

                template.get("subject") or "",

                template.get("body") or "",

                context,

            )

            if not last_result.get("success"):

                logger.warning(

                    "Email to %s for event %s failed: %s",

                    recipient,

                    event_code,

                    last_result.get("message"),

                )

                return last_result



        return last_result



    @staticmethod

    def notify_ticket_created(

        tenant_id: str,

        task: Dict[str, Any],

        creator_email: Optional[str],

    ) -> None:

        try:

            recipients: List[str] = []

            if creator_email:

                recipients.append(creator_email)

            owner = task.get("owner_email")

            if owner:

                recipients.append(owner)



            created_by_name = ""

            if task.get("created_by_email"):

                created_by_name = task["created_by_email"]

            elif task.get("created_by"):

                created_by_name = repo.resolve_user_display(str(task["created_by"]))



            enriched = dict(task)

            enriched["created_by_name"] = created_by_name

            enriched["created_by_email"] = task.get("created_by_email") or creator_email



            result = EmailNotificationService.send_for_event(

                "CREATE_TICKET",

                tenant_id,

                recipients,

                ticket=enriched,

            )

            if not result.get("success") and not result.get("skipped"):

                logger.warning("Create ticket email failed: %s", result.get("message"))

        except Exception:

            logger.exception("Create ticket email notification failed")

    @staticmethod
    def notify_work_started(
        tenant_id: str,
        task: Dict[str, Any],
        actor_email: Optional[str],
    ) -> None:
        try:
            recipients: List[str] = []
            creator = task.get("created_by_email")
            if creator:
                recipients.append(creator)
            owner = task.get("owner_email")
            if owner:
                recipients.append(owner)

            enriched = dict(task)
            enriched["created_by_email"] = creator
            if actor_email:
                enriched["started_by_email"] = actor_email

            result = EmailNotificationService.send_for_event(
                "WORK_STARTED",
                tenant_id,
                recipients,
                ticket=enriched,
            )
            if not result.get("success") and not result.get("skipped"):
                logger.warning("Work started email failed: %s", result.get("message"))
        except Exception:
            logger.exception("Work started email notification failed")



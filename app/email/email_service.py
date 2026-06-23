"""Reusable SMTP email service with variable substitution and HTML support."""
from __future__ import annotations

import asyncio
import logging
import re
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import FRONTEND_PUBLIC_URL
from app.email.email_assets import (
    attach_inline_logo,
    html_uses_inline_logo,
    normalize_html_logo_references,
)
from app.email.html_templates import html_to_plain_text, is_html_content

logger = logging.getLogger(__name__)

_VARIABLE_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def format_ticket_id(task_id: Optional[str]) -> str:
    if not task_id:
        return ""
    raw = str(task_id)
    if len(raw) >= 8:
        return f"KZN-{raw[:8].upper()}"
    return f"KZN-{raw.upper()}"


def format_display_status(status: Optional[str]) -> str:
    if not status:
        return ""
    return str(status).replace("_", " ").title()


def format_display_date(value: Optional[str]) -> str:
    if not value:
        return "—"
    raw = str(value).strip()
    if len(raw) >= 10:
        try:
            parsed = datetime.strptime(raw[:10], "%Y-%m-%d")
            return parsed.strftime("%d/%m/%Y")
        except ValueError:
            pass
    return raw


def get_ticket_url(task_id: Optional[str]) -> str:
    if not task_id:
        return FRONTEND_PUBLIC_URL
    return f"{FRONTEND_PUBLIC_URL}/tasks/{task_id}"


def build_context(
    *,
    ticket: Optional[Dict[str, Any]] = None,
    user: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    now = datetime.now(timezone.utc)
    ctx: Dict[str, str] = {
        "current_date": now.strftime("%Y-%m-%d"),
        "current_datetime": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "app_url": FRONTEND_PUBLIC_URL,
    }
    if ticket:
        task_id = ticket.get("id")
        ctx.update({
            "ticket_id": format_ticket_id(task_id),
            "ticket_title": str(ticket.get("title") or ""),
            "ticket_description": str(ticket.get("description") or ""),
            "priority": str(ticket.get("priority") or ""),
            "status": format_display_status(ticket.get("status")),
            "created_by": str(
                ticket.get("created_by_name")
                or ticket.get("created_by_email")
                or ticket.get("created_by")
                or ""
            ),
            "assignee": str(ticket.get("owner_email") or ticket.get("assignee") or ""),
            "due_date": format_display_date(ticket.get("due_date")),
            "ticket_url": get_ticket_url(task_id),
        })
    if user:
        name = str(user.get("name") or user.get("full_name") or "").strip()
        email = str(user.get("email") or "").strip()
        ctx.update({
            "user_name": name or (email.split("@")[0] if email else "User"),
            "user_email": email,
        })
    elif "user_name" not in ctx:
        ctx["user_name"] = "User"
    if extra:
        for key, value in extra.items():
            ctx[str(key)] = "" if value is None else str(value)
    if ticket and (not ctx.get("ticket_url")):
        ctx["ticket_url"] = get_ticket_url(ticket.get("id"))
    return ctx


def replace_variables(text: str, context: Dict[str, str]) -> str:
    if not text:
        return ""

    def _sub(match: re.Match) -> str:
        key = match.group(1)
        return context.get(key, match.group(0))

    return _VARIABLE_PATTERN.sub(_sub, text)


class EmailService:
    """Load SMTP settings, render templates, and send email."""

    @staticmethod
    def _build_message(
        config: Dict[str, Any],
        to_emails: List[str],
        subject: str,
        body: str,
        *,
        is_html: bool = False,
    ) -> MIMEMultipart:
        from_email = (config.get("from_email") or "").strip()
        from_name = (config.get("from_name") or "").strip()
        sender = f"{from_name} <{from_email}>" if from_name else from_email

        embed_logo = is_html and html_uses_inline_logo(body)
        msg = MIMEMultipart("related" if embed_logo else "alternative")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = ", ".join(to_emails)

        if is_html:
            alternative = MIMEMultipart("alternative")
            plain = html_to_plain_text(body)
            alternative.attach(
                MIMEText(
                    plain or "View this message in an HTML-capable email client.",
                    "plain",
                    "utf-8",
                )
            )
            alternative.attach(MIMEText(body, "html", "utf-8"))
            if embed_logo:
                msg.attach(alternative)
                attach_inline_logo(msg)
            else:
                for part in alternative.get_payload():
                    msg.attach(part)
        else:
            msg.attach(MIMEText(body, "plain", "utf-8"))

        return msg

    @staticmethod
    def _smtp_send(
        config: Dict[str, Any],
        to_emails: List[str],
        subject: str,
        body: str,
        *,
        is_html: bool = False,
    ) -> Tuple[bool, str]:
        host = (config.get("smtp_host") or "").strip()
        port = int(config.get("smtp_port") or 587)
        auth_required = bool(config.get("authentication_required", True))
        username = (config.get("username") or "").strip()
        password = config.get("password") or ""
        from_email = (config.get("from_email") or "").strip()

        if not host:
            return False, "SMTP host is required"
        if not from_email:
            return False, "From email address is required"
        if not to_emails:
            return False, "At least one recipient is required"
        if auth_required and (not username or not password):
            return False, "SMTP username and password are required when authentication is enabled"

        msg = EmailService._build_message(config, to_emails, subject, body, is_html=is_html)
        context = ssl.create_default_context()

        try:
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.ehlo()
                if server.has_extn("starttls"):
                    server.starttls(context=context)
                    server.ehlo()
                if auth_required:
                    server.login(username, password)
                server.sendmail(from_email, to_emails, msg.as_string())
            return True, "Email sent successfully"
        except smtplib.SMTPAuthenticationError as exc:
            logger.warning("SMTP authentication failed: %s", exc)
            return False, f"SMTP authentication failed: {exc}"
        except smtplib.SMTPException as exc:
            logger.warning("SMTP error: %s", exc)
            return False, f"SMTP error: {exc}"
        except OSError as exc:
            logger.warning("SMTP connection error: %s", exc)
            return False, f"Connection failed: {exc}"

    @staticmethod
    def test_connection(config: Dict[str, Any]) -> Tuple[bool, str]:
        host = (config.get("smtp_host") or "").strip()
        port = int(config.get("smtp_port") or 587)
        auth_required = bool(config.get("authentication_required", True))
        username = (config.get("username") or "").strip()
        password = config.get("password") or ""

        if not host:
            return False, "SMTP host is required"
        if auth_required and (not username or not password):
            return False, "SMTP username and password are required when authentication is enabled"

        context = ssl.create_default_context()
        try:
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.ehlo()
                if server.has_extn("starttls"):
                    server.starttls(context=context)
                    server.ehlo()
                if auth_required:
                    server.login(username, password)
            return True, "SMTP connection successful"
        except smtplib.SMTPAuthenticationError as exc:
            return False, f"SMTP authentication failed: {exc}"
        except smtplib.SMTPException as exc:
            return False, f"SMTP error: {exc}"
        except OSError as exc:
            return False, f"Connection failed: {exc}"

    @staticmethod
    def send_email(
        config: Dict[str, Any],
        to_emails: List[str],
        subject: str,
        body: str,
        context: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        rendered_subject = replace_variables(subject, context or {})
        rendered_body = replace_variables(body, context or {})
        if is_html_content(rendered_body):
            rendered_body = normalize_html_logo_references(rendered_body)

        unique_recipients = sorted({e.strip().lower() for e in to_emails if e and e.strip()})
        if not unique_recipients:
            return {"success": False, "message": "No valid recipient emails"}

        html_mode = is_html_content(rendered_body)
        ok, message = EmailService._smtp_send(
            config,
            unique_recipients,
            rendered_subject,
            rendered_body,
            is_html=html_mode,
        )
        return {"success": ok, "message": message, "format": "html" if html_mode else "plain"}

    @staticmethod
    async def send_email_async(
        config: Dict[str, Any],
        to_emails: List[str],
        subject: str,
        body: str,
        context: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            EmailService.send_email,
            config,
            to_emails,
            subject,
            body,
            context,
        )

    @staticmethod
    async def test_connection_async(config: Dict[str, Any]) -> Tuple[bool, str]:
        return await asyncio.to_thread(EmailService.test_connection, config)

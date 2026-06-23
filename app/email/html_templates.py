"""Default HTML email templates and helpers for Master Minds notifications."""

from __future__ import annotations

import re
from typing import Optional

# Safe email brand color (lime chartreuse — matches Master Minds theme)
BRAND_COLOR = "#D6FF1F"
BRAND_TEXT = "#1A1A1A"
BRAND_MUTED_BG = "#F4F5F0"

# Header logo display size (px). Asset is trimmed + 2× for retina (~103px total header with padding).
HEADER_LOGO_WIDTH = 160
HEADER_LOGO_HEIGHT = 87
HEADER_PADDING_TOP = 8
HEADER_PADDING_BOTTOM = 8
HEADER_PADDING_X = 16

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def is_html_content(body: Optional[str]) -> bool:
    if not body:
        return False
    text = body.strip().lower()
    return (
        text.startswith("<!doctype")
        or text.startswith("<html")
        or "<table" in text
        or "<div" in text
    )


def html_to_plain_text(html: str) -> str:
    if not html:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    text = re.sub(r"</p>", "\n\n", text, flags=re.I)
    text = re.sub(r"</tr>", "\n", text, flags=re.I)
    text = re.sub(r"</td>", " ", text, flags=re.I)
    text = _HTML_TAG_RE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def default_create_ticket_html_template() -> str:
    """Responsive, table-based HTML template for CREATE_TICKET (variables only)."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta http-equiv="X-UA-Compatible" content="IE=edge" />
  <title>Ticket Created - {{{{ticket_id}}}}</title>
</head>
<body style="margin:0;padding:0;background-color:#E9EAE3;font-family:Arial,Helvetica,sans-serif;-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;">
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background-color:#E9EAE3;margin:0;padding:0;">
    <tr>
      <td align="center" style="padding:24px 12px;">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="600" style="width:100%;max-width:600px;background-color:#FFFFFF;border:1px solid #C8D1C1;border-radius:12px;overflow:hidden;">
          <!-- Header: centered logo -->
          <tr>
            <td align="center" style="background-color:{BRAND_COLOR};padding:{HEADER_PADDING_TOP}px {HEADER_PADDING_X}px {HEADER_PADDING_BOTTOM}px {HEADER_PADDING_X}px;border-bottom:1px solid #C8D1C1;line-height:0;font-size:0;mso-line-height-rule:exactly;">
              <img
                src="cid:masterminds_logo"
                alt="Master Minds"
                width="{HEADER_LOGO_WIDTH}"
                height="{HEADER_LOGO_HEIGHT}"
                style="display:block;margin:0 auto;border:0;outline:none;text-decoration:none;width:{HEADER_LOGO_WIDTH}px;max-width:{HEADER_LOGO_WIDTH}px;height:auto;line-height:0;-ms-interpolation-mode:bicubic;mso-line-height-rule:exactly;"
              />
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding:28px 24px 20px 24px;font-family:Arial,Helvetica,sans-serif;color:{BRAND_TEXT};">
              <p style="margin:0 0 16px 0;font-size:16px;line-height:1.5;color:{BRAND_TEXT};">
                Hello <strong>{{{{user_name}}}}</strong>,
              </p>
              <p style="margin:0 0 20px 0;font-size:15px;line-height:1.6;color:#4B5563;">
                A new ticket has been created.
              </p>
              <!-- Ticket details card -->
              <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background-color:{BRAND_MUTED_BG};border:1px solid #C8D1C1;border-radius:8px;margin:0 0 24px 0;">
                <tr>
                  <td style="padding:16px 18px;">
                    <p style="margin:0 0 12px 0;font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:0.04em;color:#6B7280;">Ticket Details</p>
                    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="font-size:14px;line-height:1.5;">
                      <tr>
                        <td width="130" valign="top" style="padding:6px 0;font-weight:600;color:#374151;border-bottom:1px solid #E5E7EB;">Ticket ID</td>
                        <td valign="top" style="padding:6px 0;color:{BRAND_TEXT};border-bottom:1px solid #E5E7EB;">{{{{ticket_id}}}}</td>
                      </tr>
                      <tr>
                        <td valign="top" style="padding:6px 0;font-weight:600;color:#374151;border-bottom:1px solid #E5E7EB;">Title</td>
                        <td valign="top" style="padding:6px 0;color:{BRAND_TEXT};border-bottom:1px solid #E5E7EB;">{{{{ticket_title}}}}</td>
                      </tr>
                      <tr>
                        <td valign="top" style="padding:6px 0;font-weight:600;color:#374151;border-bottom:1px solid #E5E7EB;">Priority</td>
                        <td valign="top" style="padding:6px 0;color:{BRAND_TEXT};border-bottom:1px solid #E5E7EB;">{{{{priority}}}}</td>
                      </tr>
                      <tr>
                        <td valign="top" style="padding:6px 0;font-weight:600;color:#374151;border-bottom:1px solid #E5E7EB;">Status</td>
                        <td valign="top" style="padding:6px 0;color:{BRAND_TEXT};border-bottom:1px solid #E5E7EB;">{{{{status}}}}</td>
                      </tr>
                      <tr>
                        <td valign="top" style="padding:6px 0;font-weight:600;color:#374151;border-bottom:1px solid #E5E7EB;">Due Date</td>
                        <td valign="top" style="padding:6px 0;color:{BRAND_TEXT};border-bottom:1px solid #E5E7EB;">{{{{due_date}}}}</td>
                      </tr>
                      <tr>
                        <td valign="top" style="padding:6px 0;font-weight:600;color:#374151;">Created By</td>
                        <td valign="top" style="padding:6px 0;color:{BRAND_TEXT};">{{{{created_by}}}}</td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
              <!-- CTA -->
              <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                  <td align="center" style="padding:8px 0 4px 0;">
                    <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <td align="center" bgcolor="{BRAND_COLOR}" style="background-color:{BRAND_COLOR};border-radius:8px;">
                          <a href="{{{{ticket_url}}}}" target="_blank" style="display:inline-block;padding:14px 32px;font-family:Arial,Helvetica,sans-serif;font-size:15px;font-weight:700;color:{BRAND_TEXT};text-decoration:none;border-radius:8px;mso-padding-alt:0;">
                            <!--[if mso]><i style="letter-spacing:25px;mso-font-width:-100%;mso-text-raise:18pt">&nbsp;</i><![endif]-->
                            <span style="mso-text-raise:9pt;">View Ticket</span>
                            <!--[if mso]><i style="letter-spacing:25px;mso-font-width:-100%">&nbsp;</i><![endif]-->
                          </a>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="padding:20px 24px 24px 24px;border-top:1px solid #E5E7EB;font-family:Arial,Helvetica,sans-serif;">
              <p style="margin:0 0 8px 0;font-size:14px;line-height:1.5;color:{BRAND_TEXT};">
                Regards,<br /><strong>Master Minds Team</strong>
              </p>
              <p style="margin:16px 0 0 0;font-size:12px;line-height:1.6;color:#9CA3AF;text-align:center;">
                &copy; Master Minds<br />
                Enterprise Ticket Management System<br /><br />
                This is an automated email. Please do not reply.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

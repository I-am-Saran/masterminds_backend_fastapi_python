"""Email notification event codes and template variables."""

EVENT_CODES = {
    "LOGIN": "Login",
    "USER_CREATED": "User Created",
    "CREATE_TICKET": "Create Ticket",
    "WORK_STARTED": "Work Started",
    "UPDATE_TICKET": "Update Ticket",
    "ASSIGN_TICKET": "Assign Ticket",
    "CLOSE_TICKET": "Close Ticket",
    "REOPEN_TICKET": "Reopen Ticket",
    "COMMENT_ADDED": "Comment Added",
}

EMAIL_PROVIDERS = [
    {"value": "generic_smtp", "label": "Generic SMTP"},
    {"value": "gmail", "label": "Gmail"},
    {"value": "outlook", "label": "Outlook / Office 365"},
    {"value": "sendgrid", "label": "SendGrid"},
    {"value": "amazon_ses", "label": "Amazon SES"},
]

TEMPLATE_VARIABLES = {
    "ticket": [
        "{{ticket_id}}",
        "{{ticket_title}}",
        "{{ticket_description}}",
        "{{priority}}",
        "{{status}}",
        "{{created_by}}",
        "{{assignee}}",
        "{{due_date}}",
        "{{ticket_url}}",
    ],
    "user": [
        "{{user_name}}",
        "{{user_email}}",
    ],
    "system": [
        "{{current_date}}",
        "{{current_datetime}}",
        "{{app_url}}",
    ],
    "branding": [
        "cid:masterminds_logo (inline logo — embedded automatically, use in <img src>)",
    ],
}

"""Permission codes for Kaizen Tasks module."""

from app.tasks.constants import MODULE_NAME


def perm(action: str) -> str:
    return f"{MODULE_NAME}_{action}"


PERM_RETRIEVE = perm("retrieve")
PERM_CREATE = perm("create")
PERM_UPDATE = perm("update")
PERM_DELETE = perm("delete")
PERM_ASSIGN = perm("assign")
PERM_COMMENT = perm("comment")

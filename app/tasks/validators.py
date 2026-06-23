"""Field validators for Kaizen Tasks."""

from typing import Optional

from fastapi import HTTPException

from app.tasks.constants import PRIORITIES, SOURCE_TYPES, STATUSES, TICKET_CATEGORIES_SET


def validate_status(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = value.strip().upper()
    if v not in STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {value}")
    return v


def validate_priority(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = value.strip().upper()
    if v not in PRIORITIES:
        raise HTTPException(status_code=400, detail=f"Invalid priority: {value}")
    return v


def validate_source_type(
    value: Optional[str],
    meeting_id: Optional[int] = None,
) -> str:
    if meeting_id:
        return "meeting"
    if value is None:
        return "manual"
    v = value.strip().lower()
    if v not in SOURCE_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid source_type: {value}")
    return v


def normalize_email(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return value.strip().lower()


def validate_category(
    value: Optional[str],
    *,
    existing: Optional[str] = None,
    required: bool = False,
) -> Optional[str]:
    if value is None or not str(value).strip():
        if required:
            raise HTTPException(status_code=400, detail="Category is required")
        return None
    v = str(value).strip()
    if existing and v == existing.strip():
        return v
    if v not in TICKET_CATEGORIES_SET:
        raise HTTPException(status_code=400, detail=f"Invalid category: {value}")
    return v

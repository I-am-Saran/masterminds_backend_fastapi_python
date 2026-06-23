"""Pydantic schemas for Kaizen Tasks API."""

from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class TaskStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class TaskPriority(str, Enum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class TaskSourceType(str, Enum):
    MANUAL = "manual"
    MEETING = "meeting"


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=1000)
    description: Optional[str] = None
    owner_email: Optional[str] = None
    status: TaskStatus = TaskStatus.OPEN
    priority: TaskPriority = TaskPriority.P3
    due_date: Optional[date] = None
    category: Optional[str] = None
    meeting_id: Optional[int] = None
    source_type: TaskSourceType = TaskSourceType.MANUAL
    is_blocked: bool = False
    blocked_reason: Optional[str] = None
    watcher_emails: Optional[List[str]] = None
    sync_mom_action: bool = True

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        t = v.strip()
        if not t:
            raise ValueError("title is required")
        return t


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=1000)
    description: Optional[str] = None
    owner_email: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    due_date: Optional[date] = None
    category: Optional[str] = None
    is_blocked: Optional[bool] = None
    blocked_reason: Optional[str] = None
    watcher_emails: Optional[List[str]] = None


class TaskStatusPatch(BaseModel):
    status: TaskStatus
    blocked_reason: Optional[str] = None


class TaskCommentCreate(BaseModel):
    comment: str = Field(..., min_length=1)

    @field_validator("comment")
    @classmethod
    def strip_comment(cls, v: str) -> str:
        t = v.strip()
        if not t:
            raise ValueError("comment is required")
        return t


class TaskListParams(BaseModel):
    page: int = Field(1, ge=1)
    limit: int = Field(50, ge=1, le=200)
    search: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    owner_email: Optional[str] = None
    meeting_id: Optional[int] = None
    overdue: Optional[bool] = None
    blocked: Optional[bool] = None
    mine: Optional[bool] = None
    stale: Optional[bool] = None
    sort_by: str = "due_date"
    sort_desc: bool = False


class TaskResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    title: str
    description: Optional[str] = None
    owner_email: Optional[str] = None
    owner_id: Optional[UUID] = None
    status: str
    priority: str
    due_date: Optional[date] = None
    category: Optional[str] = None
    meeting_id: Optional[int] = None
    source_type: str
    is_blocked: bool
    blocked_reason: Optional[str] = None
    last_activity_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    meeting_title: Optional[str] = None
    ageing_days: Optional[int] = None
    comment_count: Optional[int] = 0
    watchers: Optional[List[str]] = None

    class Config:
        from_attributes = True


class PaginatedTasks(BaseModel):
    success: bool = True
    data: List[Dict[str, Any]]
    meta: Dict[str, Any]
    message: str = "Tasks retrieved successfully"

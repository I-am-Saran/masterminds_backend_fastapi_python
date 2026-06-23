"""Pydantic schemas for workflow engine."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

AssignmentType = Literal["TEAM", "ROLE", "USER"]


class WorkflowLevelBase(BaseModel):
    level_sequence: int = Field(..., ge=1)
    level_name: str = Field(..., min_length=1, max_length=255)
    assignment_type: AssignmentType
    assignment_value: Optional[str] = None
    sla_hours: Optional[int] = Field(None, ge=0)
    escalation_enabled: bool = False
    escalation_type: Optional[AssignmentType] = None
    escalation_value: Optional[str] = None
    mandatory_comments: bool = False
    mandatory_attachments: bool = False
    can_reject: bool = False
    can_reassign: bool = False
    allow_skip: bool = False


class WorkflowLevelCreate(WorkflowLevelBase):
    pass


class WorkflowLevelOut(WorkflowLevelBase):
    id: str
    workflow_id: str
    assignment_label: Optional[str] = None
    escalation_label: Optional[str] = None


class WorkflowCreate(BaseModel):
    workflow_name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    ticket_category: Optional[str] = Field(None, max_length=100)
    workflow_status: Literal["DRAFT", "ACTIVE", "INACTIVE"] = "DRAFT"
    is_active: Optional[bool] = None  # legacy sync; derived from workflow_status if omitted
    levels: List[WorkflowLevelCreate] = Field(default_factory=list)


class WorkflowUpdate(BaseModel):
    workflow_name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    ticket_category: Optional[str] = Field(None, max_length=100)
    workflow_status: Optional[Literal["DRAFT", "ACTIVE", "INACTIVE"]] = None
    is_active: Optional[bool] = None
    levels: Optional[List[WorkflowLevelCreate]] = None


class WorkflowMappingCreate(BaseModel):
    ticket_category: str = Field(..., min_length=1, max_length=100)
    workflow_id: str = Field(..., min_length=1)


class WorkflowMappingUpdate(BaseModel):
    workflow_id: str = Field(..., min_length=1)


class WorkflowAdvance(BaseModel):
    action: Literal["COMPLETE", "REJECT", "SKIP", "REASSIGN"] = "COMPLETE"
    comments: Optional[str] = None
    reassign_user_id: Optional[str] = None


class WorkflowLevelProgress(BaseModel):
    level_id: str
    level_sequence: int
    level_name: str
    status: Literal["COMPLETED", "IN_PROGRESS", "PENDING", "REJECTED", "SKIPPED"]
    sla_hours: Optional[int] = None
    assignment_type: Optional[str] = None
    assignment_label: Optional[str] = None
    can_reject: Optional[bool] = None
    can_reassign: Optional[bool] = None
    allow_skip: Optional[bool] = None


class TicketWorkflowState(BaseModel):
    instance_id: Optional[str] = None
    workflow_id: Optional[str] = None
    workflow_name: Optional[str] = None
    workflow_status: Optional[str] = None
    ticket_status: Optional[str] = None
    requires_start_work: bool = False
    current_level_id: Optional[str] = None
    current_level_name: Optional[str] = None
    current_owner_email: Optional[str] = None
    current_owner_label: Optional[str] = None
    can_act: bool = False
    can_reject: bool = False
    can_reassign: bool = False
    allow_skip: bool = False
    levels: List[WorkflowLevelProgress] = Field(default_factory=list)
    history: List[dict] = Field(default_factory=list)

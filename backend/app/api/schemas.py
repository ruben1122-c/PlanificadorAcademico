from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """Credentials payload for password login."""

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=512)


class UserResponse(BaseModel):
    """Authenticated user representation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str


class LoginResponse(BaseModel):
    """Session response returned after successful login."""

    model_config = ConfigDict(from_attributes=True)

    access_token: str
    token_type: str
    expires_in: int | None = None
    refresh_token: str | None = None
    user: UserResponse


class CourseCreateRequest(BaseModel):
    """Payload to create a course for the authenticated owner."""

    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=200)
    term: str | None = Field(default=None, max_length=64)
    credits: int | None = Field(default=None, ge=0, le=30)
    description: str | None = Field(default=None, max_length=1000)


class CourseResponse(BaseModel):
    """Course representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    code: str
    name: str
    term: str | None = None
    credits: int | None = None
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class DocumentResponse(BaseModel):
    """Uploaded syllabus document representation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    course_id: UUID
    filename: str
    content_type: str
    file_size: int
    storage_bucket: str
    storage_path: str
    sha256: str
    created_at: datetime


class ExecutionResponse(BaseModel):
    """Async execution status representation for extraction and planning runs."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    execution_type: Literal["extraction", "planning"] = "extraction"
    document_id: UUID | None = None
    course_id: UUID | None = None
    plan_id: UUID | None = None
    horizon_start: datetime | None = None
    horizon_end: datetime | None = None
    status: str
    model_name: str | None = None
    total_pages: int | None = None
    processed_pages: int = 0
    activities_count: int = 0
    conflicts_count: int = 0
    blocks_count: int | None = None
    pending_count: int | None = None
    error_message: str | None = None
    stage: str | None = None
    attempt_count: int = 0
    stage_timings: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ActivityResponse(BaseModel):
    """Extracted academic activity representation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    course_id: UUID
    document_id: UUID
    execution_id: UUID
    title: str
    activity_type: str
    due_date: date | None = None
    due_time: str | None = None
    weight_percentage: float | None = None
    description: str | None = None
    estimated_minutes: int | None = None
    due_at: datetime | None = None
    source_page: int
    evidence_quote: str
    evidence_valid: bool
    confidence: float | None = None
    review_status: str
    review_notes: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ConflictResponse(BaseModel):
    """Extraction conflict representation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    course_id: UUID
    document_id: UUID
    execution_id: UUID
    activity_id: UUID | None = None
    conflict_type: str
    severity: str
    message: str
    source_page: int | None = None
    details: dict[str, Any]
    resolved: bool
    created_at: datetime


class DocumentActivitiesResponse(BaseModel):
    """Combined extracted activities and conflicts for a syllabus document."""

    document_id: UUID
    activities: list[ActivityResponse]
    conflicts: list[ConflictResponse]


class ActivityReviewRequest(BaseModel):
    """Payload to review or edit an extracted activity."""

    review_status: Literal["pending", "approved", "rejected", "edited"]
    title: str | None = Field(default=None, min_length=1, max_length=250)
    activity_type: Literal[
        "exam",
        "assignment",
        "project",
        "lab",
        "reading",
        "presentation",
        "other",
    ] | None = None
    due_date: date | None = None
    clear_due_date: bool = False
    due_time: str | None = Field(default=None, max_length=32)
    weight_percentage: float | None = Field(default=None, ge=0, le=100)
    clear_weight: bool = False
    description: str | None = Field(default=None, max_length=1000)
    review_notes: str | None = Field(default=None, max_length=1000)
    estimated_minutes: int | None = Field(default=None, gt=0, le=10080)
    clear_estimated_minutes: bool = False
    due_at: datetime | None = None
    clear_due_at: bool = False


class AvailabilityIntervalRequest(BaseModel):
    """Single timezone-aware availability interval."""

    start_at: datetime
    end_at: datetime


class AvailabilityPutRequest(BaseModel):
    """Payload to replace all availability intervals for the authenticated user."""

    intervals: list[AvailabilityIntervalRequest] = Field(default_factory=list)


class AvailabilityWindowResponse(BaseModel):
    """Persisted availability interval representation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    start_at: datetime
    end_at: datetime
    created_at: datetime
    updated_at: datetime


class PlanningRunRequest(BaseModel):
    """Payload to trigger an asynchronous study planning run."""

    course_id: UUID
    horizon_start: datetime
    horizon_end: datetime


class StudyBlockResponse(BaseModel):
    """Persisted study block assigned to an activity."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    activity_id: UUID
    activity_title: str | None = None
    start_at: datetime
    end_at: datetime
    duration_minutes: int


class PlanPendingActivityResponse(BaseModel):
    """Activity that could not be fully scheduled in a study plan."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    activity_id: UUID
    activity_title: str | None = None
    reason: str


class StudyPlanResponse(BaseModel):
    """Traceable study plan with accepted blocks and pending activities."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    course_id: UUID | None = None
    execution_id: UUID
    horizon_start: datetime
    horizon_end: datetime
    model_name: str | None = None
    planner_summary: str | None = None
    blocks: list[StudyBlockResponse]
    pending_activities: list[PlanPendingActivityResponse]
    created_at: datetime

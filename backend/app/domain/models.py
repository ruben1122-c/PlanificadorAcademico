from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class AuthenticatedUser:
    """Authenticated user identity verified by Supabase Auth."""

    id: UUID
    email: str


@dataclass(frozen=True)
class AuthSession:
    """Authentication session returned after password login."""

    access_token: str
    token_type: str
    expires_in: int | None
    refresh_token: str | None
    user: AuthenticatedUser


@dataclass(frozen=True)
class Course:
    """Academic course owned by a specific user."""

    id: UUID
    owner_id: UUID
    code: str
    name: str
    term: str | None
    credits: int | None
    description: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SyllabusDocument:
    """Uploaded syllabus PDF stored in private Supabase Storage."""

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


@dataclass(frozen=True)
class UploadReservation:
    upload_id: UUID
    filename: str
    expires_at: datetime
    status: str


@dataclass(frozen=True)
class ExtractionExecution:
    """Async execution record for a syllabus extraction pipeline run."""

    id: UUID
    owner_id: UUID
    document_id: UUID
    course_id: UUID
    status: str
    model_name: str | None
    total_pages: int | None
    processed_pages: int
    activities_count: int
    conflicts_count: int
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    worker_id: str | None = None
    lease_expires_at: datetime | None = None
    attempt_count: int = 0
    stage: str | None = None
    stage_timings: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SyllabusStatus:
    upload: UploadReservation | None
    document: SyllabusDocument | None
    execution: ExtractionExecution | None
    active_execution: ExtractionExecution | None


@dataclass(frozen=True)
class ExtractedActivity:
    """Academic activity extracted from a syllabus and subject to user review."""

    id: UUID
    owner_id: UUID
    course_id: UUID
    document_id: UUID
    execution_id: UUID
    title: str
    activity_type: str
    due_date: date | None
    due_time: str | None
    weight_percentage: float | None
    description: str | None
    estimated_minutes: int | None
    due_at: datetime | None
    source_page: int
    evidence_quote: str
    evidence_valid: bool
    confidence: float | None
    review_status: str
    review_notes: str | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ExtractionConflict:
    """Validation or consistency conflict recorded during syllabus extraction."""

    id: UUID
    owner_id: UUID
    course_id: UUID
    document_id: UUID
    execution_id: UUID
    activity_id: UUID | None
    conflict_type: str
    severity: str
    message: str
    source_page: int | None
    details: dict[str, Any]
    resolved: bool
    created_at: datetime


@dataclass(frozen=True)
class AvailabilityWindow:
    """Owner-scoped study availability interval with timezone."""

    id: UUID
    owner_id: UUID
    start_at: datetime
    end_at: datetime
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class PlanningExecution:
    """Async execution record for a study planning run."""

    id: UUID
    owner_id: UUID
    status: str
    model_name: str | None
    horizon_start: datetime
    horizon_end: datetime
    plan_id: UUID | None
    activities_count: int
    blocks_count: int
    pending_count: int
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    course_id: UUID | None = None
    worker_id: str | None = None
    lease_expires_at: datetime | None = None
    attempt_count: int = 0
    stage: str | None = None
    stage_timings: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlanBlock:
    """Persisted study block assigned to a specific activity within a plan."""

    id: UUID
    owner_id: UUID
    plan_id: UUID
    activity_id: UUID
    activity_title: str | None
    start_at: datetime
    end_at: datetime
    duration_minutes: int
    created_at: datetime


@dataclass(frozen=True)
class PlanPendingActivity:
    """Activity that could not be fully scheduled in a study plan."""

    id: UUID
    owner_id: UUID
    plan_id: UUID
    activity_id: UUID
    activity_title: str | None
    reason: str
    created_at: datetime


@dataclass(frozen=True)
class StudyPlan:
    """Traceable study plan generated from availability and approved/edited activities."""

    id: UUID
    owner_id: UUID
    execution_id: UUID
    horizon_start: datetime
    horizon_end: datetime
    model_name: str | None
    planner_summary: str | None
    blocks: list[PlanBlock]
    pending_activities: list[PlanPendingActivity]
    created_at: datetime
    course_id: UUID | None = None

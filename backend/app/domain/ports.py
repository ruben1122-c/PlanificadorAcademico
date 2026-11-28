from datetime import date, datetime
from typing import Any, Protocol
from uuid import UUID

from app.domain.models import (
    AuthSession,
    AuthenticatedUser,
    AvailabilityWindow,
    Course,
    ExtractedActivity,
    ExtractionConflict,
    ExtractionExecution,
    PlanningExecution,
    StudyPlan,
    SyllabusDocument,
    SyllabusStatus,
    UploadReservation,
)
from app.domain.planning_rules import StudyBlock, StudyWindow


class AuthGateway(Protocol):
    """Port for authentication operations against an identity provider."""

    def login_with_password(self, email: str, password: str) -> AuthSession:
        """Authenticate a user with email and password."""

    def get_user_from_token(self, access_token: str) -> AuthenticatedUser:
        """Verify a bearer access token and return the associated user."""


class CourseRepository(Protocol):
    """Port for owner-scoped course persistence."""

    def create(
        self,
        owner_id: UUID,
        code: str,
        name: str,
        term: str | None,
        credits: int | None,
        description: str | None,
    ) -> Course:
        """Persist a new course for the given owner."""

    def list_by_owner(self, owner_id: UUID) -> list[Course]:
        """Return all courses belonging to the given owner."""

    def get_by_id_for_owner(self, course_id: UUID, owner_id: UUID) -> Course | None:
        """Return a single course if it belongs to the given owner."""


class StorageGateway(Protocol):
    """Port for private object storage operations."""

    def upload_private_file(
        self,
        bucket: str,
        path: str,
        content: bytes,
        content_type: str,
    ) -> None:
        """Upload a file into a private storage bucket."""

    def download_private_file(self, bucket: str, path: str) -> bytes:
        """Download a file from a private storage bucket."""

    def delete_private_file(self, bucket: str, path: str) -> None:
        """Delete an uncommitted file from private storage."""


class DocumentRepository(Protocol):
    """Port for owner-scoped syllabus document persistence."""

    def reserve_upload(
        self, owner_id: UUID, course_id: UUID, filename: str
    ) -> UploadReservation: ...

    def claim_upload(
        self, owner_id: UUID, course_id: UUID, upload_id: UUID, sha256: str
    ) -> tuple[UploadReservation, SyllabusDocument | None]: ...

    def finish_upload(
        self,
        upload_id: UUID,
        owner_id: UUID,
        course_id: UUID,
        file_size: int,
        storage_bucket: str,
        storage_path: str,
        sha256: str,
    ) -> SyllabusDocument: ...

    def fail_upload(
        self, owner_id: UUID, course_id: UUID, upload_id: UUID, *, receiving: bool
    ) -> bool:
        """Release this upload only if it belongs to the caller and expected phase."""

    def get_syllabus_status(
        self, owner_id: UUID, course_id: UUID, document_id: UUID | None
    ) -> SyllabusStatus: ...

    def list_by_owner(
        self, owner_id: UUID, course_id: UUID | None = None
    ) -> list[SyllabusDocument]:
        """List documents owned by owner_id, optionally filtered by course_id."""

    def get_by_id_for_owner(
        self, document_id: UUID, owner_id: UUID
    ) -> SyllabusDocument | None:
        """Return a document if it belongs to owner_id."""


class ExtractionRepository(Protocol):
    """Port for owner-scoped extraction executions, activities, and conflicts."""

    def create_execution(
        self,
        owner_id: UUID,
        document_id: UUID,
        course_id: UUID,
        model_name: str,
    ) -> ExtractionExecution:
        """Create a pending extraction execution."""

    def get_execution_for_owner(
        self, execution_id: UUID, owner_id: UUID
    ) -> ExtractionExecution | None:
        """Fetch an extraction execution belonging to owner_id."""

    def mark_execution_running(
        self, execution_id: UUID, owner_id: UUID
    ) -> None:
        """Transition an execution to running status."""

    def claim_next_extraction_execution(
        self,
        worker_id: str,
        lease_seconds: int,
        max_attempts: int = 3,
    ) -> ExtractionExecution | None:
        """Atomically claim the next pending or expired extraction execution."""

    def fail_exhausted_extraction_executions(self, max_attempts: int = 3) -> int:
        """Mark expired extraction executions that reached max_attempts as failed."""

    def update_execution_stage(
        self,
        execution_id: UUID,
        owner_id: UUID,
        stage: str,
        stage_timings: dict[str, Any],
        worker_id: str | None = None,
    ) -> None:
        """Update current stage and accumulated timings for an extraction execution."""

    def mark_execution_completed(
        self,
        execution_id: UUID,
        owner_id: UUID,
        total_pages: int,
        processed_pages: int,
        activities_count: int,
        conflicts_count: int,
        stage_timings: dict[str, Any] | None = None,
        worker_id: str | None = None,
    ) -> None:
        """Transition an execution to completed status."""

    def mark_execution_failed(
        self,
        execution_id: UUID,
        owner_id: UUID,
        error_message: str,
        stage_timings: dict[str, Any] | None = None,
        worker_id: str | None = None,
    ) -> None:
        """Transition an execution to failed status."""

    def replace_document_extraction_results(
        self,
        owner_id: UUID,
        course_id: UUID,
        document_id: UUID,
        execution_id: UUID,
        activities: list[dict[str, Any]],
        conflicts: list[dict[str, Any]],
        worker_id: str | None = None,
    ) -> tuple[int, int] | None:
        """Persist extracted activities and conflicts for a document execution."""

    def list_activities_by_document_for_owner(
        self, document_id: UUID, owner_id: UUID
    ) -> list[ExtractedActivity]:
        """List extracted activities for a document belonging to owner_id."""

    def list_conflicts_by_document_for_owner(
        self, document_id: UUID, owner_id: UUID
    ) -> list[ExtractionConflict]:
        """List extraction conflicts for a document belonging to owner_id."""

    def get_activity_for_owner(
        self, activity_id: UUID, owner_id: UUID
    ) -> ExtractedActivity | None:
        """Fetch a single activity belonging to owner_id."""

    def update_activity_review_for_owner(
        self,
        activity_id: UUID,
        owner_id: UUID,
        review_status: str,
        title: str | None = None,
        activity_type: str | None = None,
        due_date: date | None = None,
        clear_due_date: bool = False,
        due_time: str | None = None,
        weight_percentage: float | None = None,
        clear_weight: bool = False,
        description: str | None = None,
        review_notes: str | None = None,
        estimated_minutes: int | None = None,
        clear_estimated_minutes: bool = False,
        due_at: datetime | None = None,
        clear_due_at: bool = False,
    ) -> ExtractedActivity | None:
        """Update review status and optional fields on an owner-scoped activity."""


class PlanningRepository(Protocol):
    """Port for owner-scoped availability, planning runs, and traceable study plans."""

    def replace_availability_for_owner(
        self, owner_id: UUID, windows: list[StudyWindow]
    ) -> list[AvailabilityWindow]:
        """Replace all study availability windows for owner_id."""

    def list_availability_for_owner(
        self, owner_id: UUID
    ) -> list[AvailabilityWindow]:
        """List all study availability windows for owner_id."""

    def list_plannable_activities_for_owner(
        self, owner_id: UUID, course_id: UUID, horizon_start: datetime
    ) -> list[ExtractedActivity]:
        """List approved/edited activities for course_id with estimated_minutes and due_at > horizon_start."""

    def create_planning_execution(
        self,
        owner_id: UUID,
        course_id: UUID,
        horizon_start: datetime,
        horizon_end: datetime,
        model_name: str,
    ) -> PlanningExecution:
        """Create a pending planning execution."""

    def get_planning_execution_for_owner(
        self, execution_id: UUID, owner_id: UUID
    ) -> PlanningExecution | None:
        """Fetch a planning execution belonging to owner_id."""

    def claim_next_planning_execution(
        self,
        worker_id: str,
        lease_seconds: int,
        max_attempts: int = 3,
    ) -> PlanningExecution | None:
        """Atomically claim the next pending or expired planning execution."""

    def fail_exhausted_planning_executions(self, max_attempts: int = 3) -> int:
        """Mark expired planning executions that reached max_attempts as failed."""

    def update_planning_stage(
        self,
        execution_id: UUID,
        owner_id: UUID,
        stage: str,
        stage_timings: dict[str, Any],
        worker_id: str | None = None,
    ) -> None:
        """Update current stage and accumulated timings for a planning execution."""

    def mark_planning_execution_running(
        self, execution_id: UUID, owner_id: UUID
    ) -> None:
        """Transition a planning execution to running status."""

    def mark_planning_execution_completed(
        self,
        execution_id: UUID,
        owner_id: UUID,
        plan_id: UUID,
        activities_count: int,
        blocks_count: int,
        pending_count: int,
        stage_timings: dict[str, Any] | None = None,
        worker_id: str | None = None,
    ) -> None:
        """Transition a planning execution to completed status."""

    def mark_planning_execution_failed(
        self,
        execution_id: UUID,
        owner_id: UUID,
        error_message: str,
        stage_timings: dict[str, Any] | None = None,
        worker_id: str | None = None,
    ) -> None:
        """Transition a planning execution to failed status."""

    def create_study_plan(
        self,
        owner_id: UUID,
        course_id: UUID,
        execution_id: UUID,
        horizon: StudyWindow,
        model_name: str,
        planner_summary: str | None,
        availability_snapshot: list[dict[str, Any]],
        activities_snapshot: list[dict[str, Any]],
        blocks: list[StudyBlock],
        pending: dict[UUID, str],
    ) -> StudyPlan:
        """Persist a traceable study plan with its blocks and pending activities."""

    def get_study_plan_for_owner(
        self, plan_id: UUID, owner_id: UUID, course_id: UUID | None = None
    ) -> StudyPlan | None:
        """Fetch a study plan with blocks and pending activities for owner_id."""

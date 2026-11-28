import logging
import time
from collections.abc import Callable
from datetime import date, datetime
from typing import Any, Protocol
from uuid import UUID

from app.application.error_sanitizer import sanitize_execution_error

from app.application.principal import Principal
from app.domain.exceptions import (
    ActivityNotFoundError,
    CourseNotFoundError,
    DocumentNotFoundError,
    ExecutionNotFoundError,
    ValidationError,
)
from app.domain.models import (
    ExtractedActivity,
    ExtractionConflict,
    ExtractionExecution,
)
from app.domain.ports import (
    CourseRepository,
    DocumentRepository,
    ExtractionRepository,
    StorageGateway,
)


logger = logging.getLogger(__name__)


class ExtractionPipeline(Protocol):
    def run(
        self, *, pdf_bytes: bytes, course_code: str, course_name: str
    ) -> dict[str, Any]: ...

_VALID_REVIEW_STATUSES = {"pending", "approved", "rejected", "edited"}
_VALID_ACTIVITY_TYPES = {
    "exam",
    "assignment",
    "project",
    "lab",
    "reading",
    "presentation",
    "other",
}


class ExtractionService:
    """Application service for async syllabus extraction and human review."""

    def __init__(
        self,
        course_repository: CourseRepository,
        document_repository: DocumentRepository,
        extraction_repository: ExtractionRepository,
        storage_gateway: StorageGateway,
        pipeline: ExtractionPipeline,
        model_name: str,
        pdf_validator: Callable[[bytes], None],
        principal: Principal | None = None,
    ) -> None:
        self._course_repository = course_repository
        self._document_repository = document_repository
        self._extraction_repository = extraction_repository
        self._storage_gateway = storage_gateway
        self._pipeline = pipeline
        self._model_name = model_name
        self._pdf_validator = pdf_validator
        self._principal = principal

    def start_extraction(
        self, document_id: UUID, owner_id: UUID
    ) -> ExtractionExecution:
        """Create a pending extraction execution for an owner-scoped document."""
        document = self._document_repository.get_by_id_for_owner(document_id, owner_id)
        if document is None:
            raise DocumentNotFoundError("Documento no encontrado.")

        course = self._course_repository.get_by_id_for_owner(
            document.course_id, owner_id
        )
        if course is None:
            raise CourseNotFoundError("Curso no encontrado.")

        return self._extraction_repository.create_execution(
            owner_id=owner_id,
            document_id=document.id,
            course_id=course.id,
            model_name=self._model_name,
        )

    def run_extraction_job(
        self,
        execution_id: UUID,
        document_id: UUID,
        owner_id: UUID,
        worker_id: str | None = None,
    ) -> None:
        """Durable worker job that downloads the PDF, runs LangGraph, and persists results."""
        job_start = time.monotonic()
        stage_timings: dict[str, float] = {}

        def _record_stage(stage: str) -> None:
            self._extraction_repository.update_execution_stage(
                execution_id=execution_id,
                owner_id=owner_id,
                stage=stage,
                stage_timings=stage_timings,
                worker_id=worker_id,
            )

        try:
            if worker_id is None:
                self._extraction_repository.mark_execution_running(
                    execution_id, owner_id
                )

            t0 = time.monotonic()
            _record_stage("load_metadata")
            document = self._document_repository.get_by_id_for_owner(
                document_id, owner_id
            )
            if document is None:
                raise DocumentNotFoundError("Documento no encontrado.")

            course = self._course_repository.get_by_id_for_owner(
                document.course_id, owner_id
            )
            if course is None:
                raise CourseNotFoundError("Curso no encontrado.")
            stage_timings["load_metadata_ms"] = round((time.monotonic() - t0) * 1000, 2)

            t0 = time.monotonic()
            _record_stage("download_pdf")
            pdf_bytes = self._storage_gateway.download_private_file(
                bucket=document.storage_bucket,
                path=document.storage_path,
            )
            stage_timings["download_pdf_ms"] = round((time.monotonic() - t0) * 1000, 2)

            _record_stage("validate_pdf")
            t0 = time.monotonic()
            self._pdf_validator(pdf_bytes)
            stage_timings["validate_pdf_ms"] = round((time.monotonic() - t0) * 1000, 2)

            t0 = time.monotonic()
            if self._principal is not None:
                _record_stage("principal_delegate")
                delegation_start = time.monotonic()
                try:
                    self._principal.delegate("documental")
                finally:
                    stage_timings["principal_delegate_ms"] = round(
                        (time.monotonic() - delegation_start) * 1000, 2
                    )
            _record_stage("extract_syllabus")
            result = self._pipeline.run(
                pdf_bytes=pdf_bytes,
                course_code=course.code,
                course_name=course.name,
            )
            stage_timings["extract_syllabus_ms"] = round(
                (time.monotonic() - t0) * 1000, 2
            )

            t0 = time.monotonic()
            _record_stage("persist_results")
            counts = (
                self._extraction_repository.replace_document_extraction_results(
                    owner_id=owner_id,
                    course_id=course.id,
                    document_id=document.id,
                    execution_id=execution_id,
                    activities=result["activities"],
                    conflicts=result["conflicts"],
                    worker_id=worker_id,
                )
            )
            if counts is None:
                return
            activities_count, conflicts_count = counts
            stage_timings["persist_results_ms"] = round(
                (time.monotonic() - t0) * 1000, 2
            )
            stage_timings["total_ms"] = round((time.monotonic() - job_start) * 1000, 2)

            total_pages = int(result["total_pages"])
            self._extraction_repository.mark_execution_completed(
                execution_id=execution_id,
                owner_id=owner_id,
                total_pages=total_pages,
                processed_pages=total_pages,
                activities_count=activities_count,
                conflicts_count=conflicts_count,
                stage_timings=stage_timings,
                worker_id=worker_id,
            )
        except Exception as exc:
            logger.error(
                "Extraction job %s failed (%s)", execution_id, type(exc).__name__
            )
            stage_timings["total_ms"] = round((time.monotonic() - job_start) * 1000, 2)
            self._extraction_repository.mark_execution_failed(
                execution_id=execution_id,
                owner_id=owner_id,
                error_message=sanitize_execution_error(exc),
                stage_timings=stage_timings,
                worker_id=worker_id,
            )

    def get_execution(
        self, execution_id: UUID, owner_id: UUID
    ) -> ExtractionExecution:
        """Return extraction execution status for owner_id."""
        execution = self._extraction_repository.get_execution_for_owner(
            execution_id, owner_id
        )
        if execution is None:
            raise ExecutionNotFoundError("Ejecución de extracción no encontrada.")
        return execution

    def get_document_activities_and_conflicts(
        self, document_id: UUID, owner_id: UUID
    ) -> tuple[list[ExtractedActivity], list[ExtractionConflict]]:
        """Return extracted activities and conflicts for an owner-scoped document."""
        document = self._document_repository.get_by_id_for_owner(document_id, owner_id)
        if document is None:
            raise DocumentNotFoundError("Documento no encontrado.")

        activities = self._extraction_repository.list_activities_by_document_for_owner(
            document_id=document_id,
            owner_id=owner_id,
        )
        conflicts = self._extraction_repository.list_conflicts_by_document_for_owner(
            document_id=document_id,
            owner_id=owner_id,
        )
        return activities, conflicts

    def review_activity(
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
    ) -> ExtractedActivity:
        """Validate review payload and update an owner-scoped extracted activity."""
        normalized_status = review_status.strip().lower()
        if normalized_status not in _VALID_REVIEW_STATUSES:
            raise ValidationError(
                "Estado de revisión inválido. Use pending, approved, rejected o edited."
            )

        normalized_title = title.strip() if title is not None else None
        if normalized_title is not None and not normalized_title:
            raise ValidationError("El título de la actividad no puede estar vacío.")

        normalized_type = activity_type.strip().lower() if activity_type is not None else None
        if normalized_type is not None and normalized_type not in _VALID_ACTIVITY_TYPES:
            raise ValidationError("Tipo de actividad inválido.")

        if weight_percentage is not None and (weight_percentage < 0 or weight_percentage > 100):
            raise ValidationError("La ponderación debe estar entre 0 y 100.")

        if estimated_minutes is not None and estimated_minutes <= 0:
            raise ValidationError("La estimación humana debe ser mayor a 0 minutos.")

        if due_at is not None and due_at.utcoffset() is None:
            raise ValidationError("El vencimiento requiere zona horaria.")

        existing = self._extraction_repository.get_activity_for_owner(
            activity_id, owner_id
        )
        if existing is None:
            raise ActivityNotFoundError("Actividad no encontrada.")

        updated = self._extraction_repository.update_activity_review_for_owner(
            activity_id=activity_id,
            owner_id=owner_id,
            review_status=normalized_status,
            title=normalized_title,
            activity_type=normalized_type,
            due_date=due_date,
            clear_due_date=clear_due_date,
            due_time=due_time.strip() if due_time is not None else None,
            weight_percentage=weight_percentage,
            clear_weight=clear_weight,
            description=description.strip() if description is not None else None,
            review_notes=review_notes.strip() if review_notes is not None else None,
            estimated_minutes=estimated_minutes,
            clear_estimated_minutes=clear_estimated_minutes,
            due_at=due_at,
            clear_due_at=clear_due_at,
        )
        if updated is None:
            raise ActivityNotFoundError("Actividad no encontrada.")
        return updated

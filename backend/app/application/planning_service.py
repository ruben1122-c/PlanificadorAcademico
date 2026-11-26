import logging
import time
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.application.error_sanitizer import sanitize_execution_error
from app.application.principal import Principal
from app.domain.exceptions import (
    CourseNotFoundError,
    PlanNotFoundError,
    ValidationError,
)
from app.domain.models import AvailabilityWindow, PlanningExecution, StudyPlan
from app.domain.planning_rules import PlanningActivity, StudyWindow
from app.domain.ports import CourseRepository, PlanningRepository

logger = logging.getLogger(__name__)


class StudyPlannerPipeline(Protocol):
    def run(
        self,
        *,
        activities: list[PlanningActivity],
        availability: list[StudyWindow],
        horizon: StudyWindow,
        activity_metadata: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]: ...


class PlanningService:
    """Application service for availability windows, async planning runs, and study plans."""

    def __init__(
        self,
        planning_repository: PlanningRepository,
        course_repository: CourseRepository,
        pipeline: StudyPlannerPipeline,
        model_name: str,
        principal: Principal | None = None,
    ) -> None:
        self._planning_repository = planning_repository
        self._course_repository = course_repository
        self._pipeline = pipeline
        self._model_name = model_name
        self._principal = principal

    def replace_availability(
        self,
        owner_id: UUID,
        intervals: list[tuple[datetime, datetime]],
    ) -> list[AvailabilityWindow]:
        """Validate timezone-aware intervals and replace owner's availability."""
        windows: list[StudyWindow] = []
        for start_at, end_at in intervals:
            try:
                windows.append(StudyWindow(start=start_at, end=end_at))
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc

        return self._planning_repository.replace_availability_for_owner(
            owner_id=owner_id,
            windows=windows,
        )

    def list_availability(self, owner_id: UUID) -> list[AvailabilityWindow]:
        """Return all saved availability windows for owner_id."""
        return self._planning_repository.list_availability_for_owner(owner_id)

    def start_planning_run(
        self,
        owner_id: UUID,
        course_id: UUID,
        horizon_start: datetime,
        horizon_end: datetime,
    ) -> PlanningExecution:
        """Validate course ownership and horizon, then enqueue a pending planning execution."""
        course = self._course_repository.get_by_id_for_owner(course_id, owner_id)
        if course is None:
            raise CourseNotFoundError("Curso no encontrado.")

        try:
            horizon = StudyWindow(start=horizon_start, end=horizon_end)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        return self._planning_repository.create_planning_execution(
            owner_id=owner_id,
            course_id=course.id,
            horizon_start=horizon.start,
            horizon_end=horizon.end,
            model_name=self._model_name,
        )

    def run_planning_job(
        self,
        execution_id: UUID,
        owner_id: UUID,
        course_id: UUID,
        horizon_start: datetime,
        horizon_end: datetime,
        worker_id: str | None = None,
    ) -> None:
        """Durable worker job that runs LangGraph + Groq planner and persists blocks/pending."""
        job_start = time.monotonic()
        stage_timings: dict[str, float] = {}

        def _record_stage(stage: str) -> None:
            self._planning_repository.update_planning_stage(
                execution_id=execution_id,
                owner_id=owner_id,
                stage=stage,
                stage_timings=stage_timings,
                worker_id=worker_id,
            )

        try:
            if worker_id is None:
                self._planning_repository.mark_planning_execution_running(
                    execution_id, owner_id
                )

            t0 = time.monotonic()
            _record_stage("load_inputs")
            course = self._course_repository.get_by_id_for_owner(course_id, owner_id)
            if course is None:
                raise CourseNotFoundError("Curso no encontrado.")

            horizon = StudyWindow(start=horizon_start, end=horizon_end)
            availability_rows = self._planning_repository.list_availability_for_owner(
                owner_id
            )
            availability_windows = [
                StudyWindow(start=row.start_at, end=row.end_at)
                for row in availability_rows
            ]

            eligible_activities = (
                self._planning_repository.list_plannable_activities_for_owner(
                    owner_id=owner_id,
                    course_id=course.id,
                    horizon_start=horizon.start,
                )
            )
            stage_timings["load_inputs_ms"] = round((time.monotonic() - t0) * 1000, 2)

            planning_activities: list[PlanningActivity] = []
            activity_metadata: dict[str, dict[str, Any]] = {}
            activities_snapshot: list[dict[str, Any]] = []

            for act in eligible_activities:
                if act.due_at is None or act.estimated_minutes is None:
                    continue
                planning_activities.append(
                    PlanningActivity(
                        activity_id=act.id,
                        due_at=act.due_at,
                        estimated_minutes=act.estimated_minutes,
                    )
                )
                activity_metadata[str(act.id)] = {
                    "title": act.title,
                    "activity_type": act.activity_type,
                    "review_status": act.review_status,
                }
                activities_snapshot.append(
                    {
                        "id": str(act.id),
                        "course_id": str(act.course_id),
                        "title": act.title,
                        "review_status": act.review_status,
                        "estimated_minutes": act.estimated_minutes,
                        "due_at": act.due_at.isoformat(),
                    }
                )

            availability_snapshot = [
                {
                    "start_at": slot.start.isoformat(),
                    "end_at": slot.end.isoformat(),
                }
                for slot in availability_windows
            ]

            t0 = time.monotonic()
            if self._principal is not None:
                _record_stage("principal_delegate")
                delegation_start = time.monotonic()
                try:
                    self._principal.delegate("planificador")
                finally:
                    stage_timings["principal_delegate_ms"] = round(
                        (time.monotonic() - delegation_start) * 1000, 2
                    )
            _record_stage("plan_schedule")
            result = self._pipeline.run(
                activities=planning_activities,
                availability=availability_windows,
                horizon=horizon,
                activity_metadata=activity_metadata,
            )
            stage_timings["plan_schedule_ms"] = round((time.monotonic() - t0) * 1000, 2)

            accepted_blocks = result["accepted_blocks"]
            pending_map = result["pending"]
            planner_summary = result.get("planner_summary")

            t0 = time.monotonic()
            _record_stage("persist_plan")
            plan = self._planning_repository.create_study_plan(
                owner_id=owner_id,
                course_id=course.id,
                execution_id=execution_id,
                horizon=horizon,
                model_name=self._model_name,
                planner_summary=planner_summary,
                availability_snapshot=availability_snapshot,
                activities_snapshot=activities_snapshot,
                blocks=accepted_blocks,
                pending=pending_map,
            )
            stage_timings["persist_plan_ms"] = round((time.monotonic() - t0) * 1000, 2)
            stage_timings["total_ms"] = round((time.monotonic() - job_start) * 1000, 2)

            self._planning_repository.mark_planning_execution_completed(
                execution_id=execution_id,
                owner_id=owner_id,
                plan_id=plan.id,
                activities_count=len(planning_activities),
                blocks_count=len(accepted_blocks),
                pending_count=len(pending_map),
                stage_timings=stage_timings,
                worker_id=worker_id,
            )
        except Exception as exc:
            logger.error(
                "Planning job %s failed (%s)", execution_id, type(exc).__name__
            )
            stage_timings["total_ms"] = round((time.monotonic() - job_start) * 1000, 2)
            self._planning_repository.mark_planning_execution_failed(
                execution_id=execution_id,
                owner_id=owner_id,
                error_message=sanitize_execution_error(exc),
                stage_timings=stage_timings,
                worker_id=worker_id,
            )

    def get_execution_if_exists(
        self, execution_id: UUID, owner_id: UUID
    ) -> PlanningExecution | None:
        """Return a planning execution for owner_id if it exists."""
        return self._planning_repository.get_planning_execution_for_owner(
            execution_id=execution_id,
            owner_id=owner_id,
        )

    def get_plan(
        self, plan_id: UUID, owner_id: UUID, course_id: UUID | None = None
    ) -> StudyPlan:
        """Return a persisted study plan for owner_id (optionally scoped by course_id) or raise 404."""
        if course_id is not None:
            course = self._course_repository.get_by_id_for_owner(course_id, owner_id)
            if course is None:
                raise CourseNotFoundError("Curso no encontrado.")

        plan = self._planning_repository.get_study_plan_for_owner(
            plan_id=plan_id,
            owner_id=owner_id,
            course_id=course_id,
        )
        if plan is None:
            raise PlanNotFoundError("Plan de estudio no encontrado.")
        return plan

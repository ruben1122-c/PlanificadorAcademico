from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_current_user, get_planning_service
from app.api.schemas import (
    ExecutionResponse,
    PlanningRunRequest,
    StudyPlanResponse,
)
from app.application.planning_service import PlanningService
from app.domain.models import AuthenticatedUser

router = APIRouter(tags=["planning"])


@router.post(
    "/planning-runs",
    response_model=ExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_planning_run(
    payload: PlanningRunRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    planning_service: PlanningService = Depends(get_planning_service),
) -> ExecutionResponse:
    """Enqueue a durable PostgreSQL LangGraph + Groq study planning run for a course."""
    execution = planning_service.start_planning_run(
        owner_id=current_user.id,
        course_id=payload.course_id,
        horizon_start=payload.horizon_start,
        horizon_end=payload.horizon_end,
    )
    return ExecutionResponse(
        id=execution.id,
        owner_id=execution.owner_id,
        execution_type="planning",
        course_id=execution.course_id,
        plan_id=execution.plan_id,
        horizon_start=execution.horizon_start,
        horizon_end=execution.horizon_end,
        status=execution.status,
        model_name=execution.model_name,
        activities_count=execution.activities_count,
        blocks_count=execution.blocks_count,
        pending_count=execution.pending_count,
        error_message=execution.error_message,
        stage=execution.stage,
        attempt_count=execution.attempt_count,
        stage_timings=execution.stage_timings,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        created_at=execution.created_at,
        updated_at=execution.updated_at,
    )


@router.get("/plans/{plan_id}", response_model=StudyPlanResponse)
def get_study_plan(
    plan_id: UUID,
    course_id: UUID | None = Query(default=None),
    current_user: AuthenticatedUser = Depends(get_current_user),
    planning_service: PlanningService = Depends(get_planning_service),
) -> StudyPlanResponse:
    """Fetch a persisted study plan with blocks and pending activities for owner_id."""
    plan = planning_service.get_plan(
        plan_id=plan_id,
        owner_id=current_user.id,
        course_id=course_id,
    )
    return StudyPlanResponse.model_validate(plan)

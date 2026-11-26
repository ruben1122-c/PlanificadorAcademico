from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import (
    get_current_user,
    get_extraction_service,
    get_planning_service,
)
from app.api.schemas import ExecutionResponse
from app.application.extraction_service import ExtractionService
from app.application.planning_service import PlanningService
from app.domain.exceptions import ExecutionNotFoundError
from app.domain.models import AuthenticatedUser

router = APIRouter(prefix="/executions", tags=["executions"])


@router.get("/{execution_id}", response_model=ExecutionResponse)
def get_execution_status(
    execution_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    extraction_service: ExtractionService = Depends(get_extraction_service),
    planning_service: PlanningService = Depends(get_planning_service),
) -> ExecutionResponse:
    """Poll the status of an async extraction or planning execution."""
    try:
        extraction = extraction_service.get_execution(
            execution_id=execution_id,
            owner_id=current_user.id,
        )
        return ExecutionResponse.model_validate(extraction)
    except ExecutionNotFoundError:
        planning_exec = planning_service.get_execution_if_exists(
            execution_id=execution_id,
            owner_id=current_user.id,
        )
        if planning_exec is None:
            raise
        return ExecutionResponse(
            id=planning_exec.id,
            owner_id=planning_exec.owner_id,
            execution_type="planning",
            course_id=planning_exec.course_id,
            plan_id=planning_exec.plan_id,
            horizon_start=planning_exec.horizon_start,
            horizon_end=planning_exec.horizon_end,
            status=planning_exec.status,
            model_name=planning_exec.model_name,
            activities_count=planning_exec.activities_count,
            blocks_count=planning_exec.blocks_count,
            pending_count=planning_exec.pending_count,
            error_message=planning_exec.error_message,
            stage=planning_exec.stage,
            attempt_count=planning_exec.attempt_count,
            stage_timings=planning_exec.stage_timings,
            started_at=planning_exec.started_at,
            completed_at=planning_exec.completed_at,
            created_at=planning_exec.created_at,
            updated_at=planning_exec.updated_at,
        )

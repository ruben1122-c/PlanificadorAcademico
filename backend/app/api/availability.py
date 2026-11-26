from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user, get_planning_service
from app.api.schemas import AvailabilityPutRequest, AvailabilityWindowResponse
from app.application.planning_service import PlanningService
from app.domain.models import AuthenticatedUser

router = APIRouter(prefix="/availability", tags=["availability"])


@router.get("", response_model=list[AvailabilityWindowResponse])
def get_availability(
    current_user: AuthenticatedUser = Depends(get_current_user),
    planning_service: PlanningService = Depends(get_planning_service),
) -> list[AvailabilityWindowResponse]:
    """List study availability windows for the authenticated user."""
    windows = planning_service.list_availability(owner_id=current_user.id)
    return [AvailabilityWindowResponse.model_validate(item) for item in windows]


@router.put("", response_model=list[AvailabilityWindowResponse])
def replace_availability(
    payload: AvailabilityPutRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    planning_service: PlanningService = Depends(get_planning_service),
) -> list[AvailabilityWindowResponse]:
    """Replace all study availability windows for the authenticated user."""
    windows = planning_service.replace_availability(
        owner_id=current_user.id,
        intervals=[(item.start_at, item.end_at) for item in payload.intervals],
    )
    return [AvailabilityWindowResponse.model_validate(item) for item in windows]

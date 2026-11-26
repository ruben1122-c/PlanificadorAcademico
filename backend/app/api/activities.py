from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user, get_extraction_service
from app.api.schemas import ActivityResponse, ActivityReviewRequest
from app.application.extraction_service import ExtractionService
from app.domain.models import AuthenticatedUser

router = APIRouter(prefix="/activities", tags=["activities"])


@router.patch("/{activity_id}/review", response_model=ActivityResponse)
def review_activity(
    activity_id: UUID,
    payload: ActivityReviewRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    extraction_service: ExtractionService = Depends(get_extraction_service),
) -> ActivityResponse:
    """Approve, reject, or edit an extracted activity owned by the authenticated user."""
    updated = extraction_service.review_activity(
        activity_id=activity_id,
        owner_id=current_user.id,
        review_status=payload.review_status,
        title=payload.title,
        activity_type=payload.activity_type,
        due_date=payload.due_date,
        clear_due_date=payload.clear_due_date,
        due_time=payload.due_time,
        weight_percentage=payload.weight_percentage,
        clear_weight=payload.clear_weight,
        description=payload.description,
        review_notes=payload.review_notes,
        estimated_minutes=payload.estimated_minutes,
        clear_estimated_minutes=payload.clear_estimated_minutes,
        due_at=payload.due_at,
        clear_due_at=payload.clear_due_at,
    )
    return ActivityResponse.model_validate(updated)

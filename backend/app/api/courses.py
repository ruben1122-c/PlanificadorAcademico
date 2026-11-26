from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_course_service, get_current_user
from app.api.schemas import CourseCreateRequest, CourseResponse
from app.application.course_service import CourseService
from app.domain.models import AuthenticatedUser

router = APIRouter(prefix="/courses", tags=["courses"])


@router.post(
    "",
    response_model=CourseResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_course(
    payload: CourseCreateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    course_service: CourseService = Depends(get_course_service),
) -> CourseResponse:
    """Create a new course owned by the authenticated user."""
    course = course_service.create_course(
        owner_id=current_user.id,
        code=payload.code,
        name=payload.name,
        term=payload.term,
        credits=payload.credits,
        description=payload.description,
    )
    return CourseResponse.model_validate(course)


@router.get("", response_model=list[CourseResponse])
def list_courses(
    current_user: AuthenticatedUser = Depends(get_current_user),
    course_service: CourseService = Depends(get_course_service),
) -> list[CourseResponse]:
    """List all courses owned by the authenticated user."""
    courses = course_service.list_courses(owner_id=current_user.id)
    return [CourseResponse.model_validate(course) for course in courses]


@router.get("/{course_id}", response_model=CourseResponse)
def get_course(
    course_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    course_service: CourseService = Depends(get_course_service),
) -> CourseResponse:
    """Retrieve a single course by ID if owned by the authenticated user."""
    course = course_service.get_course(
        course_id=course_id,
        owner_id=current_user.id,
    )
    return CourseResponse.model_validate(course)

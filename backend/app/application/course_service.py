from uuid import UUID

from app.domain.exceptions import CourseNotFoundError, ValidationError
from app.domain.models import Course
from app.domain.ports import CourseRepository


class CourseService:
    """Application service for owner-scoped course management."""

    def __init__(self, course_repository: CourseRepository) -> None:
        self._course_repository = course_repository

    def create_course(
        self,
        owner_id: UUID,
        code: str,
        name: str,
        term: str | None = None,
        credits: int | None = None,
        description: str | None = None,
    ) -> Course:
        """Validate input and create a course owned by the authenticated user."""
        normalized_code = code.strip()
        normalized_name = name.strip()
        if not normalized_code or not normalized_name:
            raise ValidationError("El código y el nombre del curso son obligatorios.")
        if credits is not None and credits < 0:
            raise ValidationError("Los créditos no pueden ser negativos.")

        normalized_term = term.strip() if term and term.strip() else None
        normalized_description = (
            description.strip() if description and description.strip() else None
        )

        return self._course_repository.create(
            owner_id=owner_id,
            code=normalized_code,
            name=normalized_name,
            term=normalized_term,
            credits=credits,
            description=normalized_description,
        )

    def list_courses(self, owner_id: UUID) -> list[Course]:
        """List all courses belonging to the authenticated user."""
        return self._course_repository.list_by_owner(owner_id)

    def get_course(self, course_id: UUID, owner_id: UUID) -> Course:
        """Fetch a single course belonging to the authenticated user."""
        course = self._course_repository.get_by_id_for_owner(course_id, owner_id)
        if course is None:
            raise CourseNotFoundError("Curso no encontrado.")
        return course

from typing import Any
from uuid import UUID

import psycopg

from app.domain.exceptions import ExternalServiceError
from app.domain.models import Course
from app.infrastructure.db import get_db_connection

_COURSE_COLUMNS = (
    "id, owner_id, code, name, term, credits, description, created_at, updated_at"
)


class PostgresCourseRepository:
    """Psycopg repository for owner-scoped course queries."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    @staticmethod
    def _row_to_course(row: dict[str, Any]) -> Course:
        return Course(
            id=row["id"],
            owner_id=row["owner_id"],
            code=row["code"],
            name=row["name"],
            term=row["term"],
            credits=row["credits"],
            description=row["description"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create(
        self,
        owner_id: UUID,
        code: str,
        name: str,
        term: str | None,
        credits: int | None,
        description: str | None,
    ) -> Course:
        """Insert a new course for owner_id using a parameterized query."""
        query = f"""
            INSERT INTO public.courses (
                owner_id,
                code,
                name,
                term,
                credits,
                description
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING {_COURSE_COLUMNS}
        """
        try:
            with get_db_connection(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        query,
                        (owner_id, code, name, term, credits, description),
                    )
                    row = cur.fetchone()
        except psycopg.Error as exc:
            raise ExternalServiceError(
                "Error al guardar el curso en la base de datos."
            ) from exc

        if row is None:
            raise ExternalServiceError("No se obtuvo el curso creado.")
        return self._row_to_course(row)

    def list_by_owner(self, owner_id: UUID) -> list[Course]:
        """List courses belonging to owner_id using a parameterized query."""
        query = f"""
            SELECT {_COURSE_COLUMNS}
            FROM public.courses
            WHERE owner_id = %s
            ORDER BY created_at DESC
        """
        try:
            with get_db_connection(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (owner_id,))
                    rows = cur.fetchall()
        except psycopg.Error as exc:
            raise ExternalServiceError(
                "Error al consultar los cursos en la base de datos."
            ) from exc

        return [self._row_to_course(row) for row in rows]

    def get_by_id_for_owner(
        self, course_id: UUID, owner_id: UUID
    ) -> Course | None:
        """Fetch a course by id and owner_id using a parameterized query."""
        query = f"""
            SELECT {_COURSE_COLUMNS}
            FROM public.courses
            WHERE id = %s AND owner_id = %s
        """
        try:
            with get_db_connection(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (course_id, owner_id))
                    row = cur.fetchone()
        except psycopg.Error as exc:
            raise ExternalServiceError(
                "Error al consultar el curso en la base de datos."
            ) from exc

        return self._row_to_course(row) if row is not None else None

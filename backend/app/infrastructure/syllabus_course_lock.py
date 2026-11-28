from typing import Any
from uuid import UUID

from psycopg import Cursor

from app.domain.exceptions import CourseNotFoundError, SyllabusBusyError

ACTIVE_UPLOAD = "status IN ('reserved', 'receiving') AND expires_at > clock_timestamp()"
ACTIVE_EXTRACTION = "status IN ('pending', 'running')"


def require_course(
    cur: Cursor[dict[str, Any]], owner_id: UUID, course_id: UUID, *, lock: bool = False
) -> None:
    query = "SELECT id FROM public.courses WHERE id = %s AND owner_id = %s"
    if lock:
        query += " FOR UPDATE"
    cur.execute(query, (course_id, owner_id))
    if cur.fetchone() is None:
        raise CourseNotFoundError("Curso no encontrado.")


def require_idle_syllabus(
    cur: Cursor[dict[str, Any]], owner_id: UUID, course_id: UUID
) -> None:
    """Check the two operation types while the caller holds the course lock."""
    cur.execute(
        f"""
        SELECT EXISTS (
            SELECT 1 FROM public.syllabus_upload_reservations
            WHERE owner_id = %s AND course_id = %s AND {ACTIVE_UPLOAD}
        ) OR EXISTS (
            SELECT 1 FROM public.extraction_executions
            WHERE owner_id = %s AND course_id = %s AND {ACTIVE_EXTRACTION}
        ) AS busy
        """,
        (owner_id, course_id, owner_id, course_id),
    )
    if cur.fetchone()["busy"]:
        raise SyllabusBusyError("Ya hay una carga o un análisis activo en este curso.")

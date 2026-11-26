from typing import Any
from uuid import UUID

import psycopg

from app.domain.exceptions import ExternalServiceError
from app.domain.models import SyllabusDocument
from app.infrastructure.db import get_db_connection

_DOCUMENT_COLUMNS = (
    "id, owner_id, course_id, filename, content_type, file_size, "
    "storage_bucket, storage_path, sha256, created_at"
)


class PostgresDocumentRepository:
    """Psycopg repository for owner-scoped syllabus document queries."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    @staticmethod
    def _row_to_document(row: dict[str, Any]) -> SyllabusDocument:
        return SyllabusDocument(
            id=row["id"],
            owner_id=row["owner_id"],
            course_id=row["course_id"],
            filename=row["filename"],
            content_type=row["content_type"],
            file_size=row["file_size"],
            storage_bucket=row["storage_bucket"],
            storage_path=row["storage_path"],
            sha256=row["sha256"],
            created_at=row["created_at"],
        )

    def create(
        self,
        document_id: UUID,
        owner_id: UUID,
        course_id: UUID,
        filename: str,
        content_type: str,
        file_size: int,
        storage_bucket: str,
        storage_path: str,
        sha256: str,
    ) -> SyllabusDocument:
        """Insert a syllabus document record owned by owner_id."""
        query = f"""
            INSERT INTO public.documents (
                id,
                owner_id,
                course_id,
                filename,
                content_type,
                file_size,
                storage_bucket,
                storage_path,
                sha256
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING {_DOCUMENT_COLUMNS}
        """
        try:
            with get_db_connection(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        query,
                        (
                            document_id,
                            owner_id,
                            course_id,
                            filename,
                            content_type,
                            file_size,
                            storage_bucket,
                            storage_path,
                            sha256,
                        ),
                    )
                    row = cur.fetchone()
        except psycopg.Error as exc:
            raise ExternalServiceError(
                "Error al guardar el documento en la base de datos."
            ) from exc

        if row is None:
            raise ExternalServiceError("No se obtuvo el documento creado.")
        return self._row_to_document(row)

    def list_by_owner(
        self, owner_id: UUID, course_id: UUID | None = None
    ) -> list[SyllabusDocument]:
        """List documents owned by owner_id, optionally filtered by course_id."""
        if course_id is not None:
            query = f"""
                SELECT {_DOCUMENT_COLUMNS}
                FROM public.documents
                WHERE owner_id = %s AND course_id = %s
                ORDER BY created_at DESC
            """
            params: tuple[Any, ...] = (owner_id, course_id)
        else:
            query = f"""
                SELECT {_DOCUMENT_COLUMNS}
                FROM public.documents
                WHERE owner_id = %s
                ORDER BY created_at DESC
            """
            params = (owner_id,)

        try:
            with get_db_connection(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    rows = cur.fetchall()
        except psycopg.Error as exc:
            raise ExternalServiceError(
                "Error al consultar los documentos en la base de datos."
            ) from exc

        return [self._row_to_document(row) for row in rows]

    def get_by_id_for_owner(
        self, document_id: UUID, owner_id: UUID
    ) -> SyllabusDocument | None:
        """Fetch a document by id and owner_id."""
        query = f"""
            SELECT {_DOCUMENT_COLUMNS}
            FROM public.documents
            WHERE id = %s AND owner_id = %s
        """
        try:
            with get_db_connection(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (document_id, owner_id))
                    row = cur.fetchone()
        except psycopg.Error as exc:
            raise ExternalServiceError(
                "Error al consultar el documento en la base de datos."
            ) from exc

        return self._row_to_document(row) if row is not None else None

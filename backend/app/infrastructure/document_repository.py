from typing import Any
from uuid import UUID

import psycopg

from app.domain.exceptions import DocumentNotFoundError, ExternalServiceError, SyllabusBusyError
from app.domain.models import SyllabusDocument, SyllabusStatus, UploadReservation
from app.infrastructure.db import get_db_connection
from app.infrastructure.extraction_repository import _EXECUTION_COLUMNS, PostgresExtractionRepository
from app.infrastructure.syllabus_course_lock import (
    ACTIVE_EXTRACTION,
    ACTIVE_UPLOAD,
    require_course,
    require_idle_syllabus,
)

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

    @staticmethod
    def _row_to_upload(row: dict[str, Any]) -> UploadReservation:
        return UploadReservation(
            upload_id=row["id"],
            filename=row["filename"],
            expires_at=row["expires_at"],
            status=row["status"],
        )

    def reserve_upload(
        self, owner_id: UUID, course_id: UUID, filename: str
    ) -> UploadReservation:
        try:
            with get_db_connection(self._database_url) as conn, conn.cursor() as cur:
                require_course(cur, owner_id, course_id, lock=True)
                require_idle_syllabus(cur, owner_id, course_id)
                cur.execute(
                    """
                    UPDATE public.syllabus_upload_reservations
                    SET status = 'failed'
                    WHERE owner_id = %s AND course_id = %s
                      AND status IN ('reserved', 'receiving')
                      AND expires_at <= clock_timestamp()
                    """,
                    (owner_id, course_id),
                )
                cur.execute(
                    """
                    INSERT INTO public.syllabus_upload_reservations (owner_id, course_id, filename, status)
                    VALUES (%s, %s, %s, 'reserved')
                    RETURNING id, filename, expires_at, status
                    """,
                    (owner_id, course_id, filename),
                )
                return self._row_to_upload(cur.fetchone())
        except psycopg.Error as exc:
            raise ExternalServiceError("No se pudo reservar la carga del sílabo.") from exc

    def claim_upload(
        self, owner_id: UUID, course_id: UUID, upload_id: UUID, sha256: str
    ) -> tuple[UploadReservation, SyllabusDocument | None]:
        try:
            with get_db_connection(self._database_url) as conn, conn.cursor() as cur:
                require_course(cur, owner_id, course_id, lock=True)
                cur.execute(
                    """
                    SELECT id, filename, expires_at, status, document_id, sha256,
                           expires_at > clock_timestamp() AS live
                    FROM public.syllabus_upload_reservations
                    WHERE id = %s AND owner_id = %s AND course_id = %s
                    """,
                    (upload_id, owner_id, course_id),
                )
                upload = cur.fetchone()
                if upload is None:
                    raise DocumentNotFoundError("Reserva de carga no encontrada.")
                if upload["status"] == "ready" and upload["sha256"] == sha256:
                    cur.execute(
                        f"SELECT {_DOCUMENT_COLUMNS} FROM public.documents "
                        "WHERE id = %s AND owner_id = %s AND course_id = %s",
                        (upload["document_id"], owner_id, course_id),
                    )
                    existing = cur.fetchone()
                    if existing is not None:
                        return self._row_to_upload(upload), self._row_to_document(existing)
                if upload["status"] != "reserved" or not upload["live"]:
                    raise SyllabusBusyError("La reserva ya está en uso o venció. Actualiza el estado de la carga.")

                cur.execute(
                    f"SELECT {_DOCUMENT_COLUMNS} FROM public.documents "
                    "WHERE course_id = %s AND owner_id = %s AND sha256 = %s "
                    "ORDER BY created_at DESC, id DESC LIMIT 1",
                    (course_id, owner_id, sha256),
                )
                existing = cur.fetchone()
                if existing is not None:
                    cur.execute(
                        "UPDATE public.syllabus_upload_reservations "
                        "SET status = 'ready', document_id = %s, sha256 = %s WHERE id = %s",
                        (existing["id"], sha256, upload_id),
                    )
                    return self._row_to_upload(upload), self._row_to_document(existing)
                cur.execute(
                    "UPDATE public.syllabus_upload_reservations SET status = 'receiving', sha256 = %s "
                    "WHERE id = %s RETURNING id, filename, expires_at, status",
                    (sha256, upload_id),
                )
                return self._row_to_upload(cur.fetchone()), None
        except psycopg.Error as exc:
            raise ExternalServiceError("No se pudo registrar el inicio de la transferencia.") from exc

    def finish_upload(
        self,
        upload_id: UUID,
        owner_id: UUID,
        course_id: UUID,
        file_size: int,
        storage_bucket: str,
        storage_path: str,
        sha256: str,
    ) -> SyllabusDocument:
        """Commit the document and complete its still-active reservation together."""
        try:
            with get_db_connection(self._database_url) as conn, conn.cursor() as cur:
                require_course(cur, owner_id, course_id, lock=True)
                cur.execute(
                    """
                    SELECT filename FROM public.syllabus_upload_reservations
                    WHERE id = %s AND owner_id = %s AND course_id = %s
                      AND status = 'receiving' AND sha256 = %s
                      AND expires_at > clock_timestamp()
                    """,
                    (upload_id, owner_id, course_id, sha256),
                )
                upload = cur.fetchone()
                if upload is None:
                    raise SyllabusBusyError("La reserva venció antes de guardar el PDF.")
                cur.execute(
                    f"""
                    INSERT INTO public.documents (
                        id, owner_id, course_id, filename, content_type,
                        file_size, storage_bucket, storage_path, sha256
                    )
                    VALUES (%s, %s, %s, %s, 'application/pdf', %s, %s, %s, %s)
                    RETURNING {_DOCUMENT_COLUMNS}
                    """,
                    (
                        upload_id, owner_id, course_id, upload["filename"],
                        file_size, storage_bucket, storage_path, sha256,
                    ),
                )
                row = cur.fetchone()
                cur.execute(
                    "UPDATE public.syllabus_upload_reservations "
                    "SET status = 'ready', document_id = %s WHERE id = %s",
                    (upload_id, upload_id),
                )
                return self._row_to_document(row)
        except psycopg.Error as exc:
            raise ExternalServiceError(
                "Error al guardar el documento en la base de datos."
            ) from exc

    def fail_upload(
        self, owner_id: UUID, course_id: UUID, upload_id: UUID, *, receiving: bool
    ) -> bool:
        try:
            with get_db_connection(self._database_url) as conn, conn.cursor() as cur:
                require_course(cur, owner_id, course_id, lock=True)
                expected = ("receiving", "failed") if receiving else ("reserved", "failed")
                cur.execute(
                    """
                    UPDATE public.syllabus_upload_reservations SET status = 'failed'
                    WHERE id = %s AND owner_id = %s AND course_id = %s
                      AND status IN (%s, %s) AND document_id IS NULL
                    RETURNING id
                    """,
                    (upload_id, owner_id, course_id, *expected),
                )
                return cur.fetchone() is not None
        except psycopg.Error as exc:
            raise ExternalServiceError("No se pudo liberar la reserva de carga.") from exc

    def get_syllabus_status(
        self, owner_id: UUID, course_id: UUID, document_id: UUID | None
    ) -> SyllabusStatus:
        try:
            with get_db_connection(self._database_url) as conn, conn.cursor() as cur:
                cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                require_course(cur, owner_id, course_id)
                cur.execute(
                    "SELECT id, filename, expires_at, status FROM public.syllabus_upload_reservations "
                    f"WHERE owner_id = %s AND course_id = %s AND {ACTIVE_UPLOAD}",
                    (owner_id, course_id),
                )
                upload = cur.fetchone()
                cur.execute(
                    f"SELECT {_EXECUTION_COLUMNS} FROM public.extraction_executions "
                    f"WHERE owner_id = %s AND course_id = %s AND {ACTIVE_EXTRACTION} "
                    "ORDER BY created_at DESC, id DESC LIMIT 1",
                    (owner_id, course_id),
                )
                active_execution = cur.fetchone()
                selected_id = document_id
                if selected_id is None and active_execution is not None:
                    selected_id = active_execution["document_id"]
                if selected_id is not None:
                    cur.execute(
                        f"SELECT {_DOCUMENT_COLUMNS} FROM public.documents "
                        "WHERE owner_id = %s AND course_id = %s AND id = %s",
                        (owner_id, course_id, selected_id),
                    )
                    document = cur.fetchone()
                    if document is None:
                        raise DocumentNotFoundError("Documento no encontrado.")
                else:
                    cur.execute(
                        f"""
                        SELECT {_DOCUMENT_COLUMNS} FROM public.documents
                        WHERE owner_id = %s AND course_id = %s
                        ORDER BY GREATEST(created_at, (
                            SELECT max(created_at) FROM public.syllabus_upload_reservations
                            WHERE status = 'ready' AND owner_id = %s AND course_id = %s
                              AND document_id = documents.id
                        )) DESC, id DESC LIMIT 1
                        """,
                        (owner_id, course_id, owner_id, course_id),
                    )
                    document = cur.fetchone()
                execution = None
                if document is not None:
                    cur.execute(
                        f"SELECT {_EXECUTION_COLUMNS} FROM public.extraction_executions "
                        "WHERE owner_id = %s AND course_id = %s AND document_id = %s "
                        "ORDER BY created_at DESC, id DESC LIMIT 1",
                        (owner_id, course_id, document["id"]),
                    )
                    execution = cur.fetchone()
                return SyllabusStatus(
                    upload=self._row_to_upload(upload) if upload is not None else None,
                    document=self._row_to_document(document) if document is not None else None,
                    execution=PostgresExtractionRepository._row_to_execution(execution) if execution is not None else None,
                    active_execution=PostgresExtractionRepository._row_to_execution(active_execution) if active_execution is not None else None,
                )
        except psycopg.Error as exc:
            raise ExternalServiceError("No se pudo consultar el estado del sílabo.") from exc

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

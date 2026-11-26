import json
from datetime import date, datetime
from typing import Any
from uuid import UUID

import psycopg

from app.domain.exceptions import ExternalServiceError
from app.domain.models import (
    ExtractedActivity,
    ExtractionConflict,
    ExtractionExecution,
)
from app.infrastructure.db import get_db_connection

_EXECUTION_COLUMNS = (
    "id, owner_id, document_id, course_id, status, model_name, total_pages, "
    "processed_pages, activities_count, conflicts_count, error_message, "
    "worker_id, lease_expires_at, attempt_count, stage, stage_timings, "
    "started_at, completed_at, created_at, updated_at"
)

_ACTIVITY_COLUMNS = (
    "id, owner_id, course_id, document_id, execution_id, title, activity_type, "
    "due_date, due_time, weight_percentage, description, estimated_minutes, due_at, "
    "source_page, evidence_quote, evidence_valid, confidence, review_status, "
    "review_notes, reviewed_at, created_at, updated_at"
)

_CONFLICT_COLUMNS = (
    "id, owner_id, course_id, document_id, execution_id, activity_id, "
    "conflict_type, severity, message, source_page, details, resolved, created_at"
)


class PostgresExtractionRepository:
    """Psycopg repository for owner-scoped extraction runs, activities, and conflicts."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    @staticmethod
    def _row_to_execution(row: dict[str, Any]) -> ExtractionExecution:
        raw_timings = row.get("stage_timings")
        return ExtractionExecution(
            id=row["id"],
            owner_id=row["owner_id"],
            document_id=row["document_id"],
            course_id=row["course_id"],
            status=row["status"],
            model_name=row["model_name"],
            total_pages=row["total_pages"],
            processed_pages=row["processed_pages"],
            activities_count=row["activities_count"],
            conflicts_count=row["conflicts_count"],
            error_message=row["error_message"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            worker_id=row.get("worker_id"),
            lease_expires_at=row.get("lease_expires_at"),
            attempt_count=row.get("attempt_count", 0) or 0,
            stage=row.get("stage"),
            stage_timings=raw_timings if isinstance(raw_timings, dict) else {},
        )

    @staticmethod
    def _row_to_activity(row: dict[str, Any]) -> ExtractedActivity:
        raw_weight = row["weight_percentage"]
        raw_confidence = row["confidence"]
        return ExtractedActivity(
            id=row["id"],
            owner_id=row["owner_id"],
            course_id=row["course_id"],
            document_id=row["document_id"],
            execution_id=row["execution_id"],
            title=row["title"],
            activity_type=row["activity_type"],
            due_date=row["due_date"],
            due_time=row["due_time"],
            weight_percentage=float(raw_weight) if raw_weight is not None else None,
            description=row["description"],
            estimated_minutes=row["estimated_minutes"],
            due_at=row["due_at"],
            source_page=row["source_page"],
            evidence_quote=row["evidence_quote"],
            evidence_valid=row["evidence_valid"],
            confidence=float(raw_confidence) if raw_confidence is not None else None,
            review_status=row["review_status"],
            review_notes=row["review_notes"],
            reviewed_at=row["reviewed_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_conflict(row: dict[str, Any]) -> ExtractionConflict:
        return ExtractionConflict(
            id=row["id"],
            owner_id=row["owner_id"],
            course_id=row["course_id"],
            document_id=row["document_id"],
            execution_id=row["execution_id"],
            activity_id=row["activity_id"],
            conflict_type=row["conflict_type"],
            severity=row["severity"],
            message=row["message"],
            source_page=row["source_page"],
            details=row["details"] if isinstance(row["details"], dict) else {},
            resolved=row["resolved"],
            created_at=row["created_at"],
        )

    def create_execution(
        self,
        owner_id: UUID,
        document_id: UUID,
        course_id: UUID,
        model_name: str,
    ) -> ExtractionExecution:
        """Reuse a live or completed extraction, preserving human reviews."""
        query = f"""
            INSERT INTO public.extraction_executions (
                owner_id,
                document_id,
                course_id,
                status,
                stage,
                model_name
            )
            VALUES (%s, %s, %s, 'pending', 'queued', %s)
            RETURNING {_EXECUTION_COLUMNS}
        """
        try:
            with get_db_connection(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id FROM public.documents WHERE id = %s AND owner_id = %s FOR UPDATE",
                        (document_id, owner_id),
                    )
                    cur.execute(
                        f"SELECT {_EXECUTION_COLUMNS} FROM public.extraction_executions "
                        "WHERE document_id = %s AND owner_id = %s AND status <> 'failed' "
                        "ORDER BY created_at DESC LIMIT 1",
                        (document_id, owner_id),
                    )
                    row = cur.fetchone()
                    if row is None:
                        cur.execute(query, (owner_id, document_id, course_id, model_name))
                        row = cur.fetchone()
        except psycopg.Error as exc:
            raise ExternalServiceError(
                "Error al crear la ejecución de extracción."
            ) from exc

        if row is None:
            raise ExternalServiceError("No se obtuvo la ejecución creada.")
        return self._row_to_execution(row)

    def get_execution_for_owner(
        self, execution_id: UUID, owner_id: UUID
    ) -> ExtractionExecution | None:
        """Fetch an execution by id and owner_id."""
        query = f"""
            SELECT {_EXECUTION_COLUMNS}
            FROM public.extraction_executions
            WHERE id = %s AND owner_id = %s
        """
        try:
            with get_db_connection(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (execution_id, owner_id))
                    row = cur.fetchone()
        except psycopg.Error as exc:
            raise ExternalServiceError(
                "Error al consultar el estado de la extracción."
            ) from exc

        return self._row_to_execution(row) if row is not None else None

    def mark_execution_running(self, execution_id: UUID, owner_id: UUID) -> None:
        """Mark an owner-scoped execution as running."""
        query = """
            UPDATE public.extraction_executions
            SET status = 'running',
                stage = COALESCE(stage, 'running'),
                started_at = COALESCE(started_at, now()),
                error_message = NULL,
                updated_at = now()
            WHERE id = %s AND owner_id = %s
        """
        try:
            with get_db_connection(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (execution_id, owner_id))
        except psycopg.Error as exc:
            raise ExternalServiceError(
                "Error al actualizar la ejecución a running."
            ) from exc

    def claim_next_extraction_execution(
        self,
        worker_id: str,
        lease_seconds: int,
        max_attempts: int = 3,
    ) -> ExtractionExecution | None:
        """Atomically claim the next pending or expired extraction execution."""
        query = f"""
            WITH candidate AS (
                SELECT id
                FROM public.extraction_executions
                WHERE (
                    status = 'pending'
                    OR (
                        status = 'running'
                        AND lease_expires_at IS NOT NULL
                        AND lease_expires_at < now()
                    )
                )
                  AND attempt_count < %s
                ORDER BY created_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE public.extraction_executions AS e
            SET status = 'running',
                worker_id = %s,
                lease_expires_at = now() + (%s * interval '1 second'),
                attempt_count = e.attempt_count + 1,
                stage = 'claimed',
                started_at = COALESCE(e.started_at, now()),
                error_message = NULL,
                updated_at = now()
            FROM candidate
            WHERE e.id = candidate.id
            RETURNING e.id, e.owner_id, e.document_id, e.course_id, e.status,
                      e.model_name, e.total_pages, e.processed_pages,
                      e.activities_count, e.conflicts_count, e.error_message,
                      e.worker_id, e.lease_expires_at, e.attempt_count,
                      e.stage, e.stage_timings, e.started_at, e.completed_at,
                      e.created_at, e.updated_at
        """
        try:
            with get_db_connection(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (max_attempts, worker_id, lease_seconds))
                    row = cur.fetchone()
        except psycopg.Error as exc:
            raise ExternalServiceError(
                "Error al reclamar la siguiente ejecución de extracción."
            ) from exc
        return self._row_to_execution(row) if row is not None else None

    def fail_exhausted_extraction_executions(self, max_attempts: int = 3) -> int:
        """Mark expired extraction executions that reached max_attempts as failed."""
        query = """
            UPDATE public.extraction_executions
            SET status = 'failed',
                stage = 'failed',
                lease_expires_at = NULL,
                error_message = 'La ejecución superó el tiempo límite y el máximo de reintentos.',
                completed_at = now(),
                updated_at = now()
            WHERE status = 'running'
              AND lease_expires_at IS NOT NULL
              AND lease_expires_at < now()
              AND attempt_count >= %s
        """
        try:
            with get_db_connection(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (max_attempts,))
                    return cur.rowcount or 0
        except psycopg.Error as exc:
            raise ExternalServiceError(
                "Error al cerrar ejecuciones de extracción expiradas."
            ) from exc

    def update_execution_stage(
        self,
        execution_id: UUID,
        owner_id: UUID,
        stage: str,
        stage_timings: dict[str, Any],
        worker_id: str | None = None,
    ) -> None:
        """Update current stage and accumulated timings for an extraction execution."""
        clauses = ["id = %s", "owner_id = %s"]
        params: list[Any] = [stage, json.dumps(stage_timings), execution_id, owner_id]
        if worker_id is not None:
            clauses.append("worker_id = %s")
            params.append(worker_id)

        query = f"""
            UPDATE public.extraction_executions
            SET stage = %s,
                stage_timings = %s::jsonb,
                updated_at = now()
            WHERE {" AND ".join(clauses)}
        """
        try:
            with get_db_connection(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(query, tuple(params))
        except psycopg.Error as exc:
            raise ExternalServiceError(
                "Error al registrar la etapa de la extracción."
            ) from exc

    def mark_execution_completed(
        self,
        execution_id: UUID,
        owner_id: UUID,
        total_pages: int,
        processed_pages: int,
        activities_count: int,
        conflicts_count: int,
        stage_timings: dict[str, Any] | None = None,
        worker_id: str | None = None,
    ) -> None:
        """Mark an owner-scoped execution as completed with summary counts."""
        set_clauses = [
            "status = 'completed'",
            "stage = 'completed'",
            "lease_expires_at = NULL",
            "total_pages = %s",
            "processed_pages = %s",
            "activities_count = %s",
            "conflicts_count = %s",
            "completed_at = now()",
            "updated_at = now()",
        ]
        params: list[Any] = [
            total_pages,
            processed_pages,
            activities_count,
            conflicts_count,
        ]
        if stage_timings is not None:
            set_clauses.append("stage_timings = %s::jsonb")
            params.append(json.dumps(stage_timings))

        where_clauses = ["id = %s", "owner_id = %s"]
        params.extend([execution_id, owner_id])
        if worker_id is not None:
            where_clauses.append("worker_id = %s")
            params.append(worker_id)

        query = f"""
            UPDATE public.extraction_executions
            SET {", ".join(set_clauses)}
            WHERE {" AND ".join(where_clauses)}
        """
        try:
            with get_db_connection(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(query, tuple(params))
        except psycopg.Error as exc:
            raise ExternalServiceError(
                "Error al marcar la ejecución como completada."
            ) from exc

    def mark_execution_failed(
        self,
        execution_id: UUID,
        owner_id: UUID,
        error_message: str,
        stage_timings: dict[str, Any] | None = None,
        worker_id: str | None = None,
    ) -> None:
        """Mark an owner-scoped execution as failed with an error message."""
        set_clauses = [
            "status = 'failed'",
            "stage = 'failed'",
            "lease_expires_at = NULL",
            "error_message = %s",
            "completed_at = now()",
            "updated_at = now()",
        ]
        params: list[Any] = [error_message[:2000]]
        if stage_timings is not None:
            set_clauses.append("stage_timings = %s::jsonb")
            params.append(json.dumps(stage_timings))

        where_clauses = ["id = %s", "owner_id = %s"]
        params.extend([execution_id, owner_id])
        if worker_id is not None:
            where_clauses.append("worker_id = %s")
            params.append(worker_id)

        query = f"""
            UPDATE public.extraction_executions
            SET {", ".join(set_clauses)}
            WHERE {" AND ".join(where_clauses)}
        """
        try:
            with get_db_connection(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(query, tuple(params))
        except psycopg.Error as exc:
            raise ExternalServiceError(
                "Error al marcar la ejecución como fallida."
            ) from exc

    def replace_document_extraction_results(
        self,
        owner_id: UUID,
        course_id: UUID,
        document_id: UUID,
        execution_id: UUID,
        activities: list[dict[str, Any]],
        conflicts: list[dict[str, Any]],
    ) -> tuple[int, int]:
        """Atomically replace previous activities/conflicts for a document and insert new ones."""
        try:
            with get_db_connection(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        DELETE FROM public.extraction_conflicts
                        WHERE document_id = %s AND owner_id = %s AND execution_id = %s
                        """,
                        (document_id, owner_id, execution_id),
                    )
                    cur.execute(
                        """
                        DELETE FROM public.activities
                        WHERE document_id = %s AND owner_id = %s AND execution_id = %s
                        """,
                        (document_id, owner_id, execution_id),
                    )

                    inserted_activity_ids: list[UUID | None] = []
                    for item in activities:
                        cur.execute(
                            """
                            INSERT INTO public.activities (
                                owner_id,
                                course_id,
                                document_id,
                                execution_id,
                                title,
                                activity_type,
                                due_date,
                                due_time,
                                weight_percentage,
                                description,
                                source_page,
                                evidence_quote,
                                evidence_valid,
                                confidence
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            RETURNING id
                            """,
                            (
                                owner_id,
                                course_id,
                                document_id,
                                execution_id,
                                item["title"],
                                item["activity_type"],
                                item.get("due_date"),
                                item.get("due_time"),
                                item.get("weight_percentage"),
                                item.get("description"),
                                item["source_page"],
                                item["evidence_quote"],
                                item["evidence_valid"],
                                item.get("confidence"),
                            ),
                        )
                        row = cur.fetchone()
                        inserted_activity_ids.append(row["id"] if row else None)

                    for conflict in conflicts:
                        activity_idx = conflict.get("activity_index")
                        activity_id = (
                            inserted_activity_ids[activity_idx]
                            if isinstance(activity_idx, int)
                            and 0 <= activity_idx < len(inserted_activity_ids)
                            else None
                        )
                        cur.execute(
                            """
                            INSERT INTO public.extraction_conflicts (
                                owner_id,
                                course_id,
                                document_id,
                                execution_id,
                                activity_id,
                                conflict_type,
                                severity,
                                message,
                                source_page,
                                details
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                            """,
                            (
                                owner_id,
                                course_id,
                                document_id,
                                execution_id,
                                activity_id,
                                conflict["conflict_type"],
                                conflict.get("severity", "warning"),
                                conflict["message"],
                                conflict.get("source_page"),
                                json.dumps(conflict.get("details") or {}),
                            ),
                        )
        except psycopg.Error as exc:
            raise ExternalServiceError(
                "Error al guardar actividades y conflictos extraídos."
            ) from exc

        return len(activities), len(conflicts)

    def list_activities_by_document_for_owner(
        self, document_id: UUID, owner_id: UUID
    ) -> list[ExtractedActivity]:
        """List extracted activities for a document belonging to owner_id."""
        query = f"""
            SELECT {_ACTIVITY_COLUMNS}
            FROM public.activities
            WHERE document_id = %s AND owner_id = %s
            ORDER BY source_page ASC, due_date ASC NULLS LAST, created_at ASC
        """
        try:
            with get_db_connection(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (document_id, owner_id))
                    rows = cur.fetchall()
        except psycopg.Error as exc:
            raise ExternalServiceError(
                "Error al consultar las actividades del documento."
            ) from exc

        return [self._row_to_activity(row) for row in rows]

    def list_conflicts_by_document_for_owner(
        self, document_id: UUID, owner_id: UUID
    ) -> list[ExtractionConflict]:
        """List extraction conflicts for a document belonging to owner_id."""
        query = f"""
            SELECT {_CONFLICT_COLUMNS}
            FROM public.extraction_conflicts
            WHERE document_id = %s AND owner_id = %s
            ORDER BY created_at ASC
        """
        try:
            with get_db_connection(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (document_id, owner_id))
                    rows = cur.fetchall()
        except psycopg.Error as exc:
            raise ExternalServiceError(
                "Error al consultar los conflictos de extracción."
            ) from exc

        return [self._row_to_conflict(row) for row in rows]

    def get_activity_for_owner(
        self, activity_id: UUID, owner_id: UUID
    ) -> ExtractedActivity | None:
        """Fetch a single activity belonging to owner_id."""
        query = f"""
            SELECT {_ACTIVITY_COLUMNS}
            FROM public.activities
            WHERE id = %s AND owner_id = %s
        """
        try:
            with get_db_connection(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (activity_id, owner_id))
                    row = cur.fetchone()
        except psycopg.Error as exc:
            raise ExternalServiceError(
                "Error al consultar la actividad en la base de datos."
            ) from exc

        return self._row_to_activity(row) if row is not None else None

    def update_activity_review_for_owner(
        self,
        activity_id: UUID,
        owner_id: UUID,
        review_status: str,
        title: str | None = None,
        activity_type: str | None = None,
        due_date: date | None = None,
        clear_due_date: bool = False,
        due_time: str | None = None,
        weight_percentage: float | None = None,
        clear_weight: bool = False,
        description: str | None = None,
        review_notes: str | None = None,
        estimated_minutes: int | None = None,
        clear_estimated_minutes: bool = False,
        due_at: datetime | None = None,
        clear_due_at: bool = False,
    ) -> ExtractedActivity | None:
        """Update review metadata and optional fields for an owner-scoped activity."""
        set_clauses: list[str] = [
            "review_status = %s",
            "reviewed_at = now()",
        ]
        params: list[Any] = [review_status]

        if title is not None:
            set_clauses.append("title = %s")
            params.append(title)
        if activity_type is not None:
            set_clauses.append("activity_type = %s")
            params.append(activity_type)
        if clear_due_date:
            set_clauses.append("due_date = NULL")
        elif due_date is not None:
            set_clauses.append("due_date = %s")
            params.append(due_date)
        if due_time is not None:
            set_clauses.append("due_time = %s")
            params.append(due_time)
        if clear_weight:
            set_clauses.append("weight_percentage = NULL")
        elif weight_percentage is not None:
            set_clauses.append("weight_percentage = %s")
            params.append(weight_percentage)
        if description is not None:
            set_clauses.append("description = %s")
            params.append(description)
        if review_notes is not None:
            set_clauses.append("review_notes = %s")
            params.append(review_notes)
        if clear_estimated_minutes:
            set_clauses.append("estimated_minutes = NULL")
        elif estimated_minutes is not None:
            set_clauses.append("estimated_minutes = %s")
            params.append(estimated_minutes)
        if clear_due_at:
            set_clauses.append("due_at = NULL")
        elif due_at is not None:
            set_clauses.append("due_at = %s")
            params.append(due_at)

        params.extend([activity_id, owner_id])
        query = f"""
            UPDATE public.activities
            SET {", ".join(set_clauses)}
            WHERE id = %s AND owner_id = %s
            RETURNING {_ACTIVITY_COLUMNS}
        """

        try:
            with get_db_connection(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(query, tuple(params))
                    row = cur.fetchone()
        except psycopg.Error as exc:
            raise ExternalServiceError(
                "Error al actualizar la revisión de la actividad."
            ) from exc

        return self._row_to_activity(row) if row is not None else None

import json
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg

from app.domain.exceptions import ExternalServiceError
from app.domain.models import (
    AvailabilityWindow,
    ExtractedActivity,
    PlanBlock,
    PlanPendingActivity,
    PlanningExecution,
    StudyPlan,
)
from app.domain.planning_rules import StudyBlock, StudyWindow
from app.infrastructure.db import get_db_connection
from app.infrastructure.extraction_repository import PostgresExtractionRepository

_AVAILABILITY_COLUMNS = (
    "id, owner_id, start_at, end_at, created_at, updated_at"
)

_PLANNING_EXECUTION_COLUMNS = (
    "id, owner_id, course_id, status, model_name, horizon_start, horizon_end, plan_id, "
    "activities_count, blocks_count, pending_count, error_message, "
    "worker_id, lease_expires_at, attempt_count, stage, stage_timings, "
    "started_at, completed_at, created_at, updated_at"
)

_ACTIVITY_COLUMNS = (
    "id, owner_id, course_id, document_id, execution_id, title, activity_type, "
    "due_date, due_time, weight_percentage, description, estimated_minutes, due_at, "
    "source_page, evidence_quote, evidence_valid, confidence, review_status, "
    "review_notes, reviewed_at, created_at, updated_at"
)


class PostgresPlanningRepository:
    """Psycopg repository for owner-scoped availability, planning runs, and study plans."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    @staticmethod
    def _row_to_availability(row: dict[str, Any]) -> AvailabilityWindow:
        return AvailabilityWindow(
            id=row["id"],
            owner_id=row["owner_id"],
            start_at=row["start_at"],
            end_at=row["end_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_execution(row: dict[str, Any]) -> PlanningExecution:
        raw_timings = row.get("stage_timings")
        return PlanningExecution(
            id=row["id"],
            owner_id=row["owner_id"],
            course_id=row.get("course_id"),
            status=row["status"],
            model_name=row["model_name"],
            horizon_start=row["horizon_start"],
            horizon_end=row["horizon_end"],
            plan_id=row["plan_id"],
            activities_count=row["activities_count"],
            blocks_count=row["blocks_count"],
            pending_count=row["pending_count"],
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
    def _row_to_block(row: dict[str, Any]) -> PlanBlock:
        return PlanBlock(
            id=row["id"],
            owner_id=row["owner_id"],
            plan_id=row["plan_id"],
            activity_id=row["activity_id"],
            activity_title=row.get("activity_title"),
            start_at=row["start_at"],
            end_at=row["end_at"],
            duration_minutes=row["duration_minutes"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_pending(row: dict[str, Any]) -> PlanPendingActivity:
        return PlanPendingActivity(
            id=row["id"],
            owner_id=row["owner_id"],
            plan_id=row["plan_id"],
            activity_id=row["activity_id"],
            activity_title=row.get("activity_title"),
            reason=row["reason"],
            created_at=row["created_at"],
        )

    def replace_availability_for_owner(
        self, owner_id: UUID, windows: list[StudyWindow]
    ) -> list[AvailabilityWindow]:
        """Atomically replace all availability windows for owner_id."""
        sorted_windows = sorted(windows, key=lambda w: w.start)
        saved: list[AvailabilityWindow] = []
        try:
            with get_db_connection(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM public.availability_windows WHERE owner_id = %s",
                        (owner_id,),
                    )
                    for window in sorted_windows:
                        cur.execute(
                            f"""
                            INSERT INTO public.availability_windows (
                                owner_id,
                                start_at,
                                end_at
                            )
                            VALUES (%s, %s, %s)
                            RETURNING {_AVAILABILITY_COLUMNS}
                            """,
                            (owner_id, window.start, window.end),
                        )
                        row = cur.fetchone()
                        if row is not None:
                            saved.append(self._row_to_availability(row))
        except psycopg.Error as exc:
            raise ExternalServiceError(
                "Error al guardar la disponibilidad en la base de datos."
            ) from exc
        return saved

    def list_availability_for_owner(
        self, owner_id: UUID
    ) -> list[AvailabilityWindow]:
        """List all study availability windows for owner_id ordered by start_at."""
        query = f"""
            SELECT {_AVAILABILITY_COLUMNS}
            FROM public.availability_windows
            WHERE owner_id = %s
            ORDER BY start_at ASC
        """
        try:
            with get_db_connection(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (owner_id,))
                    rows = cur.fetchall()
        except psycopg.Error as exc:
            raise ExternalServiceError(
                "Error al consultar la disponibilidad en la base de datos."
            ) from exc
        return [self._row_to_availability(row) for row in rows]

    def list_plannable_activities_for_owner(
        self, owner_id: UUID, course_id: UUID, horizon_start: datetime
    ) -> list[ExtractedActivity]:
        """List approved/edited activities for course_id with human estimate and timezone-aware due_at."""
        query = f"""
            SELECT {_ACTIVITY_COLUMNS}
            FROM public.activities
            WHERE owner_id = %s
              AND course_id = %s
              AND review_status IN ('approved', 'edited')
              AND estimated_minutes IS NOT NULL
              AND estimated_minutes > 0
              AND due_at IS NOT NULL
              AND due_at > %s
            ORDER BY due_at ASC, created_at ASC
        """
        try:
            with get_db_connection(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (owner_id, course_id, horizon_start))
                    rows = cur.fetchall()
        except psycopg.Error as exc:
            raise ExternalServiceError(
                "Error al consultar las actividades planificables."
            ) from exc
        return [PostgresExtractionRepository._row_to_activity(row) for row in rows]

    def create_planning_execution(
        self,
        owner_id: UUID,
        course_id: UUID,
        horizon_start: datetime,
        horizon_end: datetime,
        model_name: str,
    ) -> PlanningExecution:
        """Insert a pending planning execution row."""
        query = f"""
            INSERT INTO public.planning_executions (
                owner_id,
                course_id,
                status,
                stage,
                model_name,
                horizon_start,
                horizon_end
            )
            VALUES (%s, %s, 'pending', 'queued', %s, %s, %s)
            RETURNING {_PLANNING_EXECUTION_COLUMNS}
        """
        try:
            with get_db_connection(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        query,
                        (owner_id, course_id, model_name, horizon_start, horizon_end),
                    )
                    row = cur.fetchone()
        except psycopg.Error as exc:
            raise ExternalServiceError(
                "Error al crear la ejecución de planificación."
            ) from exc

        if row is None:
            raise ExternalServiceError("No se obtuvo la ejecución de planificación creada.")
        return self._row_to_execution(row)

    def get_planning_execution_for_owner(
        self, execution_id: UUID, owner_id: UUID
    ) -> PlanningExecution | None:
        """Fetch a planning execution by id and owner_id."""
        query = f"""
            SELECT {_PLANNING_EXECUTION_COLUMNS}
            FROM public.planning_executions
            WHERE id = %s AND owner_id = %s
        """
        try:
            with get_db_connection(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (execution_id, owner_id))
                    row = cur.fetchone()
        except psycopg.Error as exc:
            raise ExternalServiceError(
                "Error al consultar la ejecución de planificación."
            ) from exc
        return self._row_to_execution(row) if row is not None else None

    def mark_planning_execution_running(
        self, execution_id: UUID, owner_id: UUID
    ) -> None:
        """Mark an owner-scoped planning execution as running."""
        query = """
            UPDATE public.planning_executions
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
                "Error al actualizar la planificación a running."
            ) from exc

    def claim_next_planning_execution(
        self,
        worker_id: str,
        lease_seconds: int,
        max_attempts: int = 3,
    ) -> PlanningExecution | None:
        """Atomically claim the next pending or expired planning execution."""
        query = """
            WITH candidate AS (
                SELECT id
                FROM public.planning_executions
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
            UPDATE public.planning_executions AS p
            SET status = 'running',
                worker_id = %s,
                lease_expires_at = now() + (%s * interval '1 second'),
                attempt_count = p.attempt_count + 1,
                stage = 'claimed',
                started_at = COALESCE(p.started_at, now()),
                error_message = NULL,
                updated_at = now()
            FROM candidate
            WHERE p.id = candidate.id
            RETURNING p.id, p.owner_id, p.course_id, p.status, p.model_name,
                      p.horizon_start, p.horizon_end, p.plan_id,
                      p.activities_count, p.blocks_count, p.pending_count,
                      p.error_message, p.worker_id, p.lease_expires_at,
                      p.attempt_count, p.stage, p.stage_timings,
                      p.started_at, p.completed_at, p.created_at, p.updated_at
        """
        try:
            with get_db_connection(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (max_attempts, worker_id, lease_seconds))
                    row = cur.fetchone()
        except psycopg.Error as exc:
            raise ExternalServiceError(
                "Error al reclamar la siguiente ejecución de planificación."
            ) from exc
        return self._row_to_execution(row) if row is not None else None

    def fail_exhausted_planning_executions(self, max_attempts: int = 3) -> int:
        """Mark expired planning executions that reached max_attempts as failed."""
        query = """
            UPDATE public.planning_executions
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
                "Error al cerrar ejecuciones de planificación expiradas."
            ) from exc

    def update_planning_stage(
        self,
        execution_id: UUID,
        owner_id: UUID,
        stage: str,
        stage_timings: dict[str, Any],
        worker_id: str | None = None,
    ) -> None:
        """Update current stage and accumulated timings for a planning execution."""
        clauses = ["id = %s", "owner_id = %s"]
        params: list[Any] = [stage, json.dumps(stage_timings), execution_id, owner_id]
        if worker_id is not None:
            clauses.append("worker_id = %s")
            params.append(worker_id)

        query = f"""
            UPDATE public.planning_executions
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
                "Error al registrar la etapa de la planificación."
            ) from exc

    def mark_planning_execution_completed(
        self,
        execution_id: UUID,
        owner_id: UUID,
        plan_id: UUID,
        activities_count: int,
        blocks_count: int,
        pending_count: int,
        stage_timings: dict[str, Any] | None = None,
        worker_id: str | None = None,
    ) -> None:
        """Mark an owner-scoped planning execution as completed."""
        set_clauses = [
            "status = 'completed'",
            "stage = 'completed'",
            "lease_expires_at = NULL",
            "plan_id = %s",
            "activities_count = %s",
            "blocks_count = %s",
            "pending_count = %s",
            "completed_at = now()",
            "updated_at = now()",
        ]
        params: list[Any] = [
            plan_id,
            activities_count,
            blocks_count,
            pending_count,
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
            UPDATE public.planning_executions
            SET {", ".join(set_clauses)}
            WHERE {" AND ".join(where_clauses)}
        """
        try:
            with get_db_connection(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(query, tuple(params))
        except psycopg.Error as exc:
            raise ExternalServiceError(
                "Error al marcar la planificación como completada."
            ) from exc

    def mark_planning_execution_failed(
        self,
        execution_id: UUID,
        owner_id: UUID,
        error_message: str,
        stage_timings: dict[str, Any] | None = None,
        worker_id: str | None = None,
    ) -> None:
        """Mark an owner-scoped planning execution as failed."""
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
            UPDATE public.planning_executions
            SET {", ".join(set_clauses)}
            WHERE {" AND ".join(where_clauses)}
        """
        try:
            with get_db_connection(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(query, tuple(params))
        except psycopg.Error as exc:
            raise ExternalServiceError(
                "Error al marcar la planificación como fallida."
            ) from exc

    def create_study_plan(
        self,
        owner_id: UUID,
        course_id: UUID,
        execution_id: UUID,
        horizon: StudyWindow,
        model_name: str,
        planner_summary: str | None,
        availability_snapshot: list[dict[str, Any]],
        activities_snapshot: list[dict[str, Any]],
        blocks: list[StudyBlock],
        pending: dict[UUID, str],
    ) -> StudyPlan:
        """Persist a traceable study plan, its accepted blocks, and pending activities."""
        try:
            with get_db_connection(self._database_url) as conn:
                with conn.cursor() as cur:
                    # Idempotency on expired-lease recovery: replace any partial/prior plan for execution_id
                    cur.execute(
                        """
                        DELETE FROM public.study_plans
                        WHERE execution_id = %s AND owner_id = %s
                        """,
                        (execution_id, owner_id),
                    )
                    cur.execute(
                        """
                        INSERT INTO public.study_plans (
                            owner_id,
                            course_id,
                            execution_id,
                            horizon_start,
                            horizon_end,
                            model_name,
                            planner_summary,
                            availability_snapshot,
                            activities_snapshot
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
                        RETURNING id, owner_id, course_id, execution_id, horizon_start, horizon_end,
                                  model_name, planner_summary, created_at
                        """,
                        (
                            owner_id,
                            course_id,
                            execution_id,
                            horizon.start,
                            horizon.end,
                            model_name,
                            planner_summary,
                            json.dumps(availability_snapshot),
                            json.dumps(activities_snapshot),
                        ),
                    )
                    plan_row = cur.fetchone()
                    if plan_row is None:
                        raise ExternalServiceError("No se pudo crear el plan de estudio.")
                    plan_id = plan_row["id"]

                    for block in blocks:
                        duration_minutes = max(
                            1,
                            round((block.window.end - block.window.start).total_seconds() / 60),
                        )
                        cur.execute(
                            """
                            INSERT INTO public.study_blocks (
                                owner_id,
                                plan_id,
                                activity_id,
                                start_at,
                                end_at,
                                duration_minutes
                            )
                            VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                            (
                                owner_id,
                                plan_id,
                                block.activity_id,
                                block.window.start,
                                block.window.end,
                                duration_minutes,
                            ),
                        )

                    for activity_id, reason in pending.items():
                        cur.execute(
                            """
                            INSERT INTO public.plan_pending_activities (
                                owner_id,
                                plan_id,
                                activity_id,
                                reason
                            )
                            VALUES (%s, %s, %s, %s)
                            """,
                            (owner_id, plan_id, activity_id, reason),
                        )
        except psycopg.Error as exc:
            raise ExternalServiceError(
                "Error al guardar el plan de estudio y sus bloques."
            ) from exc

        persisted = self.get_study_plan_for_owner(plan_id=plan_id, owner_id=owner_id)
        if persisted is None:
            raise ExternalServiceError("No se pudo recuperar el plan de estudio creado.")
        return persisted

    def get_study_plan_for_owner(
        self, plan_id: UUID, owner_id: UUID, course_id: UUID | None = None
    ) -> StudyPlan | None:
        """Fetch a study plan with its blocks and pending activities for owner_id."""
        try:
            with get_db_connection(self._database_url) as conn:
                with conn.cursor() as cur:
                    if course_id is not None:
                        cur.execute(
                            """
                            SELECT id, owner_id, course_id, execution_id, horizon_start, horizon_end,
                                   model_name, planner_summary, created_at
                            FROM public.study_plans
                            WHERE id = %s AND owner_id = %s AND course_id = %s
                            """,
                            (plan_id, owner_id, course_id),
                        )
                    else:
                        cur.execute(
                            """
                            SELECT id, owner_id, course_id, execution_id, horizon_start, horizon_end,
                                   model_name, planner_summary, created_at
                            FROM public.study_plans
                            WHERE id = %s AND owner_id = %s
                            """,
                            (plan_id, owner_id),
                        )
                    plan_row = cur.fetchone()
                    if plan_row is None:
                        return None

                    plan_course_id = plan_row.get("course_id")
                    if plan_course_id is not None:
                        cur.execute(
                            """
                            SELECT b.id, b.owner_id, b.plan_id, b.activity_id,
                                   a.title AS activity_title,
                                   b.start_at, b.end_at, b.duration_minutes, b.created_at
                            FROM public.study_blocks b
                            JOIN public.activities a
                              ON a.id = b.activity_id
                             AND a.owner_id = b.owner_id
                             AND a.course_id = %s
                            WHERE b.plan_id = %s AND b.owner_id = %s
                            ORDER BY b.start_at ASC
                            """,
                            (plan_course_id, plan_id, owner_id),
                        )
                    else:
                        cur.execute(
                            """
                            SELECT b.id, b.owner_id, b.plan_id, b.activity_id,
                                   a.title AS activity_title,
                                   b.start_at, b.end_at, b.duration_minutes, b.created_at
                            FROM public.study_blocks b
                            LEFT JOIN public.activities a ON a.id = b.activity_id
                            WHERE b.plan_id = %s AND b.owner_id = %s
                            ORDER BY b.start_at ASC
                            """,
                            (plan_id, owner_id),
                        )
                    block_rows = cur.fetchall()

                    if plan_course_id is not None:
                        cur.execute(
                            """
                            SELECT p.id, p.owner_id, p.plan_id, p.activity_id,
                                   a.title AS activity_title,
                                   p.reason, p.created_at
                            FROM public.plan_pending_activities p
                            JOIN public.activities a
                              ON a.id = p.activity_id
                             AND a.owner_id = p.owner_id
                             AND a.course_id = %s
                            WHERE p.plan_id = %s AND p.owner_id = %s
                            ORDER BY p.created_at ASC
                            """,
                            (plan_course_id, plan_id, owner_id),
                        )
                    else:
                        cur.execute(
                            """
                            SELECT p.id, p.owner_id, p.plan_id, p.activity_id,
                                   a.title AS activity_title,
                                   p.reason, p.created_at
                            FROM public.plan_pending_activities p
                            LEFT JOIN public.activities a ON a.id = p.activity_id
                            WHERE p.plan_id = %s AND p.owner_id = %s
                            ORDER BY p.created_at ASC
                            """,
                            (plan_id, owner_id),
                        )
                    pending_rows = cur.fetchall()
        except psycopg.Error as exc:
            raise ExternalServiceError(
                "Error al consultar el plan de estudio."
            ) from exc

        return StudyPlan(
            id=plan_row["id"],
            owner_id=plan_row["owner_id"],
            course_id=plan_row.get("course_id"),
            execution_id=plan_row["execution_id"],
            horizon_start=plan_row["horizon_start"],
            horizon_end=plan_row["horizon_end"],
            model_name=plan_row["model_name"],
            planner_summary=plan_row["planner_summary"],
            blocks=[self._row_to_block(row) for row in block_rows],
            pending_activities=[self._row_to_pending(row) for row in pending_rows],
            created_at=plan_row["created_at"],
        )

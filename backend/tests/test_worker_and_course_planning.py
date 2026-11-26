import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.application.extraction_service import ExtractionService
from app.application.planning_service import PlanningService
from app.domain.exceptions import (
    ConfigurationError,
    CourseNotFoundError,
    ExternalServiceError,
    PlanNotFoundError,
)
from app.domain.models import Course, ExtractionExecution, PlanningExecution, StudyPlan
from app.infrastructure.config import get_worker_config
from app.worker import DurableWorker


class CoursePlanningAndWorkerTest(unittest.TestCase):
    def test_start_planning_run_rejects_foreign_course_with_404_error(self):
        planning_repo = MagicMock()
        course_repo = MagicMock()
        course_repo.get_by_id_for_owner.return_value = None
        pipeline = MagicMock()

        service = PlanningService(
            planning_repository=planning_repo,
            course_repository=course_repo,
            pipeline=pipeline,
            model_name="test-model",
        )
        now = datetime(2026, 11, 26, 10, tzinfo=timezone.utc)
        with self.assertRaises(CourseNotFoundError):
            service.start_planning_run(
                owner_id=uuid4(),
                course_id=uuid4(),
                horizon_start=now,
                horizon_end=now + timedelta(days=3),
            )
        planning_repo.create_planning_execution.assert_not_called()

    def test_get_plan_rejects_foreign_course_or_missing_plan(self):
        planning_repo = MagicMock()
        course_repo = MagicMock()
        course_repo.get_by_id_for_owner.return_value = None
        service = PlanningService(
            planning_repository=planning_repo,
            course_repository=course_repo,
            pipeline=MagicMock(),
            model_name="test-model",
        )

        with self.assertRaises(CourseNotFoundError):
            service.get_plan(plan_id=uuid4(), owner_id=uuid4(), course_id=uuid4())

        owner_id = uuid4()
        course_id = uuid4()
        course_repo.get_by_id_for_owner.return_value = Course(
            id=course_id,
            owner_id=owner_id,
            code="CS101",
            name="Arquitectura",
            term=None,
            credits=None,
            description=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        planning_repo.get_study_plan_for_owner.return_value = None
        with self.assertRaises(PlanNotFoundError):
            service.get_plan(plan_id=uuid4(), owner_id=owner_id, course_id=course_id)

    def test_planning_job_sanitizes_provider_errors_and_records_timings(self):
        owner_id = uuid4()
        course_id = uuid4()
        execution_id = uuid4()
        now = datetime(2026, 11, 26, 10, tzinfo=timezone.utc)

        planning_repo = MagicMock()
        planning_repo.list_availability_for_owner.return_value = []
        planning_repo.list_plannable_activities_for_owner.return_value = []

        course_repo = MagicMock()
        course_repo.get_by_id_for_owner.return_value = Course(
            id=course_id,
            owner_id=owner_id,
            code="CS101",
            name="Arquitectura",
            term=None,
            credits=None,
            description=None,
            created_at=now,
            updated_at=now,
        )

        pipeline = MagicMock()
        pipeline.run.side_effect = ExternalServiceError(
            "Groq API error 502: sk-secret-provider-trace"
        )

        service = PlanningService(
            planning_repository=planning_repo,
            course_repository=course_repo,
            pipeline=pipeline,
            model_name="test-model",
        )
        service.run_planning_job(
            execution_id=execution_id,
            owner_id=owner_id,
            course_id=course_id,
            horizon_start=now,
            horizon_end=now + timedelta(days=2),
            worker_id="worker-1",
        )

        planning_repo.list_plannable_activities_for_owner.assert_called_once_with(
            owner_id=owner_id,
            course_id=course_id,
            horizon_start=now,
        )
        failed_call = planning_repo.mark_planning_execution_failed.call_args.kwargs
        self.assertNotIn("sk-secret-provider-trace", failed_call["error_message"])
        self.assertNotIn("Groq API error", failed_call["error_message"])
        self.assertIn("total_ms", failed_call["stage_timings"])
        self.assertEqual(failed_call["worker_id"], "worker-1")

    def test_extraction_job_sanitizes_provider_errors(self):
        extraction_repo = MagicMock()
        course_repo = MagicMock()
        document_repo = MagicMock()
        document_repo.get_by_id_for_owner.side_effect = RuntimeError(
            "psycopg://user:secret@host/db connection failed"
        )

        service = ExtractionService(
            course_repository=course_repo,
            document_repository=document_repo,
            extraction_repository=extraction_repo,
            storage_gateway=MagicMock(),
            pipeline=MagicMock(),
            model_name="test-model",
        )
        service.run_extraction_job(
            execution_id=uuid4(),
            document_id=uuid4(),
            owner_id=uuid4(),
            worker_id="worker-1",
        )

        failed_call = extraction_repo.mark_execution_failed.call_args.kwargs
        self.assertNotIn("secret@host", failed_call["error_message"])
        self.assertIn("error interno", failed_call["error_message"].lower())

    def test_durable_worker_claims_and_runs_extraction_and_planning(self):
        owner_id = uuid4()
        course_id = uuid4()
        doc_id = uuid4()
        now = datetime.now(timezone.utc)

        ext_exec = ExtractionExecution(
            id=uuid4(),
            owner_id=owner_id,
            document_id=doc_id,
            course_id=course_id,
            status="running",
            model_name="test",
            total_pages=None,
            processed_pages=0,
            activities_count=0,
            conflicts_count=0,
            error_message=None,
            started_at=now,
            completed_at=None,
            created_at=now,
            updated_at=now,
            worker_id="w1",
            attempt_count=1,
        )
        plan_exec = PlanningExecution(
            id=uuid4(),
            owner_id=owner_id,
            course_id=course_id,
            status="running",
            model_name="test",
            horizon_start=now,
            horizon_end=now + timedelta(days=1),
            plan_id=None,
            activities_count=0,
            blocks_count=0,
            pending_count=0,
            error_message=None,
            started_at=now,
            completed_at=None,
            created_at=now,
            updated_at=now,
            worker_id="w1",
            attempt_count=1,
        )

        ext_repo = MagicMock()
        plan_repo = MagicMock()
        ext_service = MagicMock()
        plan_service = MagicMock()

        ext_repo.claim_next_extraction_execution.side_effect = [ext_exec, None, None]
        plan_repo.claim_next_planning_execution.side_effect = [plan_exec, None]

        worker = DurableWorker(
            worker_id="w1",
            lease_seconds=180,
            max_attempts=3,
            extraction_repository=ext_repo,
            planning_repository=plan_repo,
            extraction_service=ext_service,
            planning_service=plan_service,
        )

        self.assertTrue(worker.run_once())
        ext_service.run_extraction_job.assert_called_once_with(
            execution_id=ext_exec.id,
            document_id=doc_id,
            owner_id=owner_id,
            worker_id="w1",
        )

        self.assertTrue(worker.run_once())
        plan_service.run_planning_job.assert_called_once_with(
            execution_id=plan_exec.id,
            owner_id=owner_id,
            course_id=course_id,
            horizon_start=plan_exec.horizon_start,
            horizon_end=plan_exec.horizon_end,
            worker_id="w1",
        )

        self.assertFalse(worker.run_once())

    def test_worker_config_requires_lease_greater_than_timeout(self):
        with patch.dict(
            os.environ,
            {
                "WORKER_JOB_TIMEOUT_SECONDS": "120",
                "WORKER_LEASE_SECONDS": "120",
            },
            clear=False,
        ):
            with self.assertRaises(ConfigurationError):
                get_worker_config()

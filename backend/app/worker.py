import logging
import os
import signal
import socket
import time
from uuid import uuid4

from dotenv import load_dotenv

from app.api.dependencies import get_extraction_service, get_planning_service
from app.application.extraction_service import ExtractionService
from app.application.planning_service import PlanningService
from app.domain.ports import ExtractionRepository, PlanningRepository
from app.infrastructure.config import get_database_url, get_worker_config
from app.infrastructure.extraction_repository import PostgresExtractionRepository
from app.infrastructure.planning_repository import PostgresPlanningRepository

logger = logging.getLogger(__name__)


class DurableWorker:
    """Polls PostgreSQL queues for extraction and planning jobs using SKIP LOCKED leases."""

    def __init__(
        self,
        worker_id: str,
        lease_seconds: int,
        max_attempts: int,
        extraction_repository: ExtractionRepository,
        planning_repository: PlanningRepository,
        extraction_service: ExtractionService,
        planning_service: PlanningService,
    ) -> None:
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._max_attempts = max_attempts
        self._extraction_repository = extraction_repository
        self._planning_repository = planning_repository
        self._extraction_service = extraction_service
        self._planning_service = planning_service

    def run_once(self) -> bool:
        """Reap exhausted expired jobs, then claim and run at most one queued job."""
        self._extraction_repository.fail_exhausted_extraction_executions(
            max_attempts=self._max_attempts
        )
        self._planning_repository.fail_exhausted_planning_executions(
            max_attempts=self._max_attempts
        )

        extraction_job = self._extraction_repository.claim_next_extraction_execution(
            worker_id=self._worker_id,
            lease_seconds=self._lease_seconds,
            max_attempts=self._max_attempts,
        )
        if extraction_job is not None:
            logger.info(
                "Worker %s claimed extraction %s (attempt %s)",
                self._worker_id,
                extraction_job.id,
                extraction_job.attempt_count,
            )
            self._extraction_service.run_extraction_job(
                execution_id=extraction_job.id,
                document_id=extraction_job.document_id,
                owner_id=extraction_job.owner_id,
                worker_id=self._worker_id,
            )
            return True

        planning_job = self._planning_repository.claim_next_planning_execution(
            worker_id=self._worker_id,
            lease_seconds=self._lease_seconds,
            max_attempts=self._max_attempts,
        )
        if planning_job is not None:
            logger.info(
                "Worker %s claimed planning %s (attempt %s)",
                self._worker_id,
                planning_job.id,
                planning_job.attempt_count,
            )
            if planning_job.course_id is None:
                self._planning_repository.mark_planning_execution_failed(
                    execution_id=planning_job.id,
                    owner_id=planning_job.owner_id,
                    error_message="La ejecución de planificación no tiene curso asociado.",
                    worker_id=self._worker_id,
                )
                return True

            self._planning_service.run_planning_job(
                execution_id=planning_job.id,
                owner_id=planning_job.owner_id,
                course_id=planning_job.course_id,
                horizon_start=planning_job.horizon_start,
                horizon_end=planning_job.horizon_end,
                worker_id=self._worker_id,
            )
            return True

        return False


def main() -> None:
    """Entrypoint for `python -m app.worker`."""
    load_dotenv()
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    database_url = get_database_url()
    worker_config = get_worker_config()
    worker_id = f"{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:8]}"

    worker = DurableWorker(
        worker_id=worker_id,
        lease_seconds=worker_config.lease_seconds,
        max_attempts=worker_config.max_attempts,
        extraction_repository=PostgresExtractionRepository(database_url=database_url),
        planning_repository=PostgresPlanningRepository(database_url=database_url),
        extraction_service=get_extraction_service(),
        planning_service=get_planning_service(),
    )

    running = True

    def _stop(_signum: int, _frame: object) -> None:
        nonlocal running
        logger.info("Worker %s stopping...", worker_id)
        running = False

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    logger.info(
        "Durable worker %s started (lease=%ss, timeout=%ss, poll=%ss, max_attempts=%s)",
        worker_id,
        worker_config.lease_seconds,
        worker_config.job_timeout_seconds,
        worker_config.poll_interval_seconds,
        worker_config.max_attempts,
    )

    while running:
        try:
            did_work = worker.run_once()
        except Exception as exc:
            logger.error("Unexpected error in worker loop (%s)", type(exc).__name__)
            did_work = False

        if not did_work and running:
            time.sleep(worker_config.poll_interval_seconds)


if __name__ == "__main__":
    main()

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.auth_service import AuthService
from app.application.course_service import CourseService
from app.application.document_service import DocumentService
from app.application.extraction_service import ExtractionService
from app.application.planning_service import PlanningService
from app.domain.exceptions import AuthenticationError
from app.domain.models import AuthenticatedUser
from app.infrastructure.config import (
    get_database_url,
    get_groq_config,
    get_supabase_config,
    get_supabase_storage_config,
    get_worker_config,
)
from app.infrastructure.course_repository import PostgresCourseRepository
from app.infrastructure.document_repository import PostgresDocumentRepository
from app.infrastructure.extraction_repository import PostgresExtractionRepository
from app.infrastructure.groq_principal import GroqPrincipal
from app.infrastructure.pdf_validation import validate_syllabus_pdf
from app.infrastructure.planning_repository import PostgresPlanningRepository
from app.infrastructure.study_planning_graph import StudyPlanningPipeline
from app.infrastructure.supabase_auth import SupabaseAuthGateway
from app.infrastructure.supabase_storage import SupabaseStorageGateway
from app.infrastructure.syllabus_extraction_graph import SyllabusExtractionPipeline

_bearer_scheme = HTTPBearer(auto_error=False)


def get_auth_service() -> AuthService:
    """Build AuthService wired to SupabaseAuthGateway."""
    config = get_supabase_config()
    gateway = SupabaseAuthGateway(
        supabase_url=config.url,
        publishable_key=config.publishable_key,
    )
    return AuthService(auth_gateway=gateway)


def get_course_service() -> CourseService:
    """Build CourseService wired to PostgresCourseRepository."""
    database_url = get_database_url()
    repository = PostgresCourseRepository(database_url=database_url)
    return CourseService(course_repository=repository)


def get_document_service() -> DocumentService:
    """Build DocumentService wired to Postgres and private Supabase Storage."""
    database_url = get_database_url()
    storage_config = get_supabase_storage_config()
    return DocumentService(
        course_repository=PostgresCourseRepository(database_url=database_url),
        document_repository=PostgresDocumentRepository(database_url=database_url),
        storage_gateway=SupabaseStorageGateway(
            supabase_url=storage_config.url,
            service_role_key=storage_config.service_role_key,
        ),
        storage_bucket=storage_config.bucket,
        pdf_validator=validate_syllabus_pdf,
    )


def get_extraction_service() -> ExtractionService:
    """Build ExtractionService wired to Postgres, Storage, and LangGraph+Groq."""
    database_url = get_database_url()
    storage_config = get_supabase_storage_config()
    groq_config = get_groq_config()
    worker_config = get_worker_config()
    pipeline = SyllabusExtractionPipeline(
        groq_api_key=groq_config.api_key,
        model_name=groq_config.model,
        job_timeout_seconds=worker_config.job_timeout_seconds,
    )
    return ExtractionService(
        course_repository=PostgresCourseRepository(database_url=database_url),
        document_repository=PostgresDocumentRepository(database_url=database_url),
        extraction_repository=PostgresExtractionRepository(database_url=database_url),
        storage_gateway=SupabaseStorageGateway(
            supabase_url=storage_config.url,
            service_role_key=storage_config.service_role_key,
        ),
        pipeline=pipeline,
        principal=GroqPrincipal(groq_config.api_key, groq_config.model),
        model_name=groq_config.model,
        pdf_validator=validate_syllabus_pdf,
    )


def get_planning_service() -> PlanningService:
    """Build PlanningService wired to PostgresPlanningRepository and LangGraph+Groq."""
    database_url = get_database_url()
    groq_config = get_groq_config()
    pipeline = StudyPlanningPipeline(
        groq_api_key=groq_config.api_key,
        model_name=groq_config.model,
    )
    return PlanningService(
        planning_repository=PostgresPlanningRepository(database_url=database_url),
        course_repository=PostgresCourseRepository(database_url=database_url),
        pipeline=pipeline,
        principal=GroqPrincipal(groq_config.api_key, groq_config.model),
        model_name=groq_config.model,
    )


def require_bearer_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("Se requiere token Bearer.")
    return credentials.credentials


def get_current_user(
    token: str = Depends(require_bearer_token),
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthenticatedUser:
    return auth_service.get_current_user(token)

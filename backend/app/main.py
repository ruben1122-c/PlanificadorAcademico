import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.activities import router as activities_router
from app.api.auth import router as auth_router
from app.api.availability import router as availability_router
from app.api.courses import router as courses_router
from app.api.documents import router as documents_router
from app.api.executions import router as executions_router
from app.api.health import router as health_router
from app.api.planning import router as planning_router
from app.domain.exceptions import (
    ActivityNotFoundError,
    AuthenticationError,
    ConfigurationError,
    CourseNotFoundError,
    DocumentNotFoundError,
    DomainError,
    ExecutionNotFoundError,
    ExternalServiceError,
    PlanNotFoundError,
    SyllabusBusyError,
    ValidationError,
)

load_dotenv()

_ERROR_STATUS_MAP: dict[type[DomainError], int] = {
    AuthenticationError: status.HTTP_401_UNAUTHORIZED,
    CourseNotFoundError: status.HTTP_404_NOT_FOUND,
    DocumentNotFoundError: status.HTTP_404_NOT_FOUND,
    ExecutionNotFoundError: status.HTTP_404_NOT_FOUND,
    ActivityNotFoundError: status.HTTP_404_NOT_FOUND,
    PlanNotFoundError: status.HTTP_404_NOT_FOUND,
    SyllabusBusyError: status.HTTP_409_CONFLICT,
    ValidationError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    ConfigurationError: status.HTTP_500_INTERNAL_SERVER_ERROR,
    ExternalServiceError: status.HTTP_502_BAD_GATEWAY,
}


def get_allowed_origins() -> list[str]:
    """Parse allowed CORS origins from FRONTEND_ORIGIN environment variable."""
    raw_origins = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    return origins or ["http://localhost:5173"]


app = FastAPI(title="Planificador Académico API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DomainError)
def handle_domain_error(_: Request, exc: DomainError) -> JSONResponse:
    """Map domain exceptions to HTTP status codes."""
    status_code = _ERROR_STATUS_MAP.get(
        type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR
    )
    return JSONResponse(status_code=status_code, content={"detail": str(exc)})


app.include_router(health_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(courses_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(executions_router, prefix="/api/v1")
app.include_router(activities_router, prefix="/api/v1")
app.include_router(availability_router, prefix="/api/v1")
app.include_router(planning_router, prefix="/api/v1")

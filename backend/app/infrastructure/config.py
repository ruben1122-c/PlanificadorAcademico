import os
from dataclasses import dataclass

from app.domain.exceptions import ConfigurationError


@dataclass(frozen=True)
class SupabaseConfig:
    """Supabase Auth connection settings."""

    url: str
    publishable_key: str


@dataclass(frozen=True)
class SupabaseStorageConfig:
    """Supabase Storage service settings for private buckets."""

    url: str
    service_role_key: str
    bucket: str


@dataclass(frozen=True)
class GroqConfig:
    """Groq LLM configuration for syllabus extraction."""

    api_key: str
    model: str


@dataclass(frozen=True)
class WorkerConfig:
    """Durable PostgreSQL worker configuration."""

    lease_seconds: int
    job_timeout_seconds: int
    poll_interval_seconds: float
    max_attempts: int


def get_supabase_config() -> SupabaseConfig:
    """Load and validate Supabase Auth configuration from environment variables."""
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    publishable_key = (
        os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()
        or os.getenv("SUPABASE_ANON_KEY", "").strip()
    )
    if not url or not publishable_key:
        raise ConfigurationError(
            "Faltan SUPABASE_URL o SUPABASE_PUBLISHABLE_KEY en la configuración."
        )
    return SupabaseConfig(url=url, publishable_key=publishable_key)


def get_supabase_storage_config() -> SupabaseStorageConfig:
    """Load and validate Supabase Storage configuration from environment variables."""
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    bucket = os.getenv("SUPABASE_STORAGE_BUCKET", "syllabi").strip() or "syllabi"
    if not url or not service_role_key:
        raise ConfigurationError(
            "Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY en la configuración."
        )
    return SupabaseStorageConfig(
        url=url,
        service_role_key=service_role_key,
        bucket=bucket,
    )


def get_groq_config() -> GroqConfig:
    """Load and validate Groq API configuration from environment variables."""
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b").strip() or "openai/gpt-oss-20b"
    if not api_key:
        raise ConfigurationError("Falta GROQ_API_KEY en la configuración.")
    return GroqConfig(api_key=api_key, model=model)


def get_database_url() -> str:
    """Load and validate DATABASE_URL from environment variables."""
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise ConfigurationError("Falta DATABASE_URL en la configuración.")
    return database_url


def get_worker_config() -> WorkerConfig:
    """Load and validate durable PostgreSQL worker settings."""
    try:
        lease_seconds = int(os.getenv("WORKER_LEASE_SECONDS", "180").strip() or "180")
        job_timeout_seconds = int(
            os.getenv("WORKER_JOB_TIMEOUT_SECONDS", "120").strip() or "120"
        )
        poll_interval_seconds = float(
            os.getenv("WORKER_POLL_INTERVAL_SECONDS", "1.0").strip() or "1.0"
        )
        max_attempts = int(os.getenv("WORKER_MAX_ATTEMPTS", "3").strip() or "3")
    except ValueError as exc:
        raise ConfigurationError(
            "Configuración inválida para los parámetros numéricos del worker."
        ) from exc

    if job_timeout_seconds <= 0:
        raise ConfigurationError("WORKER_JOB_TIMEOUT_SECONDS debe ser mayor a 0.")
    if lease_seconds <= job_timeout_seconds:
        raise ConfigurationError(
            "WORKER_LEASE_SECONDS debe ser estrictamente mayor que WORKER_JOB_TIMEOUT_SECONDS."
        )
    if poll_interval_seconds <= 0:
        raise ConfigurationError("WORKER_POLL_INTERVAL_SECONDS debe ser mayor a 0.")
    if max_attempts <= 0:
        raise ConfigurationError("WORKER_MAX_ATTEMPTS debe ser mayor a 0.")

    return WorkerConfig(
        lease_seconds=lease_seconds,
        job_timeout_seconds=job_timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        max_attempts=max_attempts,
    )

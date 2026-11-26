from app.domain.exceptions import (
    CourseNotFoundError,
    DocumentNotFoundError,
    ExternalServiceError,
    ValidationError,
)


def sanitize_execution_error(exc: Exception) -> str:
    """Return a safe user-facing error message without leaking provider or internal details."""
    if isinstance(exc, DocumentNotFoundError):
        return "Documento no encontrado."
    if isinstance(exc, CourseNotFoundError):
        return "Curso no encontrado."
    if isinstance(exc, ValidationError):
        return str(exc)
    if isinstance(exc, TimeoutError):
        return "La ejecución superó el tiempo máximo permitido. Intenta nuevamente."
    if isinstance(exc, ExternalServiceError):
        return "No se pudo completar el procesamiento con el servicio externo. Intenta nuevamente."
    return "Ocurrió un error interno al procesar la ejecución."

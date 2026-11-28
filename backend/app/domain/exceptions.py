class DomainError(Exception):
    """Base exception for domain and application errors."""


class AuthenticationError(DomainError):
    """Raised when credentials or bearer tokens are invalid."""


class CourseNotFoundError(DomainError):
    """Raised when a requested course does not exist for the owner."""


class DocumentNotFoundError(DomainError):
    """Raised when a requested document does not exist for the owner."""


class ExecutionNotFoundError(DomainError):
    """Raised when a requested extraction execution does not exist for the owner."""


class ActivityNotFoundError(DomainError):
    """Raised when a requested activity does not exist for the owner."""


class PlanNotFoundError(DomainError):
    """Raised when a requested study plan does not exist for the owner."""


class ValidationError(DomainError):
    """Raised when domain input violates business rules."""


class SyllabusBusyError(DomainError):
    """Raised when a course upload or extraction cannot acquire its reservation."""


class ConfigurationError(DomainError):
    """Raised when required runtime configuration is missing."""


class ExternalServiceError(DomainError):
    """Raised when an upstream service (e.g. Supabase Auth) fails."""

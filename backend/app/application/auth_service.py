from app.domain.exceptions import ValidationError
from app.domain.models import AuthSession, AuthenticatedUser
from app.domain.ports import AuthGateway


class AuthService:
    """Application service for authentication use cases."""

    def __init__(self, auth_gateway: AuthGateway) -> None:
        self._auth_gateway = auth_gateway

    def login(self, email: str, password: str) -> AuthSession:
        """Authenticate a user with email and password."""
        normalized_email = email.strip()
        if not normalized_email or not password:
            raise ValidationError("El correo y la contraseña son obligatorios.")
        return self._auth_gateway.login_with_password(normalized_email, password)

    def get_current_user(self, access_token: str) -> AuthenticatedUser:
        """Verify a bearer token and return the authenticated user."""
        token = access_token.strip()
        if not token:
            raise ValidationError("El token Bearer es obligatorio.")
        return self._auth_gateway.get_user_from_token(token)

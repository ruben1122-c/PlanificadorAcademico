from typing import Any
from uuid import UUID

import httpx

from app.domain.exceptions import AuthenticationError, ExternalServiceError
from app.domain.models import AuthSession, AuthenticatedUser


class SupabaseAuthGateway:
    """HTTPX-based client for Supabase Auth endpoints."""

    def __init__(self, supabase_url: str, publishable_key: str) -> None:
        self._base_url = supabase_url.rstrip("/")
        self._publishable_key = publishable_key

    def _headers(self, access_token: str | None = None) -> dict[str, str]:
        headers = {
            "apikey": self._publishable_key,
            "Content-Type": "application/json",
        }
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        return headers

    def _parse_user(self, payload: dict[str, Any]) -> AuthenticatedUser:
        raw_id = payload.get("id")
        raw_email = payload.get("email")
        if not raw_id or not raw_email:
            raise ExternalServiceError("Respuesta incompleta de Supabase Auth.")
        try:
            user_id = UUID(str(raw_id))
        except ValueError as exc:
            raise ExternalServiceError("ID de usuario inválido en Supabase Auth.") from exc
        return AuthenticatedUser(id=user_id, email=str(raw_email))

    def login_with_password(self, email: str, password: str) -> AuthSession:
        """Authenticate against Supabase Auth password grant."""
        url = f"{self._base_url}/auth/v1/token"
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    url,
                    params={"grant_type": "password"},
                    headers=self._headers(),
                    json={"email": email, "password": password},
                )
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                "No se pudo conectar con Supabase Auth."
            ) from exc

        if response.status_code in (400, 401):
            raise AuthenticationError("Credenciales inválidas.")
        if response.status_code >= 400:
            raise ExternalServiceError(
                f"Error de Supabase Auth (HTTP {response.status_code})."
            )

        data = response.json()
        access_token = data.get("access_token")
        user_payload = data.get("user")
        if not access_token or not isinstance(user_payload, dict):
            raise ExternalServiceError("Respuesta de login inválida de Supabase Auth.")

        user = self._parse_user(user_payload)
        return AuthSession(
            access_token=str(access_token),
            token_type=str(data.get("token_type", "bearer")),
            expires_in=data.get("expires_in"),
            refresh_token=data.get("refresh_token"),
            user=user,
        )

    def get_user_from_token(self, access_token: str) -> AuthenticatedUser:
        """Verify bearer token against Supabase Auth /auth/v1/user."""
        url = f"{self._base_url}/auth/v1/user"
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    url,
                    headers=self._headers(access_token=access_token),
                )
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                "No se pudo verificar el token con Supabase Auth."
            ) from exc

        if response.status_code in (401, 403):
            raise AuthenticationError("Token inválido o expirado.")
        if response.status_code >= 400:
            raise ExternalServiceError(
                f"Error de Supabase Auth (HTTP {response.status_code})."
            )

        data = response.json()
        if not isinstance(data, dict):
            raise ExternalServiceError("Respuesta inválida de Supabase Auth.")
        return self._parse_user(data)

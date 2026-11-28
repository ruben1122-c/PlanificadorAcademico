from urllib.parse import quote

import httpx

from app.domain.exceptions import ExternalServiceError


class SupabaseStorageGateway:
    """HTTPX-based client for private Supabase Storage bucket operations."""

    def __init__(self, supabase_url: str, service_role_key: str) -> None:
        self._base_url = supabase_url.rstrip("/")
        self._service_role_key = service_role_key

    def _headers(self, content_type: str | None = None) -> dict[str, str]:
        headers = {
            "apikey": self._service_role_key,
            "Authorization": f"Bearer {self._service_role_key}",
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    @staticmethod
    def _encode_path(path: str) -> str:
        return quote(path.lstrip("/"), safe="/")

    def upload_private_file(
        self,
        bucket: str,
        path: str,
        content: bytes,
        content_type: str,
    ) -> None:
        """Upload binary file content into a private Supabase Storage bucket."""
        encoded_path = self._encode_path(path)
        url = f"{self._base_url}/storage/v1/object/{bucket}/{encoded_path}"
        headers = self._headers(content_type=content_type)

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(url, headers=headers, content=content)
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                "No se pudo subir el archivo a Supabase Storage."
            ) from exc

        if response.status_code >= 400:
            raise ExternalServiceError(
                f"Error de Supabase Storage al subir archivo (HTTP {response.status_code})."
            )

    def download_private_file(self, bucket: str, path: str) -> bytes:
        """Download binary file content from a private Supabase Storage bucket."""
        encoded_path = self._encode_path(path)
        url = f"{self._base_url}/storage/v1/object/{bucket}/{encoded_path}"

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(url, headers=self._headers())
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                "No se pudo descargar el archivo desde Supabase Storage."
            ) from exc

        if response.status_code >= 400:
            raise ExternalServiceError(
                f"Error de Supabase Storage al descargar archivo (HTTP {response.status_code})."
            )

        return response.content

    def delete_private_file(self, bucket: str, path: str) -> None:
        url = f"{self._base_url}/storage/v1/object/{bucket}/{self._encode_path(path)}"
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.delete(url, headers=self._headers())
        except httpx.HTTPError as exc:
            raise ExternalServiceError("No se pudo limpiar el archivo de la carga fallida.") from exc
        if response.status_code >= 400 and response.status_code != 404:
            raise ExternalServiceError("No se pudo limpiar el archivo de la carga fallida.")

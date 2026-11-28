import hashlib
import logging
import os
import re
from collections.abc import Callable
from uuid import UUID

from app.domain.exceptions import (
    CourseNotFoundError,
    DocumentNotFoundError,
    DomainError,
    ValidationError,
)
from app.domain.models import SyllabusDocument, SyllabusStatus, UploadReservation
from app.domain.ports import (
    CourseRepository,
    DocumentRepository,
    StorageGateway,
)

MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
logger = logging.getLogger(__name__)


class DocumentService:
    """Application service for owner-scoped syllabus document uploads and queries."""

    def __init__(
        self,
        course_repository: CourseRepository,
        document_repository: DocumentRepository,
        storage_gateway: StorageGateway,
        storage_bucket: str,
        pdf_validator: Callable[[bytes], None],
    ) -> None:
        self._course_repository = course_repository
        self._document_repository = document_repository
        self._storage_gateway = storage_gateway
        self._storage_bucket = storage_bucket
        self._pdf_validator = pdf_validator

    @staticmethod
    def _sanitize_filename(filename: str | None) -> str:
        base = os.path.basename((filename or "syllabus.pdf").strip()) or "syllabus.pdf"
        cleaned = _SAFE_FILENAME_RE.sub("_", base).strip("._")
        if not cleaned:
            cleaned = "syllabus.pdf"
        stem = cleaned[:-4] if cleaned.lower().endswith(".pdf") else cleaned
        return f"{stem[:116]}.pdf"

    def reserve_upload(self, owner_id: UUID, course_id: UUID, filename: str) -> UploadReservation:
        return self._document_repository.reserve_upload(
            owner_id, course_id, self._sanitize_filename(filename)
        )

    def get_syllabus_status(
        self, owner_id: UUID, course_id: UUID, document_id: UUID | None
    ) -> SyllabusStatus:
        return self._document_repository.get_syllabus_status(owner_id, course_id, document_id)

    def _validate_upload(
        self, filename: str | None, content_type: str | None, content: bytes
    ) -> None:
        if not content:
            raise ValidationError("El archivo PDF está vacío.")
        if len(content) > MAX_FILE_SIZE_BYTES:
            raise ValidationError("El archivo PDF supera el límite de 20 MB.")
        normalized_type = (content_type or "application/pdf").split(";")[0].strip().lower()
        is_pdf_name = (filename or "").lower().endswith(".pdf")
        if normalized_type != "application/pdf" and not is_pdf_name:
            raise ValidationError("Solo se permiten archivos en formato PDF.")
        if not content.startswith(b"%PDF"):
            raise ValidationError("El archivo enviado no tiene cabecera PDF válida.")
        self._pdf_validator(content)

    def upload_syllabus(
        self,
        owner_id: UUID,
        course_id: UUID,
        filename: str | None,
        content_type: str | None,
        content: bytes,
        upload_id: UUID | None = None,
    ) -> SyllabusDocument:
        """Validate a PDF, store it privately in Supabase Storage, and record metadata."""
        course = self._course_repository.get_by_id_for_owner(course_id, owner_id)
        if course is None:
            raise CourseNotFoundError("Curso no encontrado.")

        try:
            self._validate_upload(filename, content_type, content)
        except ValidationError:
            if upload_id is not None:
                try:
                    self._document_repository.fail_upload(owner_id, course_id, upload_id, receiving=False)
                except DomainError:
                    logger.warning("No se pudo liberar la reserva %s tras validar el PDF.", upload_id)
            raise

        if upload_id is None:
            upload_id = self.reserve_upload(owner_id, course_id, filename or "syllabus.pdf").upload_id
        sha256 = hashlib.sha256(content).hexdigest()
        upload, existing = self._document_repository.claim_upload(owner_id, course_id, upload_id, sha256)
        if existing is not None:
            return existing

        storage_path = f"{owner_id}/{course_id}/{upload_id}_{upload.filename}"
        try:
            self._storage_gateway.upload_private_file(
                bucket=self._storage_bucket,
                path=storage_path,
                content=content,
                content_type="application/pdf",
            )
            return self._document_repository.finish_upload(
                upload_id=upload_id,
                owner_id=owner_id,
                course_id=course_id,
                file_size=len(content),
                storage_bucket=self._storage_bucket,
                storage_path=storage_path,
                sha256=sha256,
            )
        except DomainError:
            # Confirm PostgreSQL did not commit the document before removing its object.
            try:
                if self._document_repository.fail_upload(owner_id, course_id, upload_id, receiving=True):
                    self._storage_gateway.delete_private_file(self._storage_bucket, storage_path)
                else:
                    committed = self._document_repository.get_by_id_for_owner(upload_id, owner_id)
                    if committed is not None:
                        return committed
            except DomainError:
                logger.warning("No se pudo reconciliar la carga fallida %s.", upload_id)
            raise

    def list_documents(
        self, owner_id: UUID, course_id: UUID | None = None
    ) -> list[SyllabusDocument]:
        """List syllabus documents owned by owner_id, optionally filtered by course_id."""
        if course_id is not None:
            course = self._course_repository.get_by_id_for_owner(course_id, owner_id)
            if course is None:
                raise CourseNotFoundError("Curso no encontrado.")
        return self._document_repository.list_by_owner(
            owner_id=owner_id,
            course_id=course_id,
        )

    def get_document(self, document_id: UUID, owner_id: UUID) -> SyllabusDocument:
        """Fetch a single syllabus document owned by owner_id."""
        document = self._document_repository.get_by_id_for_owner(document_id, owner_id)
        if document is None:
            raise DocumentNotFoundError("Documento no encontrado.")
        return document

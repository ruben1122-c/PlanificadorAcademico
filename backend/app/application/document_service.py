import hashlib
import os
import re
from uuid import UUID, uuid4

from app.domain.exceptions import (
    CourseNotFoundError,
    DocumentNotFoundError,
    ValidationError,
)
from app.domain.models import SyllabusDocument
from app.domain.ports import (
    CourseRepository,
    DocumentRepository,
    StorageGateway,
)

_MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


class DocumentService:
    """Application service for owner-scoped syllabus document uploads and queries."""

    def __init__(
        self,
        course_repository: CourseRepository,
        document_repository: DocumentRepository,
        storage_gateway: StorageGateway,
        storage_bucket: str,
    ) -> None:
        self._course_repository = course_repository
        self._document_repository = document_repository
        self._storage_gateway = storage_gateway
        self._storage_bucket = storage_bucket

    @staticmethod
    def _sanitize_filename(filename: str | None) -> str:
        base = os.path.basename((filename or "syllabus.pdf").strip()) or "syllabus.pdf"
        cleaned = _SAFE_FILENAME_RE.sub("_", base).strip("._")
        if not cleaned:
            cleaned = "syllabus.pdf"
        if not cleaned.lower().endswith(".pdf"):
            cleaned = f"{cleaned}.pdf"
        return cleaned[:120]

    def upload_syllabus(
        self,
        owner_id: UUID,
        course_id: UUID,
        filename: str | None,
        content_type: str | None,
        content: bytes,
    ) -> SyllabusDocument:
        """Validate a PDF, store it privately in Supabase Storage, and record metadata."""
        course = self._course_repository.get_by_id_for_owner(course_id, owner_id)
        if course is None:
            raise CourseNotFoundError("Curso no encontrado.")

        if not content:
            raise ValidationError("El archivo PDF está vacío.")
        if len(content) > _MAX_FILE_SIZE_BYTES:
            raise ValidationError("El archivo PDF supera el límite de 20 MB.")

        normalized_type = (content_type or "application/pdf").split(";")[0].strip().lower()
        is_pdf_name = (filename or "").lower().endswith(".pdf")
        if normalized_type != "application/pdf" and not is_pdf_name:
            raise ValidationError("Solo se permiten archivos en formato PDF.")
        if not content.startswith(b"%PDF"):
            raise ValidationError("El archivo enviado no tiene cabecera PDF válida.")

        safe_name = self._sanitize_filename(filename)
        document_id = uuid4()
        storage_path = f"{owner_id}/{course_id}/{document_id}_{safe_name}"
        sha256 = hashlib.sha256(content).hexdigest()

        self._storage_gateway.upload_private_file(
            bucket=self._storage_bucket,
            path=storage_path,
            content=content,
            content_type="application/pdf",
        )

        return self._document_repository.create(
            document_id=document_id,
            owner_id=owner_id,
            course_id=course_id,
            filename=safe_name,
            content_type="application/pdf",
            file_size=len(content),
            storage_bucket=self._storage_bucket,
            storage_path=storage_path,
            sha256=sha256,
        )

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

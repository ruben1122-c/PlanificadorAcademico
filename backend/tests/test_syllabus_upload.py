import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pymupdf

from app.application.document_service import DocumentService
from app.application.extraction_service import ExtractionService
from app.domain.exceptions import ExternalServiceError, SyllabusBusyError, ValidationError
from app.domain.models import UploadReservation
from app.infrastructure.pdf_validation import validate_syllabus_pdf


def make_pdf(*, with_text: bool) -> bytes:
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        if with_text:
            page.insert_text((50, 60), "Actividad de arquitectura. Fecha: 12 de diciembre.")
        return pdf.tobytes()


class SyllabusUploadTest(unittest.TestCase):
    def setUp(self) -> None:
        self.owner_id, self.course_id, self.upload_id = uuid4(), uuid4(), uuid4()
        self.course_repo = MagicMock()
        self.documents = MagicMock()
        self.storage = MagicMock()
        self.now = datetime.now(timezone.utc)
        self.reservation = UploadReservation(
            self.upload_id, "syllabus.pdf", self.now + timedelta(minutes=5), "receiving"
        )
        self.service = DocumentService(
            self.course_repo, self.documents, self.storage, "syllabi", validate_syllabus_pdf
        )

    def upload(self, pdf: bytes):
        return self.service.upload_syllabus(
            self.owner_id, self.course_id, "syllabus.pdf", "application/pdf", pdf, self.upload_id
        )

    def test_corrupt_and_textless_files_release_reservation_before_storage(self):
        for pdf, message in (
            (b"%PDF-not-a-valid-pdf", "dañado"),
            (make_pdf(with_text=False), "texto seleccionable"),
        ):
            with self.subTest(message=message):
                self.documents.reset_mock()
                with self.assertRaisesRegex(ValidationError, message):
                    self.upload(pdf)
                self.documents.fail_upload.assert_called_once_with(
                    self.owner_id, self.course_id, self.upload_id, receiving=False
                )
                self.documents.claim_upload.assert_not_called()
        self.storage.upload_private_file.assert_not_called()

    def test_repeated_upload_returns_existing_document_before_storage(self):
        existing = object()
        self.documents.claim_upload.return_value = self.reservation, existing
        self.assertIs(self.upload(make_pdf(with_text=True)), existing)
        self.storage.upload_private_file.assert_not_called()
        self.documents.finish_upload.assert_not_called()

    def test_expiration_after_storage_write_removes_only_the_uncommitted_object(self):
        self.documents.claim_upload.return_value = self.reservation, None
        self.documents.finish_upload.side_effect = SyllabusBusyError("Reserva vencida.")
        self.documents.fail_upload.return_value = True
        with self.assertRaises(SyllabusBusyError):
            self.upload(make_pdf(with_text=True))
        self.storage.delete_private_file.assert_called_once_with(
            "syllabi", f"{self.owner_id}/{self.course_id}/{self.upload_id}_syllabus.pdf"
        )

    def test_ambiguous_database_commit_does_not_remove_the_committed_file(self):
        existing = object()
        self.documents.claim_upload.return_value = self.reservation, None
        self.documents.finish_upload.side_effect = ExternalServiceError("Error de conexión.")
        self.documents.fail_upload.return_value = False
        self.documents.get_by_id_for_owner.return_value = existing
        self.assertIs(self.upload(make_pdf(with_text=True)), existing)
        self.storage.delete_private_file.assert_not_called()

    def test_worker_validates_legacy_file_before_delegation(self):
        executions = MagicMock()
        principal = MagicMock()
        pipeline = MagicMock()
        self.storage.download_private_file.return_value = make_pdf(with_text=False)
        worker = ExtractionService(
            self.course_repo, self.documents, executions, self.storage, pipeline,
            "test-model", validate_syllabus_pdf, principal,
        )
        worker.run_extraction_job(uuid4(), uuid4(), self.owner_id, "test-worker")
        principal.delegate.assert_not_called()
        pipeline.run.assert_not_called()
        self.assertIn(
            "texto seleccionable",
            executions.mark_execution_failed.call_args.kwargs["error_message"],
        )

    def test_worker_does_not_complete_an_extraction_after_losing_its_lease(self):
        executions = MagicMock()
        executions.replace_document_extraction_results.return_value = None
        pipeline = MagicMock()
        pipeline.run.return_value = {"activities": [], "conflicts": [], "total_pages": 1}
        self.storage.download_private_file.return_value = make_pdf(with_text=True)
        worker = ExtractionService(
            self.course_repo, self.documents, executions, self.storage, pipeline,
            "test-model", validate_syllabus_pdf,
        )
        worker.run_extraction_job(uuid4(), uuid4(), self.owner_id, "stale-worker")
        self.assertEqual(
            executions.replace_document_extraction_results.call_args.kwargs["worker_id"],
            "stale-worker",
        )
        executions.mark_execution_completed.assert_not_called()
        executions.mark_execution_failed.assert_not_called()


if __name__ == "__main__":
    unittest.main()

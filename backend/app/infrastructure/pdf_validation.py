import pymupdf

from app.domain.exceptions import ValidationError


def validate_syllabus_pdf(content: bytes) -> None:
    """Validate the supported PDF shape before using storage or an AI provider."""
    try:
        with pymupdf.open(stream=content, filetype="pdf") as pdf:
            if not pdf.is_pdf or pdf.is_repaired or not pdf.page_count:
                raise ValidationError("No se pudo leer el PDF. Verifica que no esté dañado.")
            if pdf.needs_pass:
                raise ValidationError("El PDF está protegido con contraseña.")
            if pdf.page_count > 25:
                raise ValidationError("El PDF supera el límite de 25 páginas.")
            if not any(page.get_text().strip() for page in pdf):
                raise ValidationError("El PDF no contiene texto seleccionable.")
    except (pymupdf.FileDataError, RuntimeError) as exc:
        raise ValidationError("No se pudo leer el PDF. Verifica que no esté dañado.") from exc

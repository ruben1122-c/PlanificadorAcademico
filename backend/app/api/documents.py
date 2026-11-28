from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Query,
    UploadFile,
    status,
)

from app.api.dependencies import (
    get_current_user,
    get_document_service,
    get_extraction_service,
)
from app.api.schemas import (
    ActivityResponse,
    ConflictResponse,
    DocumentActivitiesResponse,
    DocumentResponse,
    ExecutionResponse,
)
from app.application.document_service import MAX_FILE_SIZE_BYTES, DocumentService
from app.application.extraction_service import ExtractionService
from app.domain.models import AuthenticatedUser

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_document(
    course_id: UUID = Form(...),
    file: UploadFile = File(...),
    upload_id: UUID | None = Form(default=None),
    current_user: AuthenticatedUser = Depends(get_current_user),
    document_service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    """Upload a syllabus PDF via multipart/form-data to private Supabase Storage."""
    content = file.file.read(MAX_FILE_SIZE_BYTES + 1)
    document = document_service.upload_syllabus(
        owner_id=current_user.id,
        course_id=course_id,
        filename=file.filename,
        content_type=file.content_type,
        content=content,
        upload_id=upload_id,
    )
    return DocumentResponse.model_validate(document)


@router.get("", response_model=list[DocumentResponse])
def list_documents(
    course_id: UUID | None = Query(default=None),
    current_user: AuthenticatedUser = Depends(get_current_user),
    document_service: DocumentService = Depends(get_document_service),
) -> list[DocumentResponse]:
    """List syllabus documents owned by the authenticated user."""
    documents = document_service.list_documents(
        owner_id=current_user.id,
        course_id=course_id,
    )
    return [DocumentResponse.model_validate(doc) for doc in documents]


@router.post(
    "/{document_id}/extractions",
    response_model=ExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_document_extraction(
    document_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    extraction_service: ExtractionService = Depends(get_extraction_service),
) -> ExecutionResponse:
    """Enqueue a durable PostgreSQL extraction job for a syllabus document."""
    execution = extraction_service.start_extraction(
        document_id=document_id,
        owner_id=current_user.id,
    )
    return ExecutionResponse.model_validate(execution)


@router.get(
    "/{document_id}/activities",
    response_model=DocumentActivitiesResponse,
)
def get_document_activities(
    document_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    extraction_service: ExtractionService = Depends(get_extraction_service),
) -> DocumentActivitiesResponse:
    """List extracted activities and conflicts for an owner-scoped document."""
    activities, conflicts = extraction_service.get_document_activities_and_conflicts(
        document_id=document_id,
        owner_id=current_user.id,
    )
    return DocumentActivitiesResponse(
        document_id=document_id,
        activities=[ActivityResponse.model_validate(item) for item in activities],
        conflicts=[ConflictResponse.model_validate(item) for item in conflicts],
    )

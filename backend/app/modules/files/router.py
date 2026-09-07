"""API surface for File Storage & Uploads — PRD-ARCHITECTURE.md §8:
`/api/v1/files/*`.

Unlike every other module's router, there's no single `require_permission`
gate here — this endpoint serves three unrelated business contexts
(patient documents, lab reports, clinic letterhead assets), each already
owning its own correctly-scoped permission in its own module. The router
only requires authentication (`get_current_user`); `FileService` dispatches
the real per-`owner_type` permission check and, for reads, the same
row-level scoping (Patient-self, Doctor-treated-patient, "only COMPLETED
lab reports") the source modules already enforce on this same data — see
app/modules/files/service.py's module docstring.
"""

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Query, Response, UploadFile, status

from app.api.deps import CurrentUser, get_current_user
from app.modules.files.schemas import DocumentListResponse, DocumentSummary
from app.modules.files.service import FileService

router = APIRouter(prefix="/api/v1/files", tags=["files"])


def get_file_service() -> FileService:
    return FileService()


@router.post("/upload", response_model=DocumentSummary, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile,
    owner_type: str = Form(..., description='One of PATIENT_DOCUMENT, LAB_REPORT, LETTERHEAD_ASSET'),
    owner_id: uuid.UUID = Form(...),
    current_user: CurrentUser = Depends(get_current_user),
    service: FileService = Depends(get_file_service),
) -> DocumentSummary:
    content = await file.read()
    return await service.upload(
        tenant_id=current_user.tenant_id, owner_type=owner_type, owner_id=owner_id, filename=file.filename or "upload",
        content_type=file.content_type, content=content, actor_user_id=current_user.user_id, actor_role=current_user.role_code,
        actor_permissions=current_user.permissions,
    )


@router.get("", response_model=DocumentListResponse)
async def search_files(
    owner_type: str = Query(...),
    owner_id: uuid.UUID = Query(...),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
    service: FileService = Depends(get_file_service),
) -> DocumentListResponse:
    return await service.search_documents(
        tenant_id=current_user.tenant_id, owner_type=owner_type, owner_id=owner_id, actor_user_id=current_user.user_id,
        actor_role=current_user.role_code, actor_permissions=current_user.permissions, limit=limit, offset=offset,
    )


@router.get("/{document_id}", response_model=DocumentSummary)
async def get_file_metadata(
    document_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: FileService = Depends(get_file_service),
) -> DocumentSummary:
    return await service.get_document(
        tenant_id=current_user.tenant_id, document_id=document_id, actor_user_id=current_user.user_id,
        actor_role=current_user.role_code, actor_permissions=current_user.permissions,
    )


@router.get("/{document_id}/content")
async def download_file_content(
    document_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: FileService = Depends(get_file_service),
) -> Response:
    content, document = await service.get_document_content(
        tenant_id=current_user.tenant_id, document_id=document_id, actor_user_id=current_user.user_id,
        actor_role=current_user.role_code, actor_permissions=current_user.permissions,
    )
    ascii_fallback = document.original_filename.replace('"', "")
    encoded = quote(document.original_filename)
    return Response(
        content=content,
        media_type=document.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}"},
    )

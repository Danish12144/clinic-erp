import uuid
from datetime import datetime

from pydantic import BaseModel


class DocumentSummary(BaseModel):
    """`download_url` is computed by the service, not a plain ORM column —
    never built via a bare `model_validate(document)`, same convention
    `MedicineSummary`/`InventoryItemSummary` already established for their
    own computed fields."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    owner_type: str
    owner_id: uuid.UUID
    original_filename: str
    mime_type: str | None
    file_size_bytes: int | None
    uploaded_by: uuid.UUID | None
    created_at: datetime
    download_url: str


class DocumentListResponse(BaseModel):
    items: list[DocumentSummary]
    total: int
    limit: int
    offset: int

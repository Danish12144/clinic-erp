import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.files.models import Document


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, tenant_id: uuid.UUID, **fields: object) -> Document:
        document = Document(tenant_id=tenant_id, **fields)
        self._session.add(document)
        await self._session.flush()
        return document

    async def get_by_id(self, document_id: uuid.UUID) -> Document | None:
        result = await self._session.execute(select(Document).where(Document.id == document_id))
        return result.scalar_one_or_none()

    async def search(self, *, tenant_id: uuid.UUID, owner_type: str, owner_id: uuid.UUID, limit: int, offset: int) -> tuple[list[Document], int]:
        filters = [Document.tenant_id == tenant_id, Document.owner_type == owner_type, Document.owner_id == owner_id]

        count_result = await self._session.execute(select(func.count()).select_from(Document).where(*filters))
        total = count_result.scalar_one()

        page_result = await self._session.execute(
            select(Document).where(*filters).order_by(Document.created_at.desc()).limit(limit).offset(offset)
        )
        return list(page_result.scalars().all()), total

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.patients.models import Patient


class PatientRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def next_mrn_candidate(self, *, tenant_id: uuid.UUID) -> str:
        """MRN-{year}-{sequence}, e.g. MRN-2026-0007. The sequence is a
        best-effort count of this tenant's patients registered this year,
        not a DB sequence — under concurrent registration two receptionists
        could race for the same candidate. That's handled by retrying with
        the next number on a unique-constraint conflict (see
        PatientService._create_with_mrn_retry), rather than adding a
        dedicated counter table for what should be a rare collision in
        practice."""
        year = datetime.now(timezone.utc).year
        prefix = f"MRN-{year}-"
        result = await self._session.execute(
            select(func.count()).select_from(Patient).where(Patient.tenant_id == tenant_id, Patient.mrn.like(f"{prefix}%"))
        )
        count = result.scalar_one()
        return f"{prefix}{count + 1:04d}"

    async def create(self, *, tenant_id: uuid.UUID, mrn: str, **fields: object) -> Patient:
        patient = Patient(tenant_id=tenant_id, mrn=mrn, **fields)
        self._session.add(patient)
        await self._session.flush()
        return patient

    async def get_by_id(self, patient_id: uuid.UUID, *, include_deleted: bool = False) -> Patient | None:
        query = select(Patient).where(Patient.id == patient_id)
        if not include_deleted:
            query = query.where(Patient.deleted_at.is_(None))
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: uuid.UUID) -> Patient | None:
        result = await self._session.execute(
            select(Patient).where(Patient.user_id == user_id, Patient.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def find_unlinked_by_phone(self, *, tenant_id: uuid.UUID, phone: str) -> list[Patient]:
        """Candidates for self-service portal auto-linking (see
        AuthService.request_patient_otp) — only patients with no
        `user_id` yet, so a phone that's already linked to a portal
        account is never matched here (the auth service's own
        `UserRepository.get_by_phone` lookup finds that case first)."""
        result = await self._session.execute(
            select(Patient).where(
                Patient.tenant_id == tenant_id, Patient.phone == phone, Patient.user_id.is_(None), Patient.deleted_at.is_(None)
            )
        )
        return list(result.scalars().all())

    async def link_user(self, *, patient_id: uuid.UUID, user_id: uuid.UUID) -> None:
        await self._session.execute(update(Patient).where(Patient.id == patient_id).values(user_id=user_id))

    async def find_possible_duplicates(
        self, *, tenant_id: uuid.UUID, phone: str | None, first_name: str, last_name: str | None, date_of_birth: date | None
    ) -> list[Patient]:
        """Soft duplicate signal, never a hard block (PRD §5.1): an exact
        phone match, OR the same (first name, last name, date of birth)
        triple. Either is a reasonable "you might mean this person"
        prompt, not proof of identity."""
        conditions = []
        if phone:
            conditions.append(Patient.phone == phone)
        if date_of_birth is not None:
            conditions.append(
                and_(
                    func.lower(Patient.first_name) == first_name.lower(),
                    func.lower(func.coalesce(Patient.last_name, "")) == (last_name or "").lower(),
                    Patient.date_of_birth == date_of_birth,
                )
            )
        if not conditions:
            return []

        result = await self._session.execute(
            select(Patient).where(Patient.tenant_id == tenant_id, Patient.deleted_at.is_(None), or_(*conditions))
        )
        return list(result.scalars().all())

    async def search(
        self,
        *,
        tenant_id: uuid.UUID,
        query_text: str | None,
        phone: str | None,
        mrn: str | None,
        include_deleted: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[Patient], int]:
        filters = [Patient.tenant_id == tenant_id]
        if not include_deleted:
            filters.append(Patient.deleted_at.is_(None))
        if phone:
            filters.append(Patient.phone == phone)
        if mrn:
            filters.append(Patient.mrn == mrn)

        name_expr = func.concat(Patient.first_name, " ", func.coalesce(Patient.last_name, ""))
        if query_text:
            # pg_trgm similarity, not ILIKE — tolerates typos/transposed
            # names, which matters a lot for a front-desk search box.
            filters.append(func.similarity(name_expr, query_text) > 0.2)

        count_result = await self._session.execute(select(func.count()).select_from(Patient).where(*filters))
        total = count_result.scalar_one()

        page_query = select(Patient).where(*filters)
        page_query = (
            page_query.order_by(func.similarity(name_expr, query_text).desc())
            if query_text
            else page_query.order_by(Patient.created_at.desc())
        )
        page_result = await self._session.execute(page_query.limit(limit).offset(offset))
        return list(page_result.scalars().all()), total

    async def update(self, patient_id: uuid.UUID, **fields: object) -> None:
        fields["updated_at"] = datetime.now(timezone.utc)
        await self._session.execute(update(Patient).where(Patient.id == patient_id).values(**fields))

    async def soft_delete(self, patient_id: uuid.UUID) -> None:
        now = datetime.now(timezone.utc)
        await self._session.execute(update(Patient).where(Patient.id == patient_id).values(deleted_at=now, updated_at=now))

"""Clinic Letterhead Configuration — a tenant-level settings feature
requested alongside Consultation/E-Prescription so a prescription (or any
future document) can be exported/printed either DIGITAL (full clinic
header/footer) or PHYSICAL (margins only, for pre-printed stationery).

Deliberately does NOT generate a PDF/image here — there is no PDF-rendering
or object-storage (S3/R2) infrastructure anywhere in this backend yet (the
PRD's own Documents module, §9, is a later, separate concern). This service
only resolves the *layout parameters* a frontend needs to render or print a
document correctly; see PrescriptionRouter's `/print` endpoint for the one
concrete consumer wired up so far.

Reuses `TenantSetting` (Tenancy module, migration `0003`) as the storage —
one well-known key (`letterhead.config`), a typed schema on top instead of
a raw JSON PUT, rather than a new table. No new migration needed.
"""

import uuid

from fastapi import HTTPException, status

from app.core.db import tenant_session
from app.modules.letterhead.schemas import (
    LetterheadConfig,
    LetterheadHeaderSource,
    LetterheadPrintMode,
    LetterheadResolved,
    ResolvedHeaderFooter,
)
from app.modules.tenancy.repository import BranchRepository, ClinicRepository, TenantSettingRepository

_SETTING_KEY = "letterhead.config"


class LetterheadService:
    async def get_config(self, *, tenant_id: uuid.UUID) -> LetterheadConfig:
        async with tenant_session(tenant_id) as session:
            setting = await TenantSettingRepository(session).get_by_key(tenant_id=tenant_id, key=_SETTING_KEY)
            if setting is None:
                return LetterheadConfig()
            return LetterheadConfig.model_validate(setting.value)

    async def update_config(self, *, tenant_id: uuid.UUID, payload: LetterheadConfig) -> LetterheadConfig:
        async with tenant_session(tenant_id) as session:
            await TenantSettingRepository(session).upsert(tenant_id=tenant_id, key=_SETTING_KEY, value=payload.model_dump(mode="json"))
        return payload

    async def resolve(self, *, tenant_id: uuid.UUID, mode: LetterheadPrintMode, branch_id: uuid.UUID | None) -> LetterheadResolved:
        config = await self.get_config(tenant_id=tenant_id)

        if mode == LetterheadPrintMode.PHYSICAL:
            # The pre-printed stationery already carries the clinic's
            # header/footer — rendering one digitally on top would double
            # it up, so PHYSICAL omits both entirely and only the margins
            # (sized to clear what's already on the paper) apply.
            return LetterheadResolved(
                mode=mode, header=None, footer=None,
                top_margin_mm=config.physical_top_margin_mm, bottom_margin_mm=config.physical_bottom_margin_mm,
            )

        async with tenant_session(tenant_id) as session:
            clinic = await ClinicRepository(session).get_by_id(tenant_id)
            if clinic is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Clinic not found")
            branch = await BranchRepository(session).get_by_id(branch_id) if branch_id is not None else None
            if branch_id is not None and branch is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Branch '{branch_id}' does not exist")

        if config.header_source == LetterheadHeaderSource.CUSTOM_ASSET:
            header = ResolvedHeaderFooter(source=LetterheadHeaderSource.CUSTOM_ASSET, image_url=config.header_image_url)
            footer = (
                ResolvedHeaderFooter(source=LetterheadHeaderSource.CUSTOM_ASSET, image_url=config.footer_image_url)
                if config.footer_image_url
                else None
            )
        else:
            header = ResolvedHeaderFooter(
                source=LetterheadHeaderSource.AUTO,
                clinic_name=clinic.name,
                logo_url=config.logo_url,
                address=branch.address if branch else None,
                contact=config.contact_override or (branch.phone if branch else None),
                branch_name=branch.name if branch else None,
            )
            footer = None

        # A DIGITAL header/footer is rendered as its own content block, not
        # a fixed-size margin reservation — 0mm here, distinct from
        # PHYSICAL's configured margins above.
        return LetterheadResolved(mode=mode, header=header, footer=footer, top_margin_mm=0.0, bottom_margin_mm=0.0)

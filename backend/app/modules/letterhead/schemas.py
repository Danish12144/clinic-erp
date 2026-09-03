from enum import Enum as PyEnum

from pydantic import BaseModel, Field, model_validator


class LetterheadHeaderSource(str, PyEnum):
    AUTO = "AUTO"
    CUSTOM_ASSET = "CUSTOM_ASSET"


class LetterheadPrintMode(str, PyEnum):
    DIGITAL = "DIGITAL"
    PHYSICAL = "PHYSICAL"


class LetterheadConfig(BaseModel):
    """Stored verbatim as the value of the `letterhead.config`
    `TenantSetting` (PUT replaces the whole thing — omitted fields reset to
    their default, same "generic settings bag" semantics
    `TenantSettingRepository.upsert` already has elsewhere).

    `header_source` only matters for a DIGITAL export/print — AUTO composes
    a header from the clinic's own name plus this config's `logo_url`/
    `contact_override` and (when resolved for a specific branch) that
    branch's address/phone; CUSTOM_ASSET instead uses a pre-made header/
    footer image the Owner uploaded elsewhere and just points to here.
    `physical_*_margin_mm` is independent of `header_source` — it's what a
    PHYSICAL export/print uses instead of any header/footer at all, sized
    to clear whatever is already printed on the clinic's pre-printed
    stationery."""

    header_source: LetterheadHeaderSource = LetterheadHeaderSource.AUTO
    logo_url: str | None = Field(None, max_length=2000)
    contact_override: str | None = Field(None, max_length=300)
    header_image_url: str | None = Field(None, max_length=2000)
    footer_image_url: str | None = Field(None, max_length=2000)
    physical_top_margin_mm: float = Field(40.0, ge=0, le=200)
    physical_bottom_margin_mm: float = Field(20.0, ge=0, le=200)

    @model_validator(mode="after")
    def custom_asset_needs_a_header_image(self) -> "LetterheadConfig":
        if self.header_source == LetterheadHeaderSource.CUSTOM_ASSET and not self.header_image_url:
            raise ValueError("header_image_url is required when header_source is CUSTOM_ASSET")
        return self


class ResolvedHeaderFooter(BaseModel):
    source: LetterheadHeaderSource
    clinic_name: str | None = None
    logo_url: str | None = None
    address: str | None = None
    contact: str | None = None
    branch_name: str | None = None
    image_url: str | None = None


class LetterheadResolved(BaseModel):
    """What a frontend actually renders for one export/print: DIGITAL
    carries a full header/footer and zero margins (the header/footer
    graphics define their own spacing); PHYSICAL carries no header/footer
    at all (the paper already has one printed) and the configured margins
    instead, so body content doesn't overlap the pre-printed stationery."""

    mode: LetterheadPrintMode
    header: ResolvedHeaderFooter | None
    footer: ResolvedHeaderFooter | None
    top_margin_mm: float
    bottom_margin_mm: float

"""ABHA/ABDM Preparedness — PRD-ARCHITECTURE.md §23/§29 (Phase 12,
explicitly deferred), §6's reserved `AbhaLink` sketch (patient_id, abha_id,
linked_at, consent_artifact_ref — "deliberately empty/unused until §23's
ABDM phase, but the shape is reserved so Patient doesn't need a schema
migration to grow an external-ID field later").

Deliberately simpler than that reserved `AbhaLink` table, by direct
instruction: two nullable columns directly on `patients`
(`abha_id` — the 14-digit ABHA number, `abha_address` — the
human-readable "abha-address"/health ID, e.g. `name@abdm`), not a separate
linking table with its own `linked_at`/`consent_artifact_ref` audit trail.
This is genuinely less than the master schema's own sketch — no
consent-artifact tracking, no link-history — because this task asked only
for lightweight, feature-flagged *preparedness* (fields that exist and can
be toggled visible), not a real ABDM integration. If/when real ABDM
linking is built, `AbhaLink` (or a fuller version of it) is still the
right home for the consent/audit trail this pair of columns doesn't
attempt to model — don't assume these two columns are "done," they're a
placeholder the same way `prescription_items.medicine_id` was before
Pharmacy shipped.

No new permission — `patients.register`/`patients.view_demographics`/
`patients.view_emr` already gate reading/writing every other Patient
field, and there's no reason these two need a narrower or wider audience.
`features.abdm_enabled` (Clinic Settings, TenantSetting bag — reuses the
exact same generic mechanism `require_feature_flag()` already provides for
Lab/Pharmacy, no new column, no new migration) additionally gates
*writing* a non-null value to either column at the service layer
(`PatientService`) — "small clinics keep it off with zero clutter" means
attempting to set these fields at all is rejected (422) until the Owner
opts in via the existing generic `PUT /api/v1/clinics/me/settings/{key}`
endpoint, not just a frontend-side hint.

Revision ID: 0027
Revises: 0026
Create Date: 2026-09-08

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE patients ADD COLUMN abha_id text")
    op.execute("ALTER TABLE patients ADD COLUMN abha_address text")


def downgrade() -> None:
    op.execute("ALTER TABLE patients DROP COLUMN IF EXISTS abha_address")
    op.execute("ALTER TABLE patients DROP COLUMN IF EXISTS abha_id")

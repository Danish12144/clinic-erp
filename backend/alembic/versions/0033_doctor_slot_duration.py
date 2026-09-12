"""Phase 1 (Master Handoff §5 "MEDIUM — Doctor schedule", this phase's own
instruction #5 "working hours, slot duration, and assigned branches") —
`doctor_profiles.slot_duration_minutes`, a new column backing the staff
Appointments page's slot-grid increment, which was previously a single
frontend-hardcoded constant (`SLOT_INCREMENT_MINUTES = 15` in
appointments-page.tsx) with no per-doctor configurability at all.

`NOT NULL DEFAULT 15` matches that previous hardcoded value exactly, so
every existing doctor row is unaffected until an Owner explicitly
reconfigures one via the new "Edit schedule" screen. This is purely a
scheduling-*display* concern — how far apart the grid offers slots to
click — distinct from a specific appointment's own `duration_minutes`
(still freely 5-240 per booking, unchanged).

No permission change: this column is read/written through the existing
`staff.manage`-gated `PATCH /api/v1/doctors/{user_id}` route, the same one
`working_hours` already goes through.

Revision ID: 0033
Revises: 0032
Create Date: 2026-09-13

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0033"
down_revision: Union[str, None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE doctor_profiles ADD COLUMN slot_duration_minutes SMALLINT NOT NULL DEFAULT 15")
    op.execute("ALTER TABLE doctor_profiles ADD CONSTRAINT ck_doctor_profiles_slot_duration CHECK (slot_duration_minutes BETWEEN 5 AND 240)")


def downgrade() -> None:
    op.execute("ALTER TABLE doctor_profiles DROP CONSTRAINT IF EXISTS ck_doctor_profiles_slot_duration")
    op.execute("ALTER TABLE doctor_profiles DROP COLUMN IF EXISTS slot_duration_minutes")

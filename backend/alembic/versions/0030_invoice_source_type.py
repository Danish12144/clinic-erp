"""Enables 1-to-N Encounter -> Invoice (the ER diagram in
docs/PRD-ARCHITECTURE.md previously showed one-to-zero-or-one, and the
only thing actually enforcing that shape was app code, not the schema --
`invoices.encounter_id` has always been a plain, non-unique FK). This
migration adds the discriminator that makes multiple invoices per
encounter unambiguous: `invoices.source_type`, reusing the existing
`invoice_line_source` enum (CONSULTATION/PROCEDURE/PHARMACY/LAB/OTHER --
OTHER doubles as "general/ad-hoc", no new enum value needed) rather than
inventing a parallel type.

Backfill: any existing invoice whose line items are *all* CONSULTATION is
marked CONSULTATION (matches every invoice `auto_generate_invoice` has
ever created); everything else defaults to OTHER, since a manually built
invoice with mixed line-item types has no single correct type to infer.

Revision ID: 0030
Revises: 0029
Create Date: 2026-09-11

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE invoices
          ADD COLUMN source_type invoice_line_source NOT NULL DEFAULT 'OTHER'
        """
    )
    op.execute(
        """
        UPDATE invoices SET source_type = 'CONSULTATION'
        WHERE EXISTS (SELECT 1 FROM invoice_line_items li WHERE li.invoice_id = invoices.id AND li.source_type = 'CONSULTATION')
          AND NOT EXISTS (SELECT 1 FROM invoice_line_items li WHERE li.invoice_id = invoices.id AND li.source_type != 'CONSULTATION')
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE invoices DROP COLUMN source_type")

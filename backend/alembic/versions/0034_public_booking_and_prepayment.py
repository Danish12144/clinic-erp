"""Phase 2 (Master Handoff "Patient acquisition & real integrations")
items 1/4/5 — schema support for public self-booking with an optional
online prepayment.

`payment_gateway_orders` is a new, dedicated ledger for a booking-time
prepayment — deliberately NOT layered into the existing `invoices`/
`payments` tables. Those model a clinical encounter's bill, which doesn't
exist yet at public-booking time (no consultation has happened); forcing
a booking fee through `Invoice`/`Payment` would mean fabricating a
branch-scoped invoice for a patient who hasn't been seen. If a later
phase wants to reconcile this fee against the eventual visit invoice,
that's a deliberate future task, not something this table quietly
already supports.

`Appointment.payment_status` is a new column, orthogonal to the existing
`Appointment.status` (the clinical day-of workflow — SCHEDULED/CHECKED_IN/
IN_PROGRESS/COMPLETED/CANCELLED/NO_SHOW, untouched by this migration).
Every appointment ever created by staff/walk-in is NOT_REQUIRED (no
prepayment concept there); a public online booking that opts into
prepayment starts PENDING, and reaches CONFIRMED/FAILED/REFUNDED only via
the payment gateway webhook or a staff/patient-initiated refund — never
set directly by any other code path, the same "always derived, only at
specific transition points" discipline `Invoice.status` already follows.

Revision ID: 0034
Revises: 0033
Create Date: 2026-09-14

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0034"
down_revision: Union[str, None] = "0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE payment_gateway_order_status AS ENUM ('CREATED','PAID','FAILED','REFUNDED')")
    op.execute("CREATE TYPE appointment_payment_status AS ENUM ('NOT_REQUIRED','PENDING','CONFIRMED','FAILED','REFUNDED')")

    op.execute(
        "ALTER TABLE appointments ADD COLUMN payment_status appointment_payment_status "
        "NOT NULL DEFAULT 'NOT_REQUIRED'"
    )

    op.execute(
        """
        CREATE TABLE payment_gateway_orders (
          id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id            UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          appointment_id       UUID NOT NULL REFERENCES appointments(id) ON DELETE CASCADE,
          provider             text NOT NULL,
          provider_order_id    text NOT NULL,
          amount               numeric(12,2) NOT NULL,
          currency             text NOT NULL DEFAULT 'INR',
          status               payment_gateway_order_status NOT NULL DEFAULT 'CREATED',
          provider_payment_id  text,
          failure_reason       text,
          created_at           timestamptz NOT NULL DEFAULT now(),
          updated_at           timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX ux_payment_gateway_orders_provider_order "
        "ON payment_gateway_orders (provider, provider_order_id)"
    )
    op.execute("CREATE INDEX ix_payment_gateway_orders_appointment ON payment_gateway_orders (appointment_id)")

    op.execute(
        "CREATE TRIGGER trg_payment_gateway_orders_updated_at BEFORE UPDATE ON payment_gateway_orders "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.execute("ALTER TABLE payment_gateway_orders ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE payment_gateway_orders FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON payment_gateway_orders
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS payment_gateway_orders")
    op.execute("DROP TYPE IF EXISTS payment_gateway_order_status")
    op.execute("ALTER TABLE appointments DROP COLUMN IF EXISTS payment_status")
    op.execute("DROP TYPE IF EXISTS appointment_payment_status")

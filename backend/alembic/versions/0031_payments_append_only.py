"""Phase 1 (Master Handoff §6 "Production safety rules" / §10 "Billing &
payment rules") — closes a real inconsistency this project's own docs had
flagged since migration 0014: `payments` was deliberately left off the
`prevent_update_delete()` append-only mechanism that already protects
`vitals`/`prescriptions`/`audit_logs`, on the reasoning that the master
schema classified it "insert-mostly by convention, not by constraint."
That classification is no longer good enough for a product handling real
money commercially — a payment row is at least as sensitive as a vitals
reading, and "by convention" means a bug or a compromised credential could
silently rewrite payment history with nothing at the database layer to
stop it.

This attaches the exact same trigger `vitals`/`prescriptions`/`audit_logs`
already use, and revokes UPDATE/DELETE from `app_user` the same way. No
existing code path is affected: `PaymentRepository` has never had an
update/delete method (payments were only ever inserted, per the
class's own docstring), and `void_invoice`'s reversing entry is itself a
new INSERT of a negative-amount `Payment` row — untouched by a trigger
that only blocks UPDATE/DELETE.

Revision ID: 0031
Revises: 0030
Create Date: 2026-09-13

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE TRIGGER trg_payments_immutable BEFORE UPDATE OR DELETE ON payments "
        "FOR EACH ROW EXECUTE FUNCTION prevent_update_delete()"
    )
    op.execute("REVOKE UPDATE, DELETE ON payments FROM app_user")


def downgrade() -> None:
    op.execute("GRANT UPDATE, DELETE ON payments TO app_user")
    op.execute("DROP TRIGGER IF EXISTS trg_payments_immutable ON payments")

"""File Storage & Uploads — PRD-ARCHITECTURE.md §8 (`/api/v1/files/*`),
§15. Builds `documents`, design-only in `docs/schema/clinic_erp_schema.sql`
§14 since the file's original draft ("Purpose-built alternative
`medical_documents` ... `documents` remains reserved for the generic case
... once a Documents module needs it" — migration 0016's own docstring).
This is that module.

Deliberate choices, by direct instruction:

1. `owner_type` stays free text, not a closed enum — same "polymorphic by
   design" reasoning the master schema's own comment already gives, and
   the same non-exhaustive-open-string precedent `notification_templates.
   template_key` established (migration 0024). The application layer
   (`app/modules/files/service.py`) validates against a small known set
   (`PATIENT_DOCUMENT`, `LAB_REPORT`, `LETTERHEAD_ASSET` — the three kinds
   this task named) with its own per-type permission mapping; a future
   owner kind is a one-line dict addition there, not a migration.
2. `original_filename` is a gap-fill the master schema's sketch never had
   — without it, a download response has no real filename to hand back to
   the browser (`Content-Disposition`), only an opaque generated
   `storage_key`. Same "sketch gap, fill it" pattern as `medicines.
   reorder_threshold` or `users.first_name`.
3. No `updated_at` — a `Document` row is immutable metadata about one
   uploaded file (same reasoning `medical_documents`, migration 0016,
   already established for its own, narrower table: an attachment is
   replaced by uploading a new one, never edited in place). No update
   method exists in this module's repository either way.
4. **This table does NOT replace `medical_documents`** (EMR's own
   clinically-scoped table, direct FKs to `patients`/`encounters`) —
   they stay deliberately separate, per migration 0016's own docstring.
   What was actually missing everywhere (`medical_documents.storage_key`,
   `letterhead.header_image_url`/`footer_image_url`, `expenses.
   receipt_document_id`) was a working *file upload+storage* mechanism to
   produce a real, resolvable pointer — this migration builds exactly
   that, as a small generic registry (`documents`) plus the storage
   backend (`app/core/storage.py`), not a redesign of any existing
   module's schema. Nothing in this migration touches `medical_documents`,
   `letterhead`, or `expenses` at all.

Revision ID: 0025
Revises: 0024
Create Date: 2026-09-08

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE documents (
          id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id         UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          owner_type        text NOT NULL,
          owner_id          UUID NOT NULL,
          storage_key       text NOT NULL,
          original_filename text NOT NULL,
          mime_type         text,
          file_size_bytes   bigint,
          uploaded_by       UUID REFERENCES users(id),
          created_at        timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_documents_owner ON documents (tenant_id, owner_type, owner_id)")
    op.execute("ALTER TABLE documents ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE documents FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON documents
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS documents")

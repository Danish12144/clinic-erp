"""Patient EMR Timeline & Medical Documents — PRD-ARCHITECTURE.md §4
(module list item 16, "EMR / patient medical records"), §6, §15.

`medical_documents` is a deliberate, narrower alternative to the master
schema's `documents` table (still unbuilt — see docs/schema/
clinic_erp_schema.sql), by direct instruction: the product owner asked for
a table "linked to patient_id and encounter_id" specifically, not a
polymorphic `owner_type`/`owner_id` pair. `documents` remains reserved in
the master schema for the eventual generic case (invoice PDFs, expense
receipts, ...) if/when a module needs it; this one is purpose-built for
clinical attachments (lab reports, scans, X-rays) surfaced in the EMR
timeline. `storage_key` is a metadata pointer only (an S3-style key or an
external URL) — there is no file-upload/object-storage infrastructure in
this backend yet (same "resolve layout, don't render/store the file"
scope boundary Letterhead Configuration already drew), so this module
never receives or persists raw file bytes.

Permission-matrix gap fix (same category as migrations 0004/0010/0011):
the PRD §3 matrix gives Patient "O (read)" for "Full patient EMR", but
migration 0001's seed never granted `patients.view_emr` to PATIENT at all
— unnoticed until now because no endpoint had ever used that permission
(the Patients module, migration 0004, only wired up
`patients.view_demographics`). Fixed here, the first migration to actually
consume `patients.view_emr`.

Also adds `patients.manage_documents` (new — Owner/Doctor, upload/attach a
medical document), not itself a matrix-gap-fix since "documents" isn't a
row the PRD §3 matrix models at all; scoped to the same two roles that
have clinical EMR read access, per direct instruction (task 3).

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-04

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE medical_document_type AS ENUM ('LAB_REPORT','SCAN','XRAY','OTHER')")

    op.execute(
        """
        CREATE TABLE medical_documents (
          id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id        UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          patient_id       UUID NOT NULL REFERENCES patients(id),
          encounter_id     UUID REFERENCES encounters(id),
          document_type    medical_document_type NOT NULL,
          title            text NOT NULL,
          storage_key      text NOT NULL,
          mime_type        text,
          file_size_bytes  bigint,
          notes            text,
          uploaded_by      UUID NOT NULL REFERENCES users(id),
          created_at       timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_medical_documents_patient ON medical_documents (tenant_id, patient_id, created_at)")
    op.execute("CREATE INDEX ix_medical_documents_encounter ON medical_documents (encounter_id)")
    op.execute("ALTER TABLE medical_documents ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE medical_documents FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON medical_documents
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )

    # --- Permission gap fix + new write permission -----------------------
    op.execute(
        """
        INSERT INTO permissions (code, module, description) VALUES
          ('patients.manage_documents', 'patients', 'Upload/attach a medical document to a patient or encounter')
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p WHERE (r.code, p.code) IN (
          ('PATIENT','patients.view_emr'),
          ('OWNER','patients.manage_documents'),
          ('DOCTOR','patients.manage_documents')
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE code = 'patients.manage_documents')
           OR (role_id, permission_id) IN (
             SELECT r.id, p.id FROM roles r, permissions p WHERE (r.code, p.code) = ('PATIENT', 'patients.view_emr')
           )
        """
    )
    op.execute("DELETE FROM permissions WHERE code = 'patients.manage_documents'")
    op.execute("DROP TABLE IF EXISTS medical_documents")
    op.execute("DROP TYPE IF EXISTS medical_document_type")

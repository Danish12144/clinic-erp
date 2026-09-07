"""End-to-end tests of the Billing, Invoices & Payments HTTP surface
(invoice CRUD/state machine, line items, auto-generate, payments/refunds)
against a real Postgres — see tests/conftest.py (skipped automatically if
unreachable).
"""

import pytest
from httpx import AsyncClient

from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")

_WIDE_OPEN_HOURS = {day: {"open": "00:00", "close": "23:59"} for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}


async def _create_branch(api_client: AsyncClient, owner_headers: dict[str, str], name: str) -> str:
    response = await api_client.post("/api/v1/branches", json={"name": name}, headers=owner_headers)
    assert response.status_code == 201
    return response.json()["id"]


async def _create_active_doctor(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, *, phone: str, fee: float | None = 500) -> tuple[str, dict[str, str]]:
    payload = {"first_name": "Doc", "phone": phone, "working_hours": _WIDE_OPEN_HOURS}
    if fee is not None:
        payload["consultation_fee"] = fee
    created = await api_client.post("/api/v1/doctors", json=payload, headers=owner_headers)
    assert created.status_code == 201
    user_id = created.json()["doctor"]["user_id"]
    token = created.json()["invite"]["debug_invite_token"]
    accept = await api_client.post("/api/v1/auth/accept-invite", json={"clinic_slug": test_clinic.slug, "token": token, "password": "password-123"})
    assert accept.status_code == 200
    login = await api_client.post("/api/v1/auth/staff/login", json={"clinic_slug": test_clinic.slug, "identifier": phone, "password": "password-123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    return user_id, headers


async def _create_patient(api_client: AsyncClient, owner_headers: dict[str, str], *, phone: str) -> str:
    created = await api_client.post("/api/v1/patients", json={"first_name": "Pat", "phone": phone}, headers=owner_headers)
    assert created.status_code == 201
    return created.json()["patient"]["id"]


async def _register_walk_in(api_client: AsyncClient, owner_headers: dict[str, str], *, patient_id: str, branch_id: str, doctor_id: str | None = None) -> str:
    payload = {"patient_id": patient_id, "branch_id": branch_id}
    if doctor_id:
        payload["doctor_id"] = doctor_id
    response = await api_client.post("/api/v1/encounters/walk-in", json=payload, headers=owner_headers)
    assert response.status_code == 201
    return response.json()["encounter"]["id"]


async def _start_consultation(api_client: AsyncClient, headers: dict[str, str], *, encounter_id: str) -> None:
    response = await api_client.post("/api/v1/consultations", json={"encounter_id": encounter_id}, headers=headers)
    assert response.status_code == 201


def _one_item(**overrides) -> dict:
    item = {"source_type": "OTHER", "description": "Bandage", "quantity": 2, "unit_price": 50}
    item.update(overrides)
    return item


async def _create_draft_invoice(api_client: AsyncClient, owner_headers: dict[str, str], *, branch_id: str, patient_id: str, items: list[dict] | None = None) -> dict:
    line_items = [_one_item()] if items is None else items
    response = await api_client.post(
        "/api/v1/billing/invoices", json={"branch_id": branch_id, "patient_id": patient_id, "line_items": line_items}, headers=owner_headers
    )
    assert response.status_code == 201
    return response.json()


# ---- Invoice creation ------------------------------------------------------------


async def test_receptionist_can_create_a_draft_invoice_with_line_items(api_client: AsyncClient, owner_headers: dict[str, str], login_as) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "InvoiceBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919878000001")

    headers, _ = await login_as(role_code="RECEPTIONIST")
    response = await api_client.post(
        "/api/v1/billing/invoices",
        json={"branch_id": branch_id, "patient_id": patient_id, "line_items": [_one_item(quantity=3, unit_price=100)]},
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "DRAFT"
    assert body["subtotal"] == "300.00"
    assert body["total"] == "300.00"
    assert body["total_paid"] == "0.00"
    assert body["balance_due"] == "300.00"


async def test_doctor_cannot_create_an_invoice(api_client: AsyncClient, login_as) -> None:
    headers, _ = await login_as(role_code="DOCTOR")
    response = await api_client.post("/api/v1/billing/invoices", json={"branch_id": "00000000-0000-0000-0000-000000000000", "patient_id": "00000000-0000-0000-0000-000000000000"}, headers=headers)
    assert response.status_code == 403


async def test_nurse_has_no_billing_access_at_all(api_client: AsyncClient, login_as) -> None:
    headers, _ = await login_as(role_code="NURSE")
    write = await api_client.post("/api/v1/billing/invoices", json={"branch_id": "00000000-0000-0000-0000-000000000000", "patient_id": "00000000-0000-0000-0000-000000000000"}, headers=headers)
    assert write.status_code == 403
    read = await api_client.get("/api/v1/billing/invoices", headers=headers)
    assert read.status_code == 403


async def test_create_invoice_with_nonexistent_patient_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "BadPatientInvoiceBranch")
    response = await api_client.post(
        "/api/v1/billing/invoices", json={"branch_id": branch_id, "patient_id": "00000000-0000-0000-0000-000000000000"}, headers=owner_headers
    )
    assert response.status_code == 422


# ---- Auto-generate ----------------------------------------------------------------


async def test_auto_generate_invoice_from_a_consultation_fee(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "AutoGenBranch")
    doctor_id, doctor_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919878000002", fee=750)
    patient_id = await _create_patient(api_client, owner_headers, phone="+919878000003")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id, doctor_id=doctor_id)
    await _start_consultation(api_client, doctor_headers, encounter_id=encounter_id)

    response = await api_client.post("/api/v1/billing/invoices/auto-generate", json={"encounter_id": encounter_id}, headers=owner_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "DRAFT"
    assert len(body["line_items"]) == 1
    assert body["line_items"][0]["source_type"] == "CONSULTATION"
    assert body["line_items"][0]["description"] == "Consultation Fee"
    assert body["total"] == "750.00"


async def test_auto_generate_without_a_consultation_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "NoConsultAutoGenBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919878000004")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id)

    response = await api_client.post("/api/v1/billing/invoices/auto-generate", json={"encounter_id": encounter_id}, headers=owner_headers)
    assert response.status_code == 422


async def test_auto_generate_without_a_configured_fee_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "NoFeeAutoGenBranch")
    doctor_id, doctor_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919878000005", fee=None)
    patient_id = await _create_patient(api_client, owner_headers, phone="+919878000006")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id, doctor_id=doctor_id)
    await _start_consultation(api_client, doctor_headers, encounter_id=encounter_id)

    response = await api_client.post("/api/v1/billing/invoices/auto-generate", json={"encounter_id": encounter_id}, headers=owner_headers)
    assert response.status_code == 422


# ---- Line items / DRAFT editing -------------------------------------------------------


async def test_add_and_remove_line_items_recomputes_totals(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "LineItemBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919878000007")
    invoice = await _create_draft_invoice(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id, items=[_one_item(quantity=1, unit_price=100)])
    invoice_id = invoice["id"]

    added = await api_client.post(f"/api/v1/billing/invoices/{invoice_id}/line-items", json=_one_item(description="Extra", quantity=1, unit_price=50), headers=owner_headers)
    assert added.status_code == 201
    assert added.json()["subtotal"] == "150.00"

    item_to_remove = added.json()["line_items"][1]["id"]
    removed = await api_client.delete(f"/api/v1/billing/invoices/{invoice_id}/line-items/{item_to_remove}", headers=owner_headers)
    assert removed.status_code == 200
    assert removed.json()["subtotal"] == "100.00"


async def test_update_line_item_recomputes_total(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "UpdateLineItemBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919878000008")
    invoice = await _create_draft_invoice(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id, items=[_one_item(quantity=1, unit_price=100)])
    invoice_id = invoice["id"]
    item_id = invoice["line_items"][0]["id"]

    response = await api_client.patch(f"/api/v1/billing/invoices/{invoice_id}/line-items/{item_id}", json={"quantity": 3}, headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["line_items"][0]["total"] == "300.00"
    assert response.json()["subtotal"] == "300.00"


async def test_updating_tax_and_discount_recomputes_total(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "TaxDiscountBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919878000009")
    invoice = await _create_draft_invoice(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id, items=[_one_item(quantity=1, unit_price=1000)])
    invoice_id = invoice["id"]

    response = await api_client.patch(f"/api/v1/billing/invoices/{invoice_id}", json={"tax": 90, "discount": 100}, headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["total"] == "990.00"


async def test_cannot_add_line_item_to_an_issued_invoice(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "IssuedLockBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919878000010")
    invoice = await _create_draft_invoice(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id)
    invoice_id = invoice["id"]
    await api_client.post(f"/api/v1/billing/invoices/{invoice_id}/issue", headers=owner_headers)

    response = await api_client.post(f"/api/v1/billing/invoices/{invoice_id}/line-items", json=_one_item(), headers=owner_headers)
    assert response.status_code == 409


# ---- Issue ----------------------------------------------------------------------


async def test_issuing_an_invoice_with_no_line_items_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "EmptyIssueBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919878000011")
    invoice = await _create_draft_invoice(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id, items=[])
    response = await api_client.post(f"/api/v1/billing/invoices/{invoice['id']}/issue", headers=owner_headers)
    assert response.status_code == 409


async def test_issuing_an_already_issued_invoice_conflicts(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "DoubleIssueBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919878000012")
    invoice = await _create_draft_invoice(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id)
    invoice_id = invoice["id"]
    first = await api_client.post(f"/api/v1/billing/invoices/{invoice_id}/issue", headers=owner_headers)
    assert first.status_code == 200
    assert first.json()["status"] == "ISSUED"

    second = await api_client.post(f"/api/v1/billing/invoices/{invoice_id}/issue", headers=owner_headers)
    assert second.status_code == 409


# ---- Payments ---------------------------------------------------------------------


async def test_payment_lifecycle_partial_then_full(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "PaymentBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919878000013")
    invoice = await _create_draft_invoice(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id, items=[_one_item(quantity=1, unit_price=1000)])
    invoice_id = invoice["id"]
    await api_client.post(f"/api/v1/billing/invoices/{invoice_id}/issue", headers=owner_headers)

    partial = await api_client.post("/api/v1/billing/payments", json={"invoice_id": invoice_id, "amount": 400, "method": "CASH"}, headers=owner_headers)
    assert partial.status_code == 201
    refetch_1 = await api_client.get(f"/api/v1/billing/invoices/{invoice_id}", headers=owner_headers)
    assert refetch_1.json()["status"] == "PARTIALLY_PAID"
    assert refetch_1.json()["balance_due"] == "600.00"

    full = await api_client.post("/api/v1/billing/payments", json={"invoice_id": invoice_id, "amount": 600, "method": "UPI"}, headers=owner_headers)
    assert full.status_code == 201
    refetch_2 = await api_client.get(f"/api/v1/billing/invoices/{invoice_id}", headers=owner_headers)
    assert refetch_2.json()["status"] == "PAID"
    assert refetch_2.json()["balance_due"] == "0.00"
    assert len(refetch_2.json()["payments"]) == 2


async def test_cannot_record_payment_on_a_draft_invoice(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "DraftPaymentBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919878000014")
    invoice = await _create_draft_invoice(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id)

    response = await api_client.post("/api/v1/billing/payments", json={"invoice_id": invoice["id"], "amount": 100, "method": "CASH"}, headers=owner_headers)
    assert response.status_code == 409


async def test_partial_refund_reverts_status_to_partially_paid(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "RefundBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919878000015")
    invoice = await _create_draft_invoice(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id, items=[_one_item(quantity=1, unit_price=1000)])
    invoice_id = invoice["id"]
    await api_client.post(f"/api/v1/billing/invoices/{invoice_id}/issue", headers=owner_headers)
    await api_client.post("/api/v1/billing/payments", json={"invoice_id": invoice_id, "amount": 1000, "method": "CASH"}, headers=owner_headers)

    refund = await api_client.post("/api/v1/billing/payments", json={"invoice_id": invoice_id, "amount": -300, "method": "CASH", "notes": "Overcharged"}, headers=owner_headers)
    assert refund.status_code == 201

    refetched = await api_client.get(f"/api/v1/billing/invoices/{invoice_id}", headers=owner_headers)
    assert refetched.json()["status"] == "PARTIALLY_PAID"
    assert refetched.json()["balance_due"] == "300.00"


async def test_refund_exceeding_paid_amount_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "OverRefundBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919878000016")
    invoice = await _create_draft_invoice(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id, items=[_one_item(quantity=1, unit_price=1000)])
    invoice_id = invoice["id"]
    await api_client.post(f"/api/v1/billing/invoices/{invoice_id}/issue", headers=owner_headers)
    await api_client.post("/api/v1/billing/payments", json={"invoice_id": invoice_id, "amount": 200, "method": "CASH"}, headers=owner_headers)

    response = await api_client.post("/api/v1/billing/payments", json={"invoice_id": invoice_id, "amount": -500, "method": "CASH"}, headers=owner_headers)
    assert response.status_code == 409


async def test_doctor_and_nurse_and_patient_cannot_record_or_list_payments(api_client: AsyncClient, login_as) -> None:
    for role in ("DOCTOR", "NURSE", "PATIENT"):
        headers, _ = await login_as(role_code=role)
        write = await api_client.post("/api/v1/billing/payments", json={"invoice_id": "00000000-0000-0000-0000-000000000000", "amount": 1, "method": "CASH"}, headers=headers)
        assert write.status_code == 403
        read = await api_client.get("/api/v1/billing/payments", headers=headers)
        assert read.status_code == 403


# ---- Void -----------------------------------------------------------------------


async def test_voiding_a_draft_invoice(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "VoidDraftBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919878000017")
    invoice = await _create_draft_invoice(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id)

    response = await api_client.post(f"/api/v1/billing/invoices/{invoice['id']}/void", json={"reason": "created by mistake"}, headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "VOID"
    assert response.json()["voided_reason"] == "created by mistake"


async def test_voiding_a_partially_paid_invoice_creates_a_reversal_payment(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "VoidReversalBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919878000018")
    invoice = await _create_draft_invoice(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id, items=[_one_item(quantity=1, unit_price=1000)])
    invoice_id = invoice["id"]
    await api_client.post(f"/api/v1/billing/invoices/{invoice_id}/issue", headers=owner_headers)
    await api_client.post("/api/v1/billing/payments", json={"invoice_id": invoice_id, "amount": 400, "method": "CASH"}, headers=owner_headers)

    response = await api_client.post(f"/api/v1/billing/invoices/{invoice_id}/void", json={"reason": "patient dispute"}, headers=owner_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "VOID"
    assert body["total_paid"] == "0.00"
    assert len(body["payments"]) == 2
    assert any(p["amount"] == "-400.00" for p in body["payments"])


async def test_voiding_an_already_void_invoice_conflicts(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "DoubleVoidBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919878000019")
    invoice = await _create_draft_invoice(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id)
    invoice_id = invoice["id"]
    await api_client.post(f"/api/v1/billing/invoices/{invoice_id}/void", json={"reason": "x"}, headers=owner_headers)

    response = await api_client.post(f"/api/v1/billing/invoices/{invoice_id}/void", json={"reason": "x"}, headers=owner_headers)
    assert response.status_code == 409


# ---- Row-scoped reads --------------------------------------------------------------


async def test_doctor_can_view_an_invoice_for_their_own_consultation(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "DoctorViewBranch")
    doctor_id, doctor_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919878000020")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919878000021")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id, doctor_id=doctor_id)
    await _start_consultation(api_client, doctor_headers, encounter_id=encounter_id)
    generated = await api_client.post("/api/v1/billing/invoices/auto-generate", json={"encounter_id": encounter_id}, headers=owner_headers)
    invoice_id = generated.json()["id"]

    response = await api_client.get(f"/api/v1/billing/invoices/{invoice_id}", headers=doctor_headers)
    assert response.status_code == 200


async def test_doctor_cannot_view_an_invoice_for_someone_elses_consultation(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "DoctorNoViewBranch")
    doctor_a_id, doctor_a_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919878000022")
    _, doctor_b_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919878000023")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919878000024")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id, doctor_id=doctor_a_id)
    await _start_consultation(api_client, doctor_a_headers, encounter_id=encounter_id)
    generated = await api_client.post("/api/v1/billing/invoices/auto-generate", json={"encounter_id": encounter_id}, headers=owner_headers)
    invoice_id = generated.json()["id"]

    response = await api_client.get(f"/api/v1/billing/invoices/{invoice_id}", headers=doctor_b_headers)
    assert response.status_code == 404


async def test_get_nonexistent_invoice_is_404(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.get("/api/v1/billing/invoices/00000000-0000-0000-0000-000000000000", headers=owner_headers)
    assert response.status_code == 404


# ---- Payment gateway stub (create-payment-order) -------------------------------------


async def test_create_payment_order_returns_a_simulated_order_for_the_balance_due(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "OrderBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919878000030")
    invoice = await _create_draft_invoice(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id, items=[_one_item(quantity=1, unit_price=1000)])
    invoice_id = invoice["id"]
    await api_client.post(f"/api/v1/billing/invoices/{invoice_id}/issue", headers=owner_headers)

    response = await api_client.post(f"/api/v1/billing/invoices/{invoice_id}/create-payment-order", headers=owner_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["invoice_id"] == invoice_id
    assert body["amount"] == "1000.00"
    assert body["currency"] == "INR"
    assert body["provider"] == "mock"
    assert body["status"] == "created"
    assert body["order_id"].startswith("mock_order_")

    # Purely a simulated order — no Payment was actually recorded.
    fetched = await api_client.get(f"/api/v1/billing/invoices/{invoice_id}", headers=owner_headers)
    assert fetched.json()["status"] == "ISSUED"
    assert fetched.json()["total_paid"] == "0.00"


async def test_create_payment_order_reflects_the_remaining_balance_after_a_partial_payment(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "PartialOrderBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919878000031")
    invoice = await _create_draft_invoice(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id, items=[_one_item(quantity=1, unit_price=1000)])
    invoice_id = invoice["id"]
    await api_client.post(f"/api/v1/billing/invoices/{invoice_id}/issue", headers=owner_headers)
    await api_client.post("/api/v1/billing/payments", json={"invoice_id": invoice_id, "amount": 400, "method": "CASH"}, headers=owner_headers)

    response = await api_client.post(f"/api/v1/billing/invoices/{invoice_id}/create-payment-order", headers=owner_headers)
    assert response.status_code == 201
    assert response.json()["amount"] == "600.00"


async def test_create_payment_order_for_a_draft_invoice_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "DraftOrderBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919878000032")
    invoice = await _create_draft_invoice(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id)

    response = await api_client.post(f"/api/v1/billing/invoices/{invoice['id']}/create-payment-order", headers=owner_headers)
    assert response.status_code == 409


async def test_create_payment_order_for_a_fully_paid_invoice_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "PaidOrderBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919878000033")
    invoice = await _create_draft_invoice(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id, items=[_one_item(quantity=1, unit_price=500)])
    invoice_id = invoice["id"]
    await api_client.post(f"/api/v1/billing/invoices/{invoice_id}/issue", headers=owner_headers)
    await api_client.post("/api/v1/billing/payments", json={"invoice_id": invoice_id, "amount": 500, "method": "CASH"}, headers=owner_headers)

    response = await api_client.post(f"/api/v1/billing/invoices/{invoice_id}/create-payment-order", headers=owner_headers)
    assert response.status_code == 409


async def test_create_payment_order_for_a_nonexistent_invoice_is_404(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.post("/api/v1/billing/invoices/00000000-0000-0000-0000-000000000000/create-payment-order", headers=owner_headers)
    assert response.status_code == 404


async def test_doctor_cannot_create_a_payment_order(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "NoOrderPermBranch")
    doctor_id, doctor_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919878000034")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919878000035")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id, doctor_id=doctor_id)
    await _start_consultation(api_client, doctor_headers, encounter_id=encounter_id)
    generated = await api_client.post("/api/v1/billing/invoices/auto-generate", json={"encounter_id": encounter_id}, headers=owner_headers)
    invoice_id = generated.json()["id"]
    await api_client.post(f"/api/v1/billing/invoices/{invoice_id}/issue", headers=owner_headers)

    response = await api_client.post(f"/api/v1/billing/invoices/{invoice_id}/create-payment-order", headers=doctor_headers)
    assert response.status_code == 403

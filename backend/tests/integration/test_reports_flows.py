"""End-to-end tests of the Financial Reports & Analytics HTTP surface
(`GET /api/v1/billing/summary`, `GET /api/v1/reports/financial`) against a
real Postgres — see tests/conftest.py (skipped automatically if
unreachable).
"""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")

_WIDE_OPEN_HOURS = {day: {"open": "00:00", "close": "23:59"} for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}


async def _create_branch(api_client: AsyncClient, owner_headers: dict[str, str], name: str) -> str:
    response = await api_client.post("/api/v1/branches", json={"name": name}, headers=owner_headers)
    assert response.status_code == 201
    return response.json()["id"]


async def _create_active_doctor(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, *, phone: str, fee: float = 500) -> tuple[str, dict[str, str]]:
    created = await api_client.post(
        "/api/v1/doctors", json={"first_name": "Doc", "phone": phone, "consultation_fee": fee, "working_hours": _WIDE_OPEN_HOURS}, headers=owner_headers
    )
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


async def _billed_encounter(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, *, branch_id: str, doctor_phone: str, patient_phone: str, fee: float = 500) -> tuple[str, str, dict[str, str]]:
    """Registers a walk-in, starts a consultation, and auto-generates a
    DRAFT invoice for it. Returns (invoice_id, doctor_id, doctor_headers)."""
    doctor_id, doctor_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone=doctor_phone, fee=fee)
    patient_id = await _create_patient(api_client, owner_headers, phone=patient_phone)
    walk_in = await api_client.post("/api/v1/encounters/walk-in", json={"patient_id": patient_id, "branch_id": branch_id, "doctor_id": doctor_id}, headers=owner_headers)
    assert walk_in.status_code == 201
    encounter_id = walk_in.json()["encounter"]["id"]
    started = await api_client.post("/api/v1/consultations", json={"encounter_id": encounter_id}, headers=doctor_headers)
    assert started.status_code == 201
    generated = await api_client.post("/api/v1/billing/invoices/auto-generate", json={"encounter_id": encounter_id}, headers=owner_headers)
    assert generated.status_code == 201
    return generated.json()["id"], doctor_id, doctor_headers


async def _issue_and_pay(api_client: AsyncClient, owner_headers: dict[str, str], *, invoice_id: str, amount: float, method: str) -> None:
    issued = await api_client.post(f"/api/v1/billing/invoices/{invoice_id}/issue", headers=owner_headers)
    assert issued.status_code == 200
    paid = await api_client.post("/api/v1/billing/payments", json={"invoice_id": invoice_id, "amount": amount, "method": method}, headers=owner_headers)
    assert paid.status_code == 201


# ---- RBAC -----------------------------------------------------------------------


async def test_owner_can_view_summary_and_financial_report(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    summary = await api_client.get("/api/v1/billing/summary", headers=owner_headers)
    assert summary.status_code == 200
    report = await api_client.get("/api/v1/reports/financial", headers=owner_headers)
    assert report.status_code == 200


async def test_doctor_can_view_their_own_scoped_summary_and_report(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "DoctorReportBranch")
    invoice_id, doctor_id, doctor_headers = await _billed_encounter(api_client, owner_headers, test_clinic, branch_id=branch_id, doctor_phone="+919879000001", patient_phone="+919879000002")
    await _issue_and_pay(api_client, owner_headers, invoice_id=invoice_id, amount=500, method="CASH")

    summary = await api_client.get("/api/v1/billing/summary", headers=doctor_headers)
    assert summary.status_code == 200
    assert summary.json()["total_collected"] == "500.00"

    report = await api_client.get("/api/v1/reports/financial", headers=doctor_headers)
    assert report.status_code == 200
    assert report.json()["total_billed"] == "500.00"


async def test_receptionist_nurse_and_patient_have_no_dashboard_access(api_client: AsyncClient, login_as) -> None:
    for role in ("RECEPTIONIST", "NURSE", "PATIENT"):
        headers, _ = await login_as(role_code=role)
        summary = await api_client.get("/api/v1/billing/summary", headers=headers)
        assert summary.status_code == 403
        report = await api_client.get("/api/v1/reports/financial", headers=headers)
        assert report.status_code == 403


# ---- Row-scoping across doctors -------------------------------------------------


async def test_doctor_report_is_scoped_to_their_own_revenue_even_when_another_doctor_id_is_requested(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic
) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "TwoDoctorBranch")
    invoice_a, doctor_a_id, doctor_a_headers = await _billed_encounter(
        api_client, owner_headers, test_clinic, branch_id=branch_id, doctor_phone="+919879000003", patient_phone="+919879000004", fee=300
    )
    invoice_b, doctor_b_id, _ = await _billed_encounter(
        api_client, owner_headers, test_clinic, branch_id=branch_id, doctor_phone="+919879000005", patient_phone="+919879000006", fee=700
    )
    await _issue_and_pay(api_client, owner_headers, invoice_id=invoice_a, amount=300, method="CASH")
    await _issue_and_pay(api_client, owner_headers, invoice_id=invoice_b, amount=700, method="UPI")

    # Doctor A tries to see Doctor B's numbers by passing doctor_id — the
    # service must silently override this to their own id.
    response = await api_client.get(f"/api/v1/billing/summary?doctor_id={doctor_b_id}", headers=doctor_a_headers)
    assert response.status_code == 200
    assert response.json()["total_collected"] == "300.00"


async def test_owner_can_filter_report_by_doctor_id(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "OwnerDoctorFilterBranch")
    invoice_a, doctor_a_id, _ = await _billed_encounter(
        api_client, owner_headers, test_clinic, branch_id=branch_id, doctor_phone="+919879000007", patient_phone="+919879000008", fee=250
    )
    invoice_b, doctor_b_id, _ = await _billed_encounter(
        api_client, owner_headers, test_clinic, branch_id=branch_id, doctor_phone="+919879000009", patient_phone="+919879000010", fee=900
    )
    await _issue_and_pay(api_client, owner_headers, invoice_id=invoice_a, amount=250, method="CASH")
    await _issue_and_pay(api_client, owner_headers, invoice_id=invoice_b, amount=900, method="CARD")

    response = await api_client.get(f"/api/v1/reports/financial?doctor_id={doctor_a_id}", headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["total_billed"] == "250.00"


# ---- KPI / breakdown correctness -------------------------------------------------


async def test_summary_kpis_reflect_payments_and_refunds(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "KpiBranch")
    invoice_id, _, _ = await _billed_encounter(api_client, owner_headers, test_clinic, branch_id=branch_id, doctor_phone="+919879000011", patient_phone="+919879000012", fee=1000)
    await _issue_and_pay(api_client, owner_headers, invoice_id=invoice_id, amount=1000, method="UPI")
    await api_client.post("/api/v1/billing/payments", json={"invoice_id": invoice_id, "amount": -200, "method": "UPI", "notes": "partial refund"}, headers=owner_headers)

    response = await api_client.get("/api/v1/billing/summary", headers=owner_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total_collected"] == "1000.00"
    assert body["total_refunds"] == "200.00"
    assert body["total_bills_raised"] >= 1
    assert body["payment_modes_tracked"] >= 1
    upi_row = next(m for m in body["by_payment_mode"] if m["method"] == "UPI")
    assert upi_row["collected"] == "1000.00"
    assert upi_row["refunded"] == "200.00"


async def test_financial_report_breaks_down_by_service_type(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "ServiceTypeBranch")
    doctor_id, doctor_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919879000013", fee=400)
    patient_id = await _create_patient(api_client, owner_headers, phone="+919879000014")
    walk_in = await api_client.post("/api/v1/encounters/walk-in", json={"patient_id": patient_id, "branch_id": branch_id, "doctor_id": doctor_id}, headers=owner_headers)
    encounter_id = walk_in.json()["encounter"]["id"]
    await api_client.post("/api/v1/consultations", json={"encounter_id": encounter_id}, headers=doctor_headers)
    generated = await api_client.post("/api/v1/billing/invoices/auto-generate", json={"encounter_id": encounter_id}, headers=owner_headers)
    invoice_id = generated.json()["id"]
    await api_client.post(f"/api/v1/billing/invoices/{invoice_id}/line-items", json={"source_type": "PROCEDURE", "description": "Dressing", "unit_price": 150}, headers=owner_headers)
    await _issue_and_pay(api_client, owner_headers, invoice_id=invoice_id, amount=550, method="CASH")

    response = await api_client.get("/api/v1/reports/financial", headers=owner_headers)
    assert response.status_code == 200
    by_service = {row["source_type"]: row["total_billed"] for row in response.json()["by_service_type"]}
    assert by_service.get("CONSULTATION") == "400.00"
    assert by_service.get("PROCEDURE") == "150.00"


async def test_voided_invoice_is_excluded_from_revenue_but_counted_as_raised(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "VoidedRevenueBranch")
    invoice_id, _, _ = await _billed_encounter(api_client, owner_headers, test_clinic, branch_id=branch_id, doctor_phone="+919879000015", patient_phone="+919879000016", fee=600)
    await api_client.post(f"/api/v1/billing/invoices/{invoice_id}/issue", headers=owner_headers)

    before = await api_client.get("/api/v1/reports/financial", headers=owner_headers)
    billed_before = before.json()["total_billed"]

    await api_client.post(f"/api/v1/billing/invoices/{invoice_id}/void", json={"reason": "test"}, headers=owner_headers)

    after_report = await api_client.get("/api/v1/reports/financial", headers=owner_headers)
    after_summary = await api_client.get("/api/v1/billing/summary", headers=owner_headers)
    assert float(after_report.json()["total_billed"]) == float(billed_before) - 600.0
    assert after_summary.json()["total_bills_raised"] >= 1  # still counted as raised


async def test_draft_invoice_is_excluded_from_bills_raised_count(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "DraftExcludedBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919879000017")
    before = await api_client.get("/api/v1/billing/summary", headers=owner_headers)
    before_count = before.json()["total_bills_raised"]

    await api_client.post(
        "/api/v1/billing/invoices", json={"branch_id": branch_id, "patient_id": patient_id, "line_items": [{"source_type": "OTHER", "description": "x", "unit_price": 100}]}, headers=owner_headers
    )

    after = await api_client.get("/api/v1/billing/summary", headers=owner_headers)
    assert after.json()["total_bills_raised"] == before_count


# ---- Period filtering -------------------------------------------------------------


async def test_custom_period_excludes_data_outside_the_window(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "FutureWindowBranch")
    invoice_id, _, _ = await _billed_encounter(api_client, owner_headers, test_clinic, branch_id=branch_id, doctor_phone="+919879000018", patient_phone="+919879000019", fee=500)
    await _issue_and_pay(api_client, owner_headers, invoice_id=invoice_id, amount=500, method="CASH")

    future_from = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    future_to = (datetime.now(timezone.utc) + timedelta(days=20)).isoformat()
    # Must go through `params=` (not manual f-string interpolation) so
    # httpx percent-encodes the "+" in the UTC offset — a raw "+" in a
    # query string decodes to a space server-side, corrupting the datetime.
    response = await api_client.get(
        "/api/v1/reports/financial", params={"period": "custom", "date_from": future_from, "date_to": future_to}, headers=owner_headers
    )
    assert response.status_code == 200
    assert response.json()["total_billed"] == "0.00"
    assert response.json()["by_service_type"] == []


async def test_custom_period_without_dates_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.get("/api/v1/reports/financial?period=custom", headers=owner_headers)
    assert response.status_code == 422


async def test_today_period_includes_data_created_today(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "TodayBranch")
    invoice_id, _, _ = await _billed_encounter(api_client, owner_headers, test_clinic, branch_id=branch_id, doctor_phone="+919879000020", patient_phone="+919879000021", fee=500)
    await _issue_and_pay(api_client, owner_headers, invoice_id=invoice_id, amount=500, method="CASH")

    response = await api_client.get("/api/v1/reports/financial?period=today", headers=owner_headers)
    assert response.status_code == 200
    assert float(response.json()["total_billed"]) >= 500.0

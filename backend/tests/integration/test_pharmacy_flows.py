"""End-to-end tests of the Pharmacy & Inventory Management HTTP surface
(catalog CRUD, receiving stock, FEFO dispensing against a prescription
item) against a real Postgres — see tests/conftest.py (skipped
automatically if unreachable).
"""

from datetime import date, datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")

_WIDE_OPEN_HOURS = {day: {"open": "00:00", "close": "23:59"} for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}


async def _create_branch(api_client: AsyncClient, owner_headers: dict[str, str], name: str) -> str:
    response = await api_client.post("/api/v1/branches", json={"name": name}, headers=owner_headers)
    assert response.status_code == 201
    return response.json()["id"]


async def _create_active_doctor(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, *, phone: str) -> tuple[str, dict[str, str]]:
    created = await api_client.post("/api/v1/doctors", json={"first_name": "Doc", "phone": phone, "working_hours": _WIDE_OPEN_HOURS}, headers=owner_headers)
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


async def _enable_pharmacy_feature(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.put("/api/v1/clinics/me/settings/features.pharmacy_enabled", json={"value": True}, headers=owner_headers)
    assert response.status_code == 200


async def _create_medicine(api_client: AsyncClient, owner_headers: dict[str, str], *, name: str, reorder_threshold: int = 0) -> str:
    response = await api_client.post(
        "/api/v1/pharmacy/medicines", json={"name": name, "unit_price": 5, "reorder_threshold": reorder_threshold}, headers=owner_headers
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _receive_stock(api_client: AsyncClient, owner_headers: dict[str, str], *, medicine_id: str, batch_number: str, expiry_date: str, quantity: int) -> dict:
    response = await api_client.post(
        f"/api/v1/pharmacy/medicines/{medicine_id}/batches", json={"batch_number": batch_number, "expiry_date": expiry_date, "quantity": quantity}, headers=owner_headers
    )
    assert response.status_code == 201
    return response.json()


async def _prescribe_with_medicine(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, *, medicine_id: str, prescribed_quantity: int,
    doctor_phone: str = "+919881100001", patient_phone: str = "+919881100002",
) -> str:
    """Walk-in -> consultation -> a prescription with one item linked to
    `medicine_id`. Returns the prescription_item_id."""
    branch_id = await _create_branch(api_client, owner_headers, f"PharmBranch-{doctor_phone}")
    doctor_id, doctor_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone=doctor_phone)
    patient_id = await _create_patient(api_client, owner_headers, phone=patient_phone)
    walk_in = await api_client.post("/api/v1/encounters/walk-in", json={"patient_id": patient_id, "branch_id": branch_id, "doctor_id": doctor_id}, headers=owner_headers)
    assert walk_in.status_code == 201
    encounter_id = walk_in.json()["encounter"]["id"]
    consultation = await api_client.post("/api/v1/consultations", json={"encounter_id": encounter_id}, headers=doctor_headers)
    assert consultation.status_code == 201

    prescription = await api_client.post(
        "/api/v1/prescriptions",
        json={"encounter_id": encounter_id, "items": [{"medicine_id": medicine_id, "prescribed_quantity": prescribed_quantity}]},
        headers=doctor_headers,
    )
    assert prescription.status_code == 201
    return prescription.json()["items"][0]["id"]


# ---- Catalog ----------------------------------------------------------------------


async def test_owner_can_create_a_medicine(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.post(
        "/api/v1/pharmacy/medicines",
        json={"name": "Paracetamol 500mg", "generic_name": "Paracetamol", "dosage_form": "Tablet", "strength": "500mg", "manufacturer": "Acme Pharma", "unit_price": 2.5},
        headers=owner_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["strength"] == "500mg"
    assert body["manufacturer"] == "Acme Pharma"
    assert body["total_stock"] == 0


async def test_pharmacy_staff_can_create_a_medicine(api_client: AsyncClient, login_as) -> None:
    headers, _ = await login_as(role_code="PHARMACY_STAFF")
    response = await api_client.post("/api/v1/pharmacy/medicines", json={"name": "Cetirizine"}, headers=headers)
    assert response.status_code == 201


async def test_doctor_can_view_but_not_create_medicines(api_client: AsyncClient, owner_headers: dict[str, str], login_as) -> None:
    headers, _ = await login_as(role_code="DOCTOR")
    read = await api_client.get("/api/v1/pharmacy/medicines", headers=headers)
    assert read.status_code == 200
    write = await api_client.post("/api/v1/pharmacy/medicines", json={"name": "x"}, headers=headers)
    assert write.status_code == 403


async def test_nurse_has_no_pharmacy_access(api_client: AsyncClient, login_as) -> None:
    headers, _ = await login_as(role_code="NURSE")
    read = await api_client.get("/api/v1/pharmacy/medicines", headers=headers)
    assert read.status_code == 403


async def test_receptionist_can_view_catalog_but_not_create_medicines(api_client: AsyncClient, login_as) -> None:
    # Migration 0029 deliberately granted Receptionist pharmacy.view_catalog
    # (read-only) so the OTC sales screen can search what it's selling —
    # see that migration's docstring. Receptionist still has no write
    # access to the catalog itself (pharmacy.manage_catalog stays
    # Owner/Pharmacy Staff only).
    headers, _ = await login_as(role_code="RECEPTIONIST")
    read = await api_client.get("/api/v1/pharmacy/medicines", headers=headers)
    assert read.status_code == 200
    write = await api_client.post("/api/v1/pharmacy/medicines", json={"name": "x"}, headers=headers)
    assert write.status_code == 403


async def test_duplicate_sku_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    first = await api_client.post("/api/v1/pharmacy/medicines", json={"name": "Ibuprofen", "sku": "IBU-200"}, headers=owner_headers)
    assert first.status_code == 201
    second = await api_client.post("/api/v1/pharmacy/medicines", json={"name": "Ibuprofen 400", "sku": "IBU-200"}, headers=owner_headers)
    assert second.status_code == 409


async def test_low_stock_filter(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    low_id = await _create_medicine(api_client, owner_headers, name="LowStockMed", reorder_threshold=100)
    high_id = await _create_medicine(api_client, owner_headers, name="HighStockMed", reorder_threshold=5)
    await _receive_stock(api_client, owner_headers, medicine_id=low_id, batch_number="B1", expiry_date=(date.today() + timedelta(days=30)).isoformat(), quantity=10)
    await _receive_stock(api_client, owner_headers, medicine_id=high_id, batch_number="B1", expiry_date=(date.today() + timedelta(days=30)).isoformat(), quantity=10)

    response = await api_client.get("/api/v1/pharmacy/medicines?low_stock_only=true", headers=owner_headers)
    assert response.status_code == 200
    ids = {m["id"] for m in response.json()["items"]}
    assert low_id in ids
    assert high_id not in ids


# ---- Receiving stock ----------------------------------------------------------------


async def test_receiving_stock_creates_a_batch_and_updates_total_stock(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    medicine_id = await _create_medicine(api_client, owner_headers, name="Amoxicillin")
    batch = await _receive_stock(api_client, owner_headers, medicine_id=medicine_id, batch_number="AMX-001", expiry_date=(date.today() + timedelta(days=180)).isoformat(), quantity=50)
    assert batch["quantity_on_hand"] == 50

    medicine = await api_client.get(f"/api/v1/pharmacy/medicines/{medicine_id}", headers=owner_headers)
    assert medicine.json()["total_stock"] == 50


async def test_duplicate_batch_number_for_the_same_medicine_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    medicine_id = await _create_medicine(api_client, owner_headers, name="Azithromycin")
    expiry = (date.today() + timedelta(days=90)).isoformat()
    await _receive_stock(api_client, owner_headers, medicine_id=medicine_id, batch_number="DUPE", expiry_date=expiry, quantity=20)
    response = await api_client.post(
        f"/api/v1/pharmacy/medicines/{medicine_id}/batches", json={"batch_number": "DUPE", "expiry_date": expiry, "quantity": 5}, headers=owner_headers
    )
    assert response.status_code == 409


async def test_receiving_stock_for_a_nonexistent_medicine_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.post(
        "/api/v1/pharmacy/medicines/00000000-0000-0000-0000-000000000000/batches",
        json={"batch_number": "B1", "expiry_date": (date.today() + timedelta(days=30)).isoformat(), "quantity": 1},
        headers=owner_headers,
    )
    assert response.status_code == 422


# ---- Prescription <-> catalog linkage -----------------------------------------------


async def test_prescribing_a_nonexistent_medicine_id_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "BadMedRxBranch")
    doctor_id, doctor_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919881100010")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919881100011")
    walk_in = await api_client.post("/api/v1/encounters/walk-in", json={"patient_id": patient_id, "branch_id": branch_id, "doctor_id": doctor_id}, headers=owner_headers)
    encounter_id = walk_in.json()["encounter"]["id"]
    await api_client.post("/api/v1/consultations", json={"encounter_id": encounter_id}, headers=doctor_headers)

    response = await api_client.post(
        "/api/v1/prescriptions",
        json={"encounter_id": encounter_id, "items": [{"medicine_id": "00000000-0000-0000-0000-000000000000", "prescribed_quantity": 1}]},
        headers=doctor_headers,
    )
    assert response.status_code == 422


async def test_prescription_item_with_catalog_medicine_round_trips(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    medicine_id = await _create_medicine(api_client, owner_headers, name="Metformin")
    branch_id = await _create_branch(api_client, owner_headers, "RoundTripBranch")
    doctor_id, doctor_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919881100012")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919881100013")
    walk_in = await api_client.post("/api/v1/encounters/walk-in", json={"patient_id": patient_id, "branch_id": branch_id, "doctor_id": doctor_id}, headers=owner_headers)
    encounter_id = walk_in.json()["encounter"]["id"]
    await api_client.post("/api/v1/consultations", json={"encounter_id": encounter_id}, headers=doctor_headers)

    prescription = await api_client.post(
        "/api/v1/prescriptions", json={"encounter_id": encounter_id, "items": [{"medicine_id": medicine_id, "prescribed_quantity": 10}]}, headers=doctor_headers
    )
    assert prescription.status_code == 201
    assert prescription.json()["items"][0]["medicine_id"] == medicine_id
    assert prescription.json()["items"][0]["medicine_name_freetext"] is None


# ---- Dispensing (FEFO) ---------------------------------------------------------------


async def test_dispense_draws_from_the_earliest_expiring_batch_first(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    medicine_id = await _create_medicine(api_client, owner_headers, name="Dispensable")
    early = await _receive_stock(api_client, owner_headers, medicine_id=medicine_id, batch_number="EARLY", expiry_date=(date.today() + timedelta(days=10)).isoformat(), quantity=5)
    await _receive_stock(api_client, owner_headers, medicine_id=medicine_id, batch_number="LATE", expiry_date=(date.today() + timedelta(days=100)).isoformat(), quantity=20)
    item_id = await _prescribe_with_medicine(api_client, owner_headers, test_clinic, medicine_id=medicine_id, prescribed_quantity=8, doctor_phone="+919881100014", patient_phone="+919881100015")

    response = await api_client.post("/api/v1/pharmacy/dispense", json={"prescription_item_id": item_id, "quantity": 8}, headers=owner_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["quantity_dispensed"] == 8
    assert body["prescription_item_dispensed_quantity"] == 8
    # 5 from the EARLY (soonest-expiring) batch, then 3 from LATE.
    allocations = {a["batch_id"]: a["quantity"] for a in body["allocations"]}
    assert allocations[early["id"]] == 5

    early_refetched = await api_client.get(f"/api/v1/pharmacy/batches/{early['id']}", headers=owner_headers)
    assert early_refetched.json()["quantity_on_hand"] == 0


async def test_dispensing_more_than_prescribed_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    medicine_id = await _create_medicine(api_client, owner_headers, name="OverDispense")
    await _receive_stock(api_client, owner_headers, medicine_id=medicine_id, batch_number="B1", expiry_date=(date.today() + timedelta(days=30)).isoformat(), quantity=100)
    item_id = await _prescribe_with_medicine(api_client, owner_headers, test_clinic, medicine_id=medicine_id, prescribed_quantity=5, doctor_phone="+919881100016", patient_phone="+919881100017")

    response = await api_client.post("/api/v1/pharmacy/dispense", json={"prescription_item_id": item_id, "quantity": 6}, headers=owner_headers)
    assert response.status_code == 409


async def test_dispensing_with_insufficient_stock_is_rejected(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Auto-replenish defaults ON (Settings.pharmacy_auto_replenish_stock — a
    # pre-launch testing accommodation, see its own docstring in
    # app/core/config.py); force it off here since this test's whole point
    # is verifying the real "out of stock" rule still applies when a clinic
    # turns that accommodation off.
    monkeypatch.setattr(get_settings(), "pharmacy_auto_replenish_stock", False)
    medicine_id = await _create_medicine(api_client, owner_headers, name="LowStockDispense")
    await _receive_stock(api_client, owner_headers, medicine_id=medicine_id, batch_number="B1", expiry_date=(date.today() + timedelta(days=30)).isoformat(), quantity=2)
    item_id = await _prescribe_with_medicine(api_client, owner_headers, test_clinic, medicine_id=medicine_id, prescribed_quantity=10, doctor_phone="+919881100018", patient_phone="+919881100019")

    response = await api_client.post("/api/v1/pharmacy/dispense", json={"prescription_item_id": item_id, "quantity": 5}, headers=owner_headers)
    assert response.status_code == 409


async def test_dispensing_a_freetext_only_item_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "FreetextDispenseBranch")
    doctor_id, doctor_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919881100020")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919881100021")
    walk_in = await api_client.post("/api/v1/encounters/walk-in", json={"patient_id": patient_id, "branch_id": branch_id, "doctor_id": doctor_id}, headers=owner_headers)
    encounter_id = walk_in.json()["encounter"]["id"]
    await api_client.post("/api/v1/consultations", json={"encounter_id": encounter_id}, headers=doctor_headers)
    prescription = await api_client.post(
        "/api/v1/prescriptions", json={"encounter_id": encounter_id, "items": [{"medicine_name_freetext": "Herbal tea", "prescribed_quantity": 1}]}, headers=doctor_headers
    )
    item_id = prescription.json()["items"][0]["id"]

    response = await api_client.post("/api/v1/pharmacy/dispense", json={"prescription_item_id": item_id, "quantity": 1}, headers=owner_headers)
    assert response.status_code == 422


async def test_doctor_cannot_dispense(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    medicine_id = await _create_medicine(api_client, owner_headers, name="DoctorNoDispense")
    await _receive_stock(api_client, owner_headers, medicine_id=medicine_id, batch_number="B1", expiry_date=(date.today() + timedelta(days=30)).isoformat(), quantity=10)
    item_id = await _prescribe_with_medicine(api_client, owner_headers, test_clinic, medicine_id=medicine_id, prescribed_quantity=5, doctor_phone="+919881100022", patient_phone="+919881100023")

    _, doctor_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919881100024")
    response = await api_client.post("/api/v1/pharmacy/dispense", json={"prescription_item_id": item_id, "quantity": 1}, headers=doctor_headers)
    assert response.status_code == 403


async def test_pharmacy_staff_can_dispense(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, login_as) -> None:
    medicine_id = await _create_medicine(api_client, owner_headers, name="PharmacistDispense")
    await _receive_stock(api_client, owner_headers, medicine_id=medicine_id, batch_number="B1", expiry_date=(date.today() + timedelta(days=30)).isoformat(), quantity=10)
    item_id = await _prescribe_with_medicine(api_client, owner_headers, test_clinic, medicine_id=medicine_id, prescribed_quantity=5, doctor_phone="+919881100025", patient_phone="+919881100026")

    headers, _ = await login_as(role_code="PHARMACY_STAFF")
    response = await api_client.post("/api/v1/pharmacy/dispense", json={"prescription_item_id": item_id, "quantity": 3}, headers=headers)
    assert response.status_code == 201


async def test_dispense_for_nonexistent_prescription_item_is_404(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.post("/api/v1/pharmacy/dispense", json={"prescription_item_id": "00000000-0000-0000-0000-000000000000", "quantity": 1}, headers=owner_headers)
    assert response.status_code == 404


# ---- OTC / Retail sales ------------------------------------------------------------


async def test_sales_routes_are_blocked_until_the_feature_flag_is_enabled(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    medicine_id = await _create_medicine(api_client, owner_headers, name="GatedOTC")
    await _receive_stock(api_client, owner_headers, medicine_id=medicine_id, batch_number="B1", expiry_date=(date.today() + timedelta(days=30)).isoformat(), quantity=10)

    response = await api_client.post(
        "/api/v1/pharmacy/sales", json={"items": [{"medicine_id": medicine_id, "quantity": 1}], "payment_mode": "CASH"}, headers=owner_headers
    )
    assert response.status_code == 403

    await _enable_pharmacy_feature(api_client, owner_headers)
    response = await api_client.post(
        "/api/v1/pharmacy/sales", json={"items": [{"medicine_id": medicine_id, "quantity": 1}], "payment_mode": "CASH"}, headers=owner_headers
    )
    assert response.status_code == 201


async def test_checkout_deducts_stock_fefo_across_batches(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    await _enable_pharmacy_feature(api_client, owner_headers)
    medicine_id = await _create_medicine(api_client, owner_headers, name="OTC-FEFO")
    early = await _receive_stock(api_client, owner_headers, medicine_id=medicine_id, batch_number="OTC-EARLY", expiry_date=(date.today() + timedelta(days=10)).isoformat(), quantity=5)
    late = await _receive_stock(api_client, owner_headers, medicine_id=medicine_id, batch_number="OTC-LATE", expiry_date=(date.today() + timedelta(days=100)).isoformat(), quantity=20)

    response = await api_client.post(
        "/api/v1/pharmacy/sales",
        json={"customer_name": "Walk-in Customer", "customer_phone": "+919000000001", "items": [{"medicine_id": medicine_id, "quantity": 8}], "payment_mode": "CASH"},
        headers=owner_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PAID"
    assert len(body["items"]) == 2
    by_batch = {item["batch_id"]: item["quantity"] for item in body["items"]}
    assert by_batch[early["id"]] == 5
    assert by_batch[late["id"]] == 3

    early_refetched = await api_client.get(f"/api/v1/pharmacy/batches/{early['id']}", headers=owner_headers)
    assert early_refetched.json()["quantity_on_hand"] == 0
    late_refetched = await api_client.get(f"/api/v1/pharmacy/batches/{late['id']}", headers=owner_headers)
    assert late_refetched.json()["quantity_on_hand"] == 17


async def test_checkout_computes_total_discount_and_net_amount(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    await _enable_pharmacy_feature(api_client, owner_headers)
    medicine_id = await _create_medicine(api_client, owner_headers, name="OTC-Pricing")
    await api_client.patch(f"/api/v1/pharmacy/medicines/{medicine_id}", json={"unit_price": 10}, headers=owner_headers)
    await _receive_stock(api_client, owner_headers, medicine_id=medicine_id, batch_number="B1", expiry_date=(date.today() + timedelta(days=30)).isoformat(), quantity=50)

    response = await api_client.post(
        "/api/v1/pharmacy/sales",
        json={"items": [{"medicine_id": medicine_id, "quantity": 4}], "discount_amount": 5, "payment_mode": "UPI"},
        headers=owner_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["total_amount"] == "40.00"
    assert body["discount_amount"] == "5.00"
    assert body["net_amount"] == "35.00"
    assert body["payment_mode"] == "UPI"


async def test_discount_exceeding_total_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    await _enable_pharmacy_feature(api_client, owner_headers)
    medicine_id = await _create_medicine(api_client, owner_headers, name="OTC-BigDiscount")
    await _receive_stock(api_client, owner_headers, medicine_id=medicine_id, batch_number="B1", expiry_date=(date.today() + timedelta(days=30)).isoformat(), quantity=10)

    response = await api_client.post(
        "/api/v1/pharmacy/sales",
        json={"items": [{"medicine_id": medicine_id, "quantity": 1}], "discount_amount": 1_000_000, "payment_mode": "CASH"},
        headers=owner_headers,
    )
    assert response.status_code == 409


async def test_checkout_with_insufficient_stock_is_rejected(
    api_client: AsyncClient, owner_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "pharmacy_auto_replenish_stock", False)
    await _enable_pharmacy_feature(api_client, owner_headers)
    medicine_id = await _create_medicine(api_client, owner_headers, name="OTC-LowStock")
    await _receive_stock(api_client, owner_headers, medicine_id=medicine_id, batch_number="B1", expiry_date=(date.today() + timedelta(days=30)).isoformat(), quantity=2)

    response = await api_client.post(
        "/api/v1/pharmacy/sales", json={"items": [{"medicine_id": medicine_id, "quantity": 5}], "payment_mode": "CASH"}, headers=owner_headers
    )
    assert response.status_code == 409

    unchanged = await api_client.get(f"/api/v1/pharmacy/medicines/{medicine_id}", headers=owner_headers)
    assert unchanged.json()["total_stock"] == 2


async def test_checkout_with_unknown_medicine_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    await _enable_pharmacy_feature(api_client, owner_headers)
    response = await api_client.post(
        "/api/v1/pharmacy/sales",
        json={"items": [{"medicine_id": "00000000-0000-0000-0000-000000000000", "quantity": 1}], "payment_mode": "CASH"},
        headers=owner_headers,
    )
    assert response.status_code == 422


async def test_pharmacy_staff_and_receptionist_can_checkout_doctor_and_nurse_cannot(api_client: AsyncClient, owner_headers: dict[str, str], login_as) -> None:
    await _enable_pharmacy_feature(api_client, owner_headers)
    medicine_id = await _create_medicine(api_client, owner_headers, name="OTC-RBAC")
    await _receive_stock(api_client, owner_headers, medicine_id=medicine_id, batch_number="B1", expiry_date=(date.today() + timedelta(days=30)).isoformat(), quantity=100)

    for role in ("PHARMACY_STAFF", "RECEPTIONIST"):
        headers, _ = await login_as(role_code=role)
        response = await api_client.post(
            "/api/v1/pharmacy/sales", json={"items": [{"medicine_id": medicine_id, "quantity": 1}], "payment_mode": "CASH"}, headers=headers
        )
        assert response.status_code == 201, role
        listing = await api_client.get("/api/v1/pharmacy/sales", headers=headers)
        assert listing.status_code == 200, role

    for role in ("DOCTOR", "NURSE"):
        headers, _ = await login_as(role_code=role)
        response = await api_client.post(
            "/api/v1/pharmacy/sales", json={"items": [{"medicine_id": medicine_id, "quantity": 1}], "payment_mode": "CASH"}, headers=headers
        )
        assert response.status_code == 403, role
        listing = await api_client.get("/api/v1/pharmacy/sales", headers=headers)
        assert listing.status_code == 403, role


async def test_get_sale_returns_a_detailed_bill_breakdown(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    await _enable_pharmacy_feature(api_client, owner_headers)
    medicine_id = await _create_medicine(api_client, owner_headers, name="OTC-Detail")
    await _receive_stock(api_client, owner_headers, medicine_id=medicine_id, batch_number="B1", expiry_date=(date.today() + timedelta(days=30)).isoformat(), quantity=10)

    created = await api_client.post(
        "/api/v1/pharmacy/sales", json={"customer_name": "Jane", "items": [{"medicine_id": medicine_id, "quantity": 3}], "payment_mode": "CARD"}, headers=owner_headers
    )
    sale_id = created.json()["id"]

    detail = await api_client.get(f"/api/v1/pharmacy/sales/{sale_id}", headers=owner_headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["customer_name"] == "Jane"
    assert body["payment_mode"] == "CARD"
    assert len(body["items"]) == 1
    assert body["items"][0]["quantity"] == 3
    assert body["items"][0]["medicine_id"] == medicine_id


async def test_get_nonexistent_sale_is_404(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    await _enable_pharmacy_feature(api_client, owner_headers)
    response = await api_client.get("/api/v1/pharmacy/sales/00000000-0000-0000-0000-000000000000", headers=owner_headers)
    assert response.status_code == 404


async def test_search_sales_filters_by_date_range_and_payment_mode_with_total_metric(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    await _enable_pharmacy_feature(api_client, owner_headers)
    medicine_id = await _create_medicine(api_client, owner_headers, name="OTC-Search")
    await api_client.patch(f"/api/v1/pharmacy/medicines/{medicine_id}", json={"unit_price": 20}, headers=owner_headers)
    await _receive_stock(api_client, owner_headers, medicine_id=medicine_id, batch_number="B1", expiry_date=(date.today() + timedelta(days=30)).isoformat(), quantity=100)

    cash_sale = await api_client.post(
        "/api/v1/pharmacy/sales", json={"items": [{"medicine_id": medicine_id, "quantity": 2}], "payment_mode": "CASH"}, headers=owner_headers
    )
    assert cash_sale.status_code == 201
    upi_sale = await api_client.post(
        "/api/v1/pharmacy/sales", json={"items": [{"medicine_id": medicine_id, "quantity": 3}], "payment_mode": "UPI"}, headers=owner_headers
    )
    assert upi_sale.status_code == 201

    cash_only = await api_client.get("/api/v1/pharmacy/sales?payment_mode=CASH", headers=owner_headers)
    assert cash_only.status_code == 200
    cash_body = cash_only.json()
    ids = {s["id"] for s in cash_body["items"]}
    assert cash_sale.json()["id"] in ids
    assert upi_sale.json()["id"] not in ids
    assert cash_body["total_net_amount"] == "40.00"

    future_only = await api_client.get(
        "/api/v1/pharmacy/sales", params={"date_from": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}, headers=owner_headers
    )
    assert future_only.status_code == 200
    assert future_only.json()["total"] == 0

"""End-to-end tests of the Pathology / Diagnostic Lab Management HTTP
surface (tenant feature gate, catalog, order lifecycle, auto-flagging,
RBAC) against a real Postgres — see tests/conftest.py (skipped
automatically if unreachable).
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from app.core.db import tenant_session
from app.modules.patients.models import Patient
from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")

_WIDE_OPEN_HOURS = {day: {"open": "00:00", "close": "23:59"} for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}


async def _enable_lab_feature(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.put("/api/v1/clinics/me/settings/features.lab_enabled", json={"value": True}, headers=owner_headers)
    assert response.status_code == 200


async def _create_branch(api_client: AsyncClient, owner_headers: dict[str, str], name: str) -> str:
    response = await api_client.post("/api/v1/branches", json={"name": name}, headers=owner_headers)
    assert response.status_code == 201
    return response.json()["id"]


async def _create_active_doctor(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, *, phone: str, gender: str = "Male") -> tuple[str, dict[str, str]]:
    created = await api_client.post("/api/v1/doctors", json={"first_name": "Doc", "phone": phone, "working_hours": _WIDE_OPEN_HOURS}, headers=owner_headers)
    assert created.status_code == 201
    user_id = created.json()["doctor"]["user_id"]
    token = created.json()["invite"]["debug_invite_token"]
    accept = await api_client.post("/api/v1/auth/accept-invite", json={"clinic_slug": test_clinic.slug, "token": token, "password": "password-123"})
    assert accept.status_code == 200
    login = await api_client.post("/api/v1/auth/staff/login", json={"clinic_slug": test_clinic.slug, "identifier": phone, "password": "password-123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    return user_id, headers


async def _create_patient(api_client: AsyncClient, owner_headers: dict[str, str], *, phone: str, gender: str = "Male") -> str:
    created = await api_client.post("/api/v1/patients", json={"first_name": "Pat", "phone": phone, "gender": gender}, headers=owner_headers)
    assert created.status_code == 201
    return created.json()["patient"]["id"]


async def _create_walkin_encounter(api_client: AsyncClient, owner_headers: dict[str, str], *, branch_id: str, patient_id: str, doctor_id: str | None = None) -> str:
    payload = {"patient_id": patient_id, "branch_id": branch_id}
    if doctor_id:
        payload["doctor_id"] = doctor_id
    response = await api_client.post("/api/v1/encounters/walk-in", json=payload, headers=owner_headers)
    assert response.status_code == 201
    return response.json()["encounter"]["id"]


async def _create_lab_test(api_client: AsyncClient, owner_headers: dict[str, str], *, name: str, reference_ranges: list[dict] | None = None) -> str:
    response = await api_client.post(
        "/api/v1/lab/tests", json={"name": name, "test_code": name.upper()[:10], "specimen_type": "Blood", "turnaround_hours": 24, "price": 500, "reference_ranges": reference_ranges or []},
        headers=owner_headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _create_order(api_client: AsyncClient, headers: dict[str, str], *, encounter_id: str, test_id: str) -> str:
    response = await api_client.post("/api/v1/lab/orders", json={"encounter_id": encounter_id, "test_id": test_id}, headers=headers)
    assert response.status_code == 201
    return response.json()["id"]


# ---- Tenant feature gate ---------------------------------------------------------


async def test_lab_routes_are_blocked_until_the_feature_flag_is_enabled(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.get("/api/v1/lab/tests", headers=owner_headers)
    assert response.status_code == 403

    await _enable_lab_feature(api_client, owner_headers)
    response = await api_client.get("/api/v1/lab/tests", headers=owner_headers)
    assert response.status_code == 200


async def test_disabling_the_feature_flag_blocks_it_again(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    await _enable_lab_feature(api_client, owner_headers)
    enabled = await api_client.get("/api/v1/lab/tests", headers=owner_headers)
    assert enabled.status_code == 200

    disable = await api_client.put("/api/v1/clinics/me/settings/features.lab_enabled", json={"value": False}, headers=owner_headers)
    assert disable.status_code == 200
    disabled = await api_client.get("/api/v1/lab/tests", headers=owner_headers)
    assert disabled.status_code == 403


# ---- Catalog ----------------------------------------------------------------------


async def test_owner_can_create_a_lab_test(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    await _enable_lab_feature(api_client, owner_headers)
    response = await api_client.post(
        "/api/v1/lab/tests",
        json={"name": "Complete Blood Count", "test_code": "CBC", "specimen_type": "Blood", "turnaround_hours": 24, "price": 400, "reference_ranges": []},
        headers=owner_headers,
    )
    assert response.status_code == 201
    assert response.json()["test_code"] == "CBC"


async def test_lab_staff_cannot_manage_catalog_but_can_view(api_client: AsyncClient, owner_headers: dict[str, str], login_as) -> None:
    await _enable_lab_feature(api_client, owner_headers)
    headers, _ = await login_as(role_code="LAB_STAFF")
    write = await api_client.post("/api/v1/lab/tests", json={"name": "x"}, headers=headers)
    assert write.status_code == 403
    read = await api_client.get("/api/v1/lab/tests", headers=headers)
    assert read.status_code == 200


async def test_receptionist_and_nurse_have_no_lab_access(api_client: AsyncClient, owner_headers: dict[str, str], login_as) -> None:
    await _enable_lab_feature(api_client, owner_headers)
    for role in ("RECEPTIONIST", "NURSE"):
        headers, _ = await login_as(role_code=role)
        response = await api_client.get("/api/v1/lab/tests", headers=headers)
        assert response.status_code == 403


# ---- Orders ----------------------------------------------------------------------


async def test_doctor_can_order_a_test(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    await _enable_lab_feature(api_client, owner_headers)
    branch_id = await _create_branch(api_client, owner_headers, "LabBranch")
    doctor_id, doctor_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919882200001")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919882200002")
    encounter_id = await _create_walkin_encounter(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id, doctor_id=doctor_id)
    test_id = await _create_lab_test(api_client, owner_headers, name="Lipid Profile")

    response = await api_client.post("/api/v1/lab/orders", json={"encounter_id": encounter_id, "test_id": test_id}, headers=doctor_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "ORDERED"
    assert body["doctor_id"] == doctor_id
    assert body["patient_id"] == patient_id


async def test_full_order_lifecycle(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    await _enable_lab_feature(api_client, owner_headers)
    branch_id = await _create_branch(api_client, owner_headers, "LifecycleBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919882200003")
    encounter_id = await _create_walkin_encounter(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id)
    test_id = await _create_lab_test(api_client, owner_headers, name="Thyroid Panel")
    order_id = await _create_order(api_client, owner_headers, encounter_id=encounter_id, test_id=test_id)

    collected = await api_client.post(f"/api/v1/lab/orders/{order_id}/collect-sample", headers=owner_headers)
    assert collected.status_code == 200
    assert collected.json()["status"] == "SAMPLE_COLLECTED"

    resulted = await api_client.post(f"/api/v1/lab/orders/{order_id}/results", json={"results": [{"parameter": "TSH", "value": "2.5", "unit": "mIU/L"}]}, headers=owner_headers)
    assert resulted.status_code == 201
    assert resulted.json()["status"] == "RESULTED"
    assert len(resulted.json()["results"]) == 1

    completed = await api_client.post(f"/api/v1/lab/orders/{order_id}/complete", headers=owner_headers)
    assert completed.status_code == 200
    assert completed.json()["status"] == "COMPLETED"
    assert completed.json()["results"][0]["finalized_at"] is not None


async def test_cannot_collect_sample_twice(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    await _enable_lab_feature(api_client, owner_headers)
    branch_id = await _create_branch(api_client, owner_headers, "DoubleCollectBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919882200004")
    encounter_id = await _create_walkin_encounter(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id)
    test_id = await _create_lab_test(api_client, owner_headers, name="Blood Sugar")
    order_id = await _create_order(api_client, owner_headers, encounter_id=encounter_id, test_id=test_id)

    await api_client.post(f"/api/v1/lab/orders/{order_id}/collect-sample", headers=owner_headers)
    second = await api_client.post(f"/api/v1/lab/orders/{order_id}/collect-sample", headers=owner_headers)
    assert second.status_code == 409


async def test_cannot_add_results_before_sample_collected(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    await _enable_lab_feature(api_client, owner_headers)
    branch_id = await _create_branch(api_client, owner_headers, "NoSampleBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919882200005")
    encounter_id = await _create_walkin_encounter(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id)
    test_id = await _create_lab_test(api_client, owner_headers, name="Urinalysis")
    order_id = await _create_order(api_client, owner_headers, encounter_id=encounter_id, test_id=test_id)

    response = await api_client.post(f"/api/v1/lab/orders/{order_id}/results", json={"results": [{"parameter": "pH", "value": "6.0"}]}, headers=owner_headers)
    assert response.status_code == 409


async def test_cannot_complete_before_results_entered(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    await _enable_lab_feature(api_client, owner_headers)
    branch_id = await _create_branch(api_client, owner_headers, "NoResultsCompleteBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919882200006")
    encounter_id = await _create_walkin_encounter(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id)
    test_id = await _create_lab_test(api_client, owner_headers, name="Electrolytes")
    order_id = await _create_order(api_client, owner_headers, encounter_id=encounter_id, test_id=test_id)
    await api_client.post(f"/api/v1/lab/orders/{order_id}/collect-sample", headers=owner_headers)

    response = await api_client.post(f"/api/v1/lab/orders/{order_id}/complete", headers=owner_headers)
    assert response.status_code == 409


async def test_cancel_from_ordered_and_cannot_cancel_completed(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    await _enable_lab_feature(api_client, owner_headers)
    branch_id = await _create_branch(api_client, owner_headers, "CancelBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919882200007")
    encounter_id = await _create_walkin_encounter(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id)
    test_id = await _create_lab_test(api_client, owner_headers, name="Cancellable Test")
    order_id = await _create_order(api_client, owner_headers, encounter_id=encounter_id, test_id=test_id)

    cancelled = await api_client.post(f"/api/v1/lab/orders/{order_id}/cancel", json={"reason": "duplicate order"}, headers=owner_headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"

    # A completed order can no longer be cancelled.
    test_id_2 = await _create_lab_test(api_client, owner_headers, name="Completed Test")
    order_id_2 = await _create_order(api_client, owner_headers, encounter_id=encounter_id, test_id=test_id_2)
    await api_client.post(f"/api/v1/lab/orders/{order_id_2}/collect-sample", headers=owner_headers)
    await api_client.post(f"/api/v1/lab/orders/{order_id_2}/results", json={"results": [{"parameter": "x", "value": "1"}]}, headers=owner_headers)
    await api_client.post(f"/api/v1/lab/orders/{order_id_2}/complete", headers=owner_headers)
    response = await api_client.post(f"/api/v1/lab/orders/{order_id_2}/cancel", json={"reason": "too late"}, headers=owner_headers)
    assert response.status_code == 409


# ---- Auto-flagging ----------------------------------------------------------------


async def test_result_below_range_is_flagged_low(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    await _enable_lab_feature(api_client, owner_headers)
    branch_id = await _create_branch(api_client, owner_headers, "LowFlagBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919882200008")
    encounter_id = await _create_walkin_encounter(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id)
    test_id = await _create_lab_test(api_client, owner_headers, name="Hemoglobin", reference_ranges=[{"min": 13.0, "max": 17.0, "unit": "g/dL"}])
    order_id = await _create_order(api_client, owner_headers, encounter_id=encounter_id, test_id=test_id)
    await api_client.post(f"/api/v1/lab/orders/{order_id}/collect-sample", headers=owner_headers)

    response = await api_client.post(f"/api/v1/lab/orders/{order_id}/results", json={"results": [{"parameter": "Hb", "value": "10.5"}]}, headers=owner_headers)
    assert response.status_code == 201
    result = response.json()["results"][0]
    assert result["flag"] == "LOW"
    assert result["unit"] == "g/dL"
    assert result["reference_range"] == "13.0-17.0 g/dL"


async def test_result_above_range_is_flagged_high(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    await _enable_lab_feature(api_client, owner_headers)
    branch_id = await _create_branch(api_client, owner_headers, "HighFlagBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919882200009")
    encounter_id = await _create_walkin_encounter(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id)
    test_id = await _create_lab_test(api_client, owner_headers, name="Blood Glucose", reference_ranges=[{"min": 70, "max": 100, "unit": "mg/dL"}])
    order_id = await _create_order(api_client, owner_headers, encounter_id=encounter_id, test_id=test_id)
    await api_client.post(f"/api/v1/lab/orders/{order_id}/collect-sample", headers=owner_headers)

    response = await api_client.post(f"/api/v1/lab/orders/{order_id}/results", json={"results": [{"parameter": "Glucose", "value": "145"}]}, headers=owner_headers)
    assert response.json()["results"][0]["flag"] == "HIGH"


async def test_result_within_range_is_normal(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    await _enable_lab_feature(api_client, owner_headers)
    branch_id = await _create_branch(api_client, owner_headers, "NormalFlagBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919882200010")
    encounter_id = await _create_walkin_encounter(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id)
    test_id = await _create_lab_test(api_client, owner_headers, name="Sodium", reference_ranges=[{"min": 135, "max": 145, "unit": "mmol/L"}])
    order_id = await _create_order(api_client, owner_headers, encounter_id=encounter_id, test_id=test_id)
    await api_client.post(f"/api/v1/lab/orders/{order_id}/collect-sample", headers=owner_headers)

    response = await api_client.post(f"/api/v1/lab/orders/{order_id}/results", json={"results": [{"parameter": "Na", "value": "140"}]}, headers=owner_headers)
    assert response.json()["results"][0]["flag"] == "NORMAL"


async def test_qualitative_result_defaults_to_normal_without_crashing(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    await _enable_lab_feature(api_client, owner_headers)
    branch_id = await _create_branch(api_client, owner_headers, "QualitativeBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919882200011")
    encounter_id = await _create_walkin_encounter(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id)
    test_id = await _create_lab_test(api_client, owner_headers, name="Pregnancy Test", reference_ranges=[{"min": 0, "max": 5, "unit": "mIU/mL"}])
    order_id = await _create_order(api_client, owner_headers, encounter_id=encounter_id, test_id=test_id)
    await api_client.post(f"/api/v1/lab/orders/{order_id}/collect-sample", headers=owner_headers)

    response = await api_client.post(f"/api/v1/lab/orders/{order_id}/results", json={"results": [{"parameter": "Result", "value": "Negative"}]}, headers=owner_headers)
    assert response.status_code == 201
    assert response.json()["results"][0]["flag"] == "NORMAL"


async def test_flag_override_sets_critical_manually(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    await _enable_lab_feature(api_client, owner_headers)
    branch_id = await _create_branch(api_client, owner_headers, "CriticalBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919882200012")
    encounter_id = await _create_walkin_encounter(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id)
    test_id = await _create_lab_test(api_client, owner_headers, name="Potassium", reference_ranges=[{"min": 3.5, "max": 5.0, "unit": "mmol/L"}])
    order_id = await _create_order(api_client, owner_headers, encounter_id=encounter_id, test_id=test_id)
    await api_client.post(f"/api/v1/lab/orders/{order_id}/collect-sample", headers=owner_headers)

    response = await api_client.post(
        f"/api/v1/lab/orders/{order_id}/results", json={"results": [{"parameter": "K+", "value": "7.2", "flag_override": "CRITICAL"}]}, headers=owner_headers
    )
    assert response.json()["results"][0]["flag"] == "CRITICAL"


async def test_reference_range_selects_by_patient_sex(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    await _enable_lab_feature(api_client, owner_headers)
    branch_id = await _create_branch(api_client, owner_headers, "SexRangeBranch")
    male_patient_id = await _create_patient(api_client, owner_headers, phone="+919882200013", gender="Male")
    female_patient_id = await _create_patient(api_client, owner_headers, phone="+919882200014", gender="Female")
    test_id = await _create_lab_test(
        api_client, owner_headers, name="Hemoglobin Sex-Specific",
        reference_ranges=[{"min": 13.5, "max": 17.5, "unit": "g/dL", "sex": "Male"}, {"min": 12.0, "max": 15.5, "unit": "g/dL", "sex": "Female"}],
    )

    male_encounter = await _create_walkin_encounter(api_client, owner_headers, branch_id=branch_id, patient_id=male_patient_id)
    male_order = await _create_order(api_client, owner_headers, encounter_id=male_encounter, test_id=test_id)
    await api_client.post(f"/api/v1/lab/orders/{male_order}/collect-sample", headers=owner_headers)
    male_result = await api_client.post(f"/api/v1/lab/orders/{male_order}/results", json={"results": [{"parameter": "Hb", "value": "13.0"}]}, headers=owner_headers)
    assert male_result.json()["results"][0]["flag"] == "LOW"  # below the Male range's 13.5 floor

    female_encounter = await _create_walkin_encounter(api_client, owner_headers, branch_id=branch_id, patient_id=female_patient_id)
    female_order = await _create_order(api_client, owner_headers, encounter_id=female_encounter, test_id=test_id)
    await api_client.post(f"/api/v1/lab/orders/{female_order}/collect-sample", headers=owner_headers)
    female_result = await api_client.post(f"/api/v1/lab/orders/{female_order}/results", json={"results": [{"parameter": "Hb", "value": "13.0"}]}, headers=owner_headers)
    assert female_result.json()["results"][0]["flag"] == "NORMAL"  # within the Female range


# ---- RBAC reads ---------------------------------------------------------------------


async def test_doctor_sees_all_orders_tenant_wide(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    await _enable_lab_feature(api_client, owner_headers)
    branch_id = await _create_branch(api_client, owner_headers, "DoctorReadBranch")
    doctor_a_id, doctor_a_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919882200015")
    doctor_b_id, _ = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919882200016")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919882200017")
    test_id = await _create_lab_test(api_client, owner_headers, name="Shared Visibility Test")

    encounter_a = await _create_walkin_encounter(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id, doctor_id=doctor_a_id)
    encounter_b = await _create_walkin_encounter(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id, doctor_id=doctor_b_id)
    order_a = await _create_order(api_client, owner_headers, encounter_id=encounter_a, test_id=test_id)
    order_b = await _create_order(api_client, owner_headers, encounter_id=encounter_b, test_id=test_id)

    response = await api_client.get("/api/v1/lab/orders", headers=doctor_a_headers)
    assert response.status_code == 200
    ids = {o["id"] for o in response.json()["items"]}
    assert order_a in ids
    assert order_b in ids  # tenant-wide, not row-scoped — see migration 0018's docstring


async def test_patient_sees_only_own_completed_orders(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, login_as) -> None:
    await _enable_lab_feature(api_client, owner_headers)
    branch_id = await _create_branch(api_client, owner_headers, "PatientReadBranch")
    patient_a_id = await _create_patient(api_client, owner_headers, phone="+919882200018")
    patient_b_id = await _create_patient(api_client, owner_headers, phone="+919882200019")
    test_id = await _create_lab_test(api_client, owner_headers, name="Patient Visibility Test")

    encounter_a = await _create_walkin_encounter(api_client, owner_headers, branch_id=branch_id, patient_id=patient_a_id)
    pending_order = await _create_order(api_client, owner_headers, encounter_id=encounter_a, test_id=test_id)  # stays ORDERED

    completed_encounter = await _create_walkin_encounter(api_client, owner_headers, branch_id=branch_id, patient_id=patient_a_id)
    completed_order = await _create_order(api_client, owner_headers, encounter_id=completed_encounter, test_id=test_id)
    await api_client.post(f"/api/v1/lab/orders/{completed_order}/collect-sample", headers=owner_headers)
    await api_client.post(f"/api/v1/lab/orders/{completed_order}/results", json={"results": [{"parameter": "x", "value": "1"}]}, headers=owner_headers)
    await api_client.post(f"/api/v1/lab/orders/{completed_order}/complete", headers=owner_headers)

    other_encounter = await _create_walkin_encounter(api_client, owner_headers, branch_id=branch_id, patient_id=patient_b_id)
    other_order = await _create_order(api_client, owner_headers, encounter_id=other_encounter, test_id=test_id)
    await api_client.post(f"/api/v1/lab/orders/{other_order}/collect-sample", headers=owner_headers)
    await api_client.post(f"/api/v1/lab/orders/{other_order}/results", json={"results": [{"parameter": "x", "value": "1"}]}, headers=owner_headers)
    await api_client.post(f"/api/v1/lab/orders/{other_order}/complete", headers=owner_headers)

    patient_headers, patient_user_id = await login_as(role_code="PATIENT")
    async with tenant_session(test_clinic.id) as session:
        await session.execute(update(Patient).where(Patient.id == uuid.UUID(patient_a_id)).values(user_id=patient_user_id))

    listed = await api_client.get("/api/v1/lab/orders", headers=patient_headers)
    assert listed.status_code == 200
    ids = {o["id"] for o in listed.json()["items"]}
    assert ids == {completed_order}  # not the pending one, not the other patient's

    pending_direct = await api_client.get(f"/api/v1/lab/orders/{pending_order}", headers=patient_headers)
    assert pending_direct.status_code == 404
    completed_direct = await api_client.get(f"/api/v1/lab/orders/{completed_order}", headers=patient_headers)
    assert completed_direct.status_code == 200

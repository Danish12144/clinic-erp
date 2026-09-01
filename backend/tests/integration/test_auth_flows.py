"""End-to-end tests of the Auth module's HTTP surface, against a real
Postgres (see tests/conftest.py — skipped automatically if unreachable).
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.db import platform_admin_session
from app.modules.auth.models import Permission, PermissionOverride
from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")


async def test_staff_login_success_returns_tokens_and_effective_permissions(
    api_client: AsyncClient, test_clinic: Clinic, make_staff_user
) -> None:
    user_id, password = await make_staff_user(role_code="DOCTOR", email="doc@apex.clinic")

    response = await api_client.post(
        "/api/v1/auth/staff/login",
        json={"clinic_slug": test_clinic.slug, "identifier": "doc@apex.clinic", "password": password},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["id"] == str(user_id)
    assert body["user"]["role_code"] == "DOCTOR"
    assert "access_token" in body and "refresh_token" in body

    # Doctor should have vitals.record and prescription.manage by default
    # (PRD §3 matrix), but not staff.manage (Owner-only).
    me = await api_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    permissions = set(me.json()["permissions"])
    assert "vitals.record" in permissions
    assert "prescription.manage" in permissions
    assert "staff.manage" not in permissions


async def test_staff_login_rejects_wrong_password(api_client: AsyncClient, test_clinic: Clinic, make_staff_user) -> None:
    await make_staff_user(role_code="OWNER", email="owner@apex.clinic", password="correct-password")

    response = await api_client.post(
        "/api/v1/auth/staff/login",
        json={"clinic_slug": test_clinic.slug, "identifier": "owner@apex.clinic", "password": "wrong-password"},
    )

    assert response.status_code == 401


async def test_staff_login_rejects_unknown_clinic(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/auth/staff/login",
        json={"clinic_slug": f"nonexistent-{uuid.uuid4().hex}", "identifier": "a@b.com", "password": "x"},
    )
    assert response.status_code == 404


async def test_me_without_token_is_unauthorized(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_receptionist_lacks_vitals_permission_by_default(
    api_client: AsyncClient, test_clinic: Clinic, make_staff_user
) -> None:
    # Receptionist does not have vitals.record by default (PRD §3) —
    # enabling it is the per-tenant PermissionOverride case covered in
    # test_permission_override_grants_receptionist_vitals_recording below.
    _, password = await make_staff_user(role_code="RECEPTIONIST", email="front-desk@apex.clinic")
    login = await api_client.post(
        "/api/v1/auth/staff/login",
        json={"clinic_slug": test_clinic.slug, "identifier": "front-desk@apex.clinic", "password": password},
    )
    me = await api_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"}
    )
    assert "vitals.record" not in set(me.json()["permissions"])


async def test_refresh_rotates_token_and_invalidates_the_old_one(
    api_client: AsyncClient, test_clinic: Clinic, make_staff_user
) -> None:
    _, password = await make_staff_user(role_code="OWNER", email="owner2@apex.clinic")
    login = await api_client.post(
        "/api/v1/auth/staff/login",
        json={"clinic_slug": test_clinic.slug, "identifier": "owner2@apex.clinic", "password": password},
    )
    old_refresh = login.json()["refresh_token"]

    refreshed = await api_client.post(
        "/api/v1/auth/staff/refresh", json={"clinic_slug": test_clinic.slug, "refresh_token": old_refresh}
    )
    assert refreshed.status_code == 200
    new_refresh = refreshed.json()["refresh_token"]
    assert new_refresh != old_refresh

    # The rotated-out token must no longer work.
    replay = await api_client.post(
        "/api/v1/auth/staff/refresh", json={"clinic_slug": test_clinic.slug, "refresh_token": old_refresh}
    )
    assert replay.status_code == 401

    # But the new one does.
    second_refresh = await api_client.post(
        "/api/v1/auth/staff/refresh", json={"clinic_slug": test_clinic.slug, "refresh_token": new_refresh}
    )
    assert second_refresh.status_code == 200


async def test_logout_revokes_the_refresh_token(api_client: AsyncClient, test_clinic: Clinic, make_staff_user) -> None:
    _, password = await make_staff_user(role_code="OWNER", email="owner3@apex.clinic")
    login = await api_client.post(
        "/api/v1/auth/staff/login",
        json={"clinic_slug": test_clinic.slug, "identifier": "owner3@apex.clinic", "password": password},
    )
    refresh_token = login.json()["refresh_token"]

    logout = await api_client.post(
        "/api/v1/auth/staff/logout", json={"clinic_slug": test_clinic.slug, "refresh_token": refresh_token}
    )
    assert logout.status_code == 204

    reuse = await api_client.post(
        "/api/v1/auth/staff/refresh", json={"clinic_slug": test_clinic.slug, "refresh_token": refresh_token}
    )
    assert reuse.status_code == 401


async def test_patient_otp_login_full_flow(api_client: AsyncClient, test_clinic: Clinic, make_patient_user) -> None:
    phone = "+919812345000"
    await make_patient_user(phone=phone)

    requested = await api_client.post(
        "/api/v1/auth/patient/otp/request", json={"clinic_slug": test_clinic.slug, "phone": phone}
    )
    assert requested.status_code == 200
    code = requested.json()["debug_code"]  # only present outside production — see AuthService
    assert code is not None and len(code) == 6

    verified = await api_client.post(
        "/api/v1/auth/patient/otp/verify", json={"clinic_slug": test_clinic.slug, "phone": phone, "code": code}
    )
    assert verified.status_code == 200
    assert verified.json()["user"]["role_code"] == "PATIENT"


async def test_patient_otp_wrong_code_is_rejected_and_does_not_consume_the_valid_one(
    api_client: AsyncClient, test_clinic: Clinic, make_patient_user
) -> None:
    phone = "+919812345001"
    await make_patient_user(phone=phone)
    requested = await api_client.post(
        "/api/v1/auth/patient/otp/request", json={"clinic_slug": test_clinic.slug, "phone": phone}
    )
    correct_code = requested.json()["debug_code"]
    wrong_code = "000000" if correct_code != "000000" else "111111"

    wrong_attempt = await api_client.post(
        "/api/v1/auth/patient/otp/verify", json={"clinic_slug": test_clinic.slug, "phone": phone, "code": wrong_code}
    )
    assert wrong_attempt.status_code == 401

    right_attempt = await api_client.post(
        "/api/v1/auth/patient/otp/verify", json={"clinic_slug": test_clinic.slug, "phone": phone, "code": correct_code}
    )
    assert right_attempt.status_code == 200


async def test_patient_otp_request_for_unregistered_phone_gives_generic_response(
    api_client: AsyncClient, test_clinic: Clinic
) -> None:
    # Must not reveal whether a phone number is registered.
    response = await api_client.post(
        "/api/v1/auth/patient/otp/request", json={"clinic_slug": test_clinic.slug, "phone": "+919800000999"}
    )
    assert response.status_code == 200
    assert response.json()["debug_code"] is None


async def test_permission_override_grants_receptionist_vitals_recording(
    api_client: AsyncClient, test_clinic: Clinic, make_staff_user, role_map: dict[str, uuid.UUID]
) -> None:
    """The concrete requirement from PRD §3/§13: an Owner enabling
    vitals.record for Receptionists at their clinic, without touching the
    global RolePermission defaults."""
    _, password = await make_staff_user(role_code="RECEPTIONIST", email="front-desk2@apex.clinic")

    async with platform_admin_session() as session:
        permission = (
            await session.execute(select(Permission).where(Permission.code == "vitals.record"))
        ).scalar_one()
        session.add(
            PermissionOverride(
                tenant_id=test_clinic.id,
                role_id=role_map["RECEPTIONIST"],
                permission_id=permission.id,
                granted=True,
            )
        )

    login = await api_client.post(
        "/api/v1/auth/staff/login",
        json={"clinic_slug": test_clinic.slug, "identifier": "front-desk2@apex.clinic", "password": password},
    )
    me = await api_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"}
    )
    assert "vitals.record" in set(me.json()["permissions"])


async def test_sessions_can_be_listed_and_revoked(api_client: AsyncClient, test_clinic: Clinic, make_staff_user) -> None:
    _, password = await make_staff_user(role_code="OWNER", email="owner4@apex.clinic")
    login = await api_client.post(
        "/api/v1/auth/staff/login",
        json={"clinic_slug": test_clinic.slug, "identifier": "owner4@apex.clinic", "password": password},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    sessions = await api_client.get("/api/v1/auth/sessions", headers=headers)
    assert sessions.status_code == 200
    assert len(sessions.json()) >= 1
    session_id = sessions.json()[0]["id"]

    revoke = await api_client.delete(f"/api/v1/auth/sessions/{session_id}", headers=headers)
    assert revoke.status_code == 204

    reuse = await api_client.post(
        "/api/v1/auth/staff/refresh",
        json={"clinic_slug": test_clinic.slug, "refresh_token": login.json()["refresh_token"]},
    )
    assert reuse.status_code == 401

"""End-to-end tests of the Auth module's HTTP surface, against a real
Postgres (see tests/conftest.py — skipped automatically if unreachable).
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import platform_admin_session
from app.modules.auth.models import Permission, PermissionOverride
from app.modules.patients.models import Patient
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


async def test_patient_otp_request_auto_provisions_a_login_for_an_unlinked_patient(
    api_client: AsyncClient, test_clinic: Clinic, make_patient
) -> None:
    """The portal's real first-login path: a clinical Patient record
    exists (created the normal way, via Patient Management) with no
    linked user yet — the very first OTP request for that phone should
    both create the PATIENT user and link patients.user_id, not just
    reject as unregistered."""
    phone = "+919812345555"
    patient_id = await make_patient(phone=phone, first_name="Asha", last_name="Rao")

    requested = await api_client.post(
        "/api/v1/auth/patient/otp/request", json={"clinic_slug": test_clinic.slug, "phone": phone}
    )
    assert requested.status_code == 200
    code = requested.json()["debug_code"]
    assert code is not None

    verified = await api_client.post(
        "/api/v1/auth/patient/otp/verify", json={"clinic_slug": test_clinic.slug, "phone": phone, "code": code}
    )
    assert verified.status_code == 200
    body = verified.json()
    assert body["user"]["role_code"] == "PATIENT"
    assert body["user"]["first_name"] == "Asha"

    async with platform_admin_session() as session:
        patient = (await session.execute(select(Patient).where(Patient.id == patient_id))).scalar_one()
        assert patient.user_id == uuid.UUID(body["user"]["id"])


async def test_patient_otp_request_does_not_auto_provision_when_phone_matches_two_patients(
    api_client: AsyncClient, test_clinic: Clinic, make_patient
) -> None:
    """Ambiguous — two different clinical records share this phone (e.g.
    a shared household landline) — auto-linking would guess which person
    is actually logging in, so this must fall through to the same generic
    "if registered" response as an unregistered phone, not silently pick
    one."""
    phone = "+919812345556"
    await make_patient(phone=phone, first_name="Parent")
    await make_patient(phone=phone, first_name="Child")

    response = await api_client.post(
        "/api/v1/auth/patient/otp/request", json={"clinic_slug": test_clinic.slug, "phone": phone}
    )
    assert response.status_code == 200
    assert response.json()["debug_code"] is None


async def test_patient_otp_request_never_auto_provisions_over_a_staff_phone(
    api_client: AsyncClient, test_clinic: Clinic, make_staff_user
) -> None:
    """A phone already belonging to a staff account (any non-PATIENT
    role) must never get a PATIENT login auto-created for it — the
    existing user is the whole answer, matched before any Patient-table
    lookup even runs."""
    phone = "+919812345557"
    await make_staff_user(role_code="RECEPTIONIST", phone=phone)

    response = await api_client.post(
        "/api/v1/auth/patient/otp/request", json={"clinic_slug": test_clinic.slug, "phone": phone}
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


async def test_otp_static_code_is_issued_and_revealed_even_when_is_production(
    api_client: AsyncClient, test_clinic: Clinic, make_patient_user, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point of otp_static_code: unblock demo/staging login
    testing without server log access, even on a deployment running
    ENVIRONMENT=production (Render's real config) -- confirmed by forcing
    is_production True in the same test, not just testing the setting in
    isolation."""
    settings = get_settings()
    monkeypatch.setattr(settings, "otp_static_code", "123456")
    monkeypatch.setattr(settings, "environment", "production")

    phone = "+919812345600"
    await make_patient_user(phone=phone)

    requested = await api_client.post(
        "/api/v1/auth/patient/otp/request", json={"clinic_slug": test_clinic.slug, "phone": phone}
    )
    assert requested.status_code == 200
    assert requested.json()["debug_code"] == "123456"

    verified = await api_client.post(
        "/api/v1/auth/patient/otp/verify", json={"clinic_slug": test_clinic.slug, "phone": phone, "code": "123456"}
    )
    assert verified.status_code == 200


async def test_otp_static_code_still_hides_for_an_unregistered_phone(
    api_client: AsyncClient, test_clinic: Clinic, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Static-code mode must not weaken the anti-enumeration guarantee --
    an unregistered phone still gets the same generic, code-free response
    it always did, static mode or not."""
    settings = get_settings()
    monkeypatch.setattr(settings, "otp_static_code", "123456")

    response = await api_client.post(
        "/api/v1/auth/patient/otp/request", json={"clinic_slug": test_clinic.slug, "phone": "+919800000998"}
    )
    assert response.status_code == 200
    assert response.json()["debug_code"] is None


async def test_otp_static_code_unset_preserves_original_production_behavior(
    api_client: AsyncClient, test_clinic: Clinic, make_patient_user, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With otp_static_code left unset (the default), forcing is_production
    True must still hide debug_code exactly as before this feature existed
    -- this is the regression guard for the "byte-for-byte the original
    behavior" claim in Settings.otp_static_code's own docstring."""
    settings = get_settings()
    monkeypatch.setattr(settings, "environment", "production")
    assert settings.otp_static_code is None

    phone = "+919812345601"
    await make_patient_user(phone=phone)

    response = await api_client.post(
        "/api/v1/auth/patient/otp/request", json={"clinic_slug": test_clinic.slug, "phone": phone}
    )
    assert response.status_code == 200
    assert response.json()["debug_code"] is None

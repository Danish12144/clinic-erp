"""Phase 1 (Master Handoff item 4, "Accountant permission bundle") — the
new `billing.view`/`expenses.view` permission codes (migration 0032),
granted to a real user via a `permission_overrides` row rather than a new
role. Confirms the whole point of the design: an OTHER_STAFF user with no
override has zero access to billing/expenses/reports, the same user with
the three-permission bundle granted gets tenant-wide read access to all
three, and a *different* OTHER_STAFF user with no override of their own is
unaffected — the grant is genuinely per-user, not per-role. See
tests/conftest.py (skipped automatically if the DB is unreachable).
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.usefixtures("require_db")


async def _login(api_client: AsyncClient, test_clinic, identifier: str, password: str) -> dict[str, str]:
    response = await api_client.post(
        "/api/v1/auth/staff/login", json={"clinic_slug": test_clinic.slug, "identifier": identifier, "password": password}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _grant(api_client: AsyncClient, owner_headers: dict[str, str], *, user_id, permission_code: str) -> None:
    response = await api_client.put(
        "/api/v1/permission-overrides",
        json={"user_id": str(user_id), "permission_code": permission_code, "granted": True},
        headers=owner_headers,
    )
    assert response.status_code == 200, response.text


BUNDLE_PERMISSION_CODES = ("billing.view", "expenses.view", "dashboard.view")


async def test_other_staff_without_override_has_no_access_to_billing_expenses_or_reports(
    api_client: AsyncClient, login_as
) -> None:
    headers, _ = await login_as(role_code="OTHER_STAFF", email="accountant-no-override@apex.clinic")

    assert (await api_client.get("/api/v1/billing/invoices", headers=headers)).status_code == 403
    assert (await api_client.get("/api/v1/billing/payments", headers=headers)).status_code == 403
    assert (await api_client.get("/api/v1/expenses", headers=headers)).status_code == 403
    assert (await api_client.get("/api/v1/billing/summary", headers=headers)).status_code == 403
    assert (await api_client.get("/api/v1/reports/financial", headers=headers)).status_code == 403


async def test_granting_the_accountant_bundle_unlocks_tenant_wide_read_access(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic, login_as
) -> None:
    _, user_id = await login_as(role_code="OTHER_STAFF", email="accountant-bundle@apex.clinic")

    for code in BUNDLE_PERMISSION_CODES:
        await _grant(api_client, owner_headers, user_id=user_id, permission_code=code)

    relogged_in = await _login(api_client, test_clinic, "accountant-bundle@apex.clinic", "correct-horse-battery-staple")
    permissions = (await api_client.get("/api/v1/auth/me", headers=relogged_in)).json()["permissions"]
    for code in BUNDLE_PERMISSION_CODES:
        assert code in permissions

    assert (await api_client.get("/api/v1/billing/invoices", headers=relogged_in)).status_code == 200
    assert (await api_client.get("/api/v1/billing/payments", headers=relogged_in)).status_code == 200
    assert (await api_client.get("/api/v1/expenses", headers=relogged_in)).status_code == 200
    assert (await api_client.get("/api/v1/billing/summary", headers=relogged_in)).status_code == 200
    assert (await api_client.get("/api/v1/reports/financial", headers=relogged_in)).status_code == 200

    # Write access must still be refused — this is a read-only bundle. A
    # syntactically-valid-but-nonexistent branch_id is enough here: the
    # permission dependency rejects the request before the service layer
    # would ever look the branch up.
    assert (await api_client.post("/api/v1/expenses", json={
        "branch_id": "00000000-0000-0000-0000-000000000000",
        "category": "OTHER", "amount": "10.00", "payment_mode": "CASH", "expense_date": "2026-01-01",
    }, headers=relogged_in)).status_code == 403


async def test_the_bundle_is_per_user_not_per_role(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic, login_as
) -> None:
    _, granted_user_id = await login_as(role_code="OTHER_STAFF", email="accountant-granted@apex.clinic")
    other_headers, _ = await login_as(role_code="OTHER_STAFF", email="accountant-ungranted@apex.clinic")

    for code in BUNDLE_PERMISSION_CODES:
        await _grant(api_client, owner_headers, user_id=granted_user_id, permission_code=code)

    # The other OTHER_STAFF user, who never got the override, is unaffected.
    assert (await api_client.get("/api/v1/billing/invoices", headers=other_headers)).status_code == 403
    assert (await api_client.get("/api/v1/expenses", headers=other_headers)).status_code == 403

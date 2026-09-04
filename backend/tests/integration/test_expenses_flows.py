"""End-to-end tests of the Clinic Expenses HTTP surface (schema,
filtering/aggregation, RBAC) against a real Postgres — see
tests/conftest.py (skipped automatically if unreachable).
"""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.usefixtures("require_db")


async def _create_branch(api_client: AsyncClient, owner_headers: dict[str, str], name: str) -> str:
    response = await api_client.post("/api/v1/branches", json={"name": name}, headers=owner_headers)
    assert response.status_code == 201
    return response.json()["id"]


def _payload(branch_id: str, **overrides) -> dict:
    payload = {
        "branch_id": branch_id, "category": "RENT", "amount": "15000.00", "payment_mode": "BANK_TRANSFER",
        "vendor": "Landlord Co", "notes": "Monthly rent",
    }
    payload.update(overrides)
    return payload


# ---- Create / RBAC ------------------------------------------------------------------


async def test_owner_can_create_and_read_an_expense(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "ExpenseBranch")
    response = await api_client.post("/api/v1/expenses", json=_payload(branch_id), headers=owner_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["category"] == "RENT"
    assert body["payment_mode"] == "BANK_TRANSFER"
    assert body["amount"] == "15000.00"

    fetched = await api_client.get(f"/api/v1/expenses/{body['id']}", headers=owner_headers)
    assert fetched.status_code == 200
    assert fetched.json()["vendor"] == "Landlord Co"


async def test_receptionist_can_create_and_read_but_not_update(api_client: AsyncClient, owner_headers: dict[str, str], login_as) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "PettyCashBranch")
    headers, _ = await login_as(role_code="RECEPTIONIST")

    created = await api_client.post("/api/v1/expenses", json=_payload(branch_id, category="SUPPLIES", amount="500.00", payment_mode="CASH"), headers=headers)
    assert created.status_code == 201
    expense_id = created.json()["id"]

    read = await api_client.get(f"/api/v1/expenses/{expense_id}", headers=headers)
    assert read.status_code == 200

    update = await api_client.patch(f"/api/v1/expenses/{expense_id}", json={"amount": "600.00"}, headers=headers)
    assert update.status_code == 403


async def test_doctor_and_nurse_have_zero_access(api_client: AsyncClient, owner_headers: dict[str, str], login_as) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "ZeroAccessBranch")
    for role in ("DOCTOR", "NURSE", "LAB_STAFF", "PHARMACY_STAFF"):
        headers, _ = await login_as(role_code=role)
        write = await api_client.post("/api/v1/expenses", json=_payload(branch_id), headers=headers)
        assert write.status_code == 403
        read = await api_client.get("/api/v1/expenses", headers=headers)
        assert read.status_code == 403


async def test_creating_with_a_nonexistent_branch_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.post("/api/v1/expenses", json=_payload("00000000-0000-0000-0000-000000000000"), headers=owner_headers)
    assert response.status_code == 422


# ---- Update ---------------------------------------------------------------------


async def test_owner_can_update_an_expense(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "UpdateBranch")
    created = await api_client.post("/api/v1/expenses", json=_payload(branch_id), headers=owner_headers)
    expense_id = created.json()["id"]

    response = await api_client.patch(f"/api/v1/expenses/{expense_id}", json={"amount": "16000.00", "notes": "Revised rent"}, headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["amount"] == "16000.00"
    assert response.json()["notes"] == "Revised rent"
    assert response.json()["category"] == "RENT"  # untouched field preserved


async def test_updating_a_nonexistent_expense_is_404(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.patch("/api/v1/expenses/00000000-0000-0000-0000-000000000000", json={"amount": "1.00"}, headers=owner_headers)
    assert response.status_code == 404


async def test_get_nonexistent_expense_is_404(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.get("/api/v1/expenses/00000000-0000-0000-0000-000000000000", headers=owner_headers)
    assert response.status_code == 404


# ---- Filtering + aggregation --------------------------------------------------------


async def test_search_filters_by_category_and_payment_mode(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "FilterBranch")
    await api_client.post("/api/v1/expenses", json=_payload(branch_id, category="RENT", amount="10000.00", payment_mode="BANK_TRANSFER"), headers=owner_headers)
    await api_client.post("/api/v1/expenses", json=_payload(branch_id, category="SUPPLIES", amount="500.00", payment_mode="CASH"), headers=owner_headers)
    await api_client.post("/api/v1/expenses", json=_payload(branch_id, category="SUPPLIES", amount="250.00", payment_mode="UPI"), headers=owner_headers)

    by_category = await api_client.get(f"/api/v1/expenses?branch_id={branch_id}&category=SUPPLIES", headers=owner_headers)
    assert by_category.status_code == 200
    assert by_category.json()["total"] == 2
    assert by_category.json()["total_amount"] == "750.00"

    by_payment_mode = await api_client.get(f"/api/v1/expenses?branch_id={branch_id}&payment_mode=CASH", headers=owner_headers)
    assert by_payment_mode.status_code == 200
    assert by_payment_mode.json()["total"] == 1
    assert by_payment_mode.json()["total_amount"] == "500.00"


async def test_search_filters_by_date_range(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "DateRangeBranch")
    old_date = (date.today() - timedelta(days=60)).isoformat()
    recent_date = date.today().isoformat()
    await api_client.post("/api/v1/expenses", json=_payload(branch_id, expense_date=old_date, amount="100.00"), headers=owner_headers)
    await api_client.post("/api/v1/expenses", json=_payload(branch_id, expense_date=recent_date, amount="200.00"), headers=owner_headers)

    window_from = (date.today() - timedelta(days=5)).isoformat()
    response = await api_client.get(f"/api/v1/expenses?branch_id={branch_id}&date_from={window_from}", headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["total_amount"] == "200.00"


async def test_expense_date_defaults_to_today_when_omitted(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "DefaultDateBranch")
    response = await api_client.post("/api/v1/expenses", json=_payload(branch_id), headers=owner_headers)
    assert response.status_code == 201
    assert response.json()["expense_date"] == date.today().isoformat()


async def test_total_amount_sums_across_the_full_filtered_set_not_just_the_page(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "PaginationBranch")
    for i in range(3):
        await api_client.post("/api/v1/expenses", json=_payload(branch_id, category="MAINTENANCE", amount="100.00"), headers=owner_headers)

    response = await api_client.get(f"/api/v1/expenses?branch_id={branch_id}&category=MAINTENANCE&limit=1", headers=owner_headers)
    assert response.status_code == 200
    assert len(response.json()["items"]) == 1
    assert response.json()["total"] == 3
    assert response.json()["total_amount"] == "300.00"

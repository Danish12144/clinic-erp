import os
from decimal import Decimal

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

from app.modules.billing.payment_gateway import MockPaymentGatewayAdapter, get_payment_gateway_adapter


class TestMockPaymentGatewayAdapter:
    async def test_create_order_returns_a_simulated_order(self) -> None:
        adapter = MockPaymentGatewayAdapter()
        order = await adapter.create_order(amount=Decimal("500.00"), currency="INR", receipt="invoice-123")
        assert order.provider == "mock"
        assert order.status == "created"
        assert order.amount == Decimal("500.00")
        assert order.currency == "INR"
        assert order.order_id.startswith("mock_order_")

    async def test_each_order_gets_a_distinct_id(self) -> None:
        adapter = MockPaymentGatewayAdapter()
        first = await adapter.create_order(amount=Decimal("100"), currency="INR", receipt="a")
        second = await adapter.create_order(amount=Decimal("100"), currency="INR", receipt="b")
        assert first.order_id != second.order_id


class TestGetPaymentGatewayAdapter:
    def test_returns_mock_adapter_by_default(self) -> None:
        assert isinstance(get_payment_gateway_adapter(), MockPaymentGatewayAdapter)

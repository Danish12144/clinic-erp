import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

import pytest

from app.modules.notifications.adapters import ConsoleChannelAdapter, get_channel_adapter
from app.modules.notifications.models import CommChannel, CommStatus


class TestConsoleChannelAdapter:
    async def test_send_simulates_success(self) -> None:
        adapter = ConsoleChannelAdapter(CommChannel.WHATSAPP)
        result = await adapter.send(recipient="+919876543210", body="Hello")
        assert result.status == CommStatus.SENT
        assert result.provider_message_id is not None
        assert result.provider_message_id.startswith("console-")

    async def test_each_send_gets_a_distinct_message_id(self) -> None:
        adapter = ConsoleChannelAdapter(CommChannel.SMS)
        first = await adapter.send(recipient="+919876543210", body="A")
        second = await adapter.send(recipient="+919876543210", body="B")
        assert first.provider_message_id != second.provider_message_id


class TestGetChannelAdapter:
    def test_returns_console_adapter_by_default_for_every_channel(self) -> None:
        for channel in (CommChannel.SMS, CommChannel.WHATSAPP, CommChannel.EMAIL, CommChannel.PUSH):
            assert isinstance(get_channel_adapter(channel), ConsoleChannelAdapter)

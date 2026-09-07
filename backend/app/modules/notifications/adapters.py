"""Channel adapters — PRD-ARCHITECTURE.md §16's `ChannelAdapter` (WhatsApp/
SMS/Email), the piece `dispatch_notification` was still missing: it could
render a message and log it, but never actually handed it to anything.
Only a `ConsoleChannelAdapter` is implemented — same "log it, don't send
it, simulate success" placeholder precedent `ConsoleOtpSender`
(`app/modules/auth/otp_sender.py`) already established for OTP delivery.

Swapping in a real provider later (Fast2SMS/MSG91 for SMS, Meta's WhatsApp
Business API or a BSP like Gupshup/Interakt for WhatsApp, Resend/SES for
Email) means implementing `ChannelAdapter` and adding one `elif` branch to
`get_channel_adapter` — no change to `dispatch_notification` or any of its
callers (Appointments/Billing/Lab/CRM), which only ever see the interface.
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Protocol

from app.core.config import get_settings
from app.modules.notifications.models import CommChannel, CommStatus

logger = logging.getLogger("clinic_erp.notifications.channel")


@dataclass(frozen=True)
class ChannelSendResult:
    status: CommStatus
    provider_message_id: str | None


class ChannelAdapter(Protocol):
    async def send(self, *, recipient: str, body: str) -> ChannelSendResult: ...


class ConsoleChannelAdapter:
    """Not production-safe — logs the message instead of sending it, and
    always simulates a successful send (a fake `console-<uuid>` message
    id), the same way `ConsoleOtpSender` simulates OTP delivery. This is
    what every channel resolves to until a real provider is configured."""

    def __init__(self, channel: CommChannel) -> None:
        self._channel = channel

    async def send(self, *, recipient: str, body: str) -> ChannelSendResult:
        logger.warning(
            "[%s] to %s (ConsoleChannelAdapter — dev/test only, not production-safe): %s",
            self._channel.value, recipient, body,
        )
        return ChannelSendResult(status=CommStatus.SENT, provider_message_id=f"console-{uuid.uuid4().hex[:12]}")


def get_channel_adapter(channel: CommChannel) -> ChannelAdapter:
    settings = get_settings()
    provider = {
        CommChannel.SMS: settings.sms_provider,
        CommChannel.WHATSAPP: settings.whatsapp_provider,
        CommChannel.EMAIL: settings.email_provider,
        CommChannel.PUSH: "console",
    }[channel]
    if provider == "console":
        return ConsoleChannelAdapter(channel)
    raise NotImplementedError(
        f"Unsupported {channel.value} provider: {provider!r} — only 'console' is implemented. "
        "A real provider (e.g. Fast2SMS for SMS, Meta's WhatsApp Business API for WhatsApp) can be "
        "added behind this same ChannelAdapter interface without changing any caller."
    )

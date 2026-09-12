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

import httpx

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


class TwilioChannelAdapter:
    """Phase 2 (Master Handoff item 3) — a genuine Twilio Programmable
    Messaging integration (SMS and WhatsApp both go through the same
    Messages resource; only the `From`/`To` number formatting differs —
    WhatsApp numbers are prefixed `whatsapp:`, per Twilio's own
    convention). No SDK dependency added: this is one HTTP POST with HTTP
    Basic Auth (Account SID as username, Auth Token as password), exactly
    Twilio's documented REST shape.

    Not selected by `get_channel_adapter` unless `sms_provider`/
    `whatsapp_provider` is explicitly set to `'twilio'` and the three
    required settings are non-empty — the default ('console') is
    unchanged, so no existing deployment's behavior changes just because
    this class now exists."""

    _MESSAGES_URL_TEMPLATE = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"

    def __init__(self, *, channel: CommChannel, account_sid: str, auth_token: str, from_number: str) -> None:
        self._channel = channel
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._from_number = from_number

    def _format_number(self, number: str) -> str:
        return f"whatsapp:{number}" if self._channel == CommChannel.WHATSAPP and not number.startswith("whatsapp:") else number

    async def send(self, *, recipient: str, body: str) -> ChannelSendResult:
        url = self._MESSAGES_URL_TEMPLATE.format(account_sid=self._account_sid)
        async with httpx.AsyncClient(auth=(self._account_sid, self._auth_token), timeout=15.0) as client:
            response = await client.post(
                url,
                data={
                    "From": self._format_number(self._from_number),
                    "To": self._format_number(recipient),
                    "Body": body,
                },
            )
        if response.status_code >= 400:
            logger.error("[%s] Twilio send to %s failed: %s %s", self._channel.value, recipient, response.status_code, response.text)
            return ChannelSendResult(status=CommStatus.FAILED, provider_message_id=None)
        data = response.json()
        return ChannelSendResult(status=CommStatus.SENT, provider_message_id=data.get("sid"))


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
    if provider == "twilio":
        if not settings.twilio_account_sid or not settings.twilio_auth_token:
            raise RuntimeError(
                f"{channel.value.lower()}_provider=twilio requires TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN to be "
                "set — misconfigured environment, failing loud rather than silently falling back to console."
            )
        from_number = settings.twilio_whatsapp_from if channel == CommChannel.WHATSAPP else settings.twilio_from_number
        if not from_number:
            raise RuntimeError(
                f"{channel.value.lower()}_provider=twilio requires "
                f"{'TWILIO_WHATSAPP_FROM' if channel == CommChannel.WHATSAPP else 'TWILIO_FROM_NUMBER'} to be set."
            )
        return TwilioChannelAdapter(
            channel=channel, account_sid=settings.twilio_account_sid, auth_token=settings.twilio_auth_token, from_number=from_number,
        )
    raise NotImplementedError(
        f"Unsupported {channel.value} provider: {provider!r} — only 'console'/'twilio' are implemented. "
        "A different provider (e.g. Meta's WhatsApp Business API directly, MSG91 for SMS) can be "
        "added behind this same ChannelAdapter interface without changing any caller."
    )

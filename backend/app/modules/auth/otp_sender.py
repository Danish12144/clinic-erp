"""OTP delivery is deliberately behind an interface: the Communications
module (PRD-ARCHITECTURE.md §16, Phase 6 in §29) will eventually own a
real WhatsApp/SMS adapter. Until then, ConsoleOtpSender is the only
implementation — logs the code instead of sending it. NOT production-safe;
`AuthService` additionally echoes the code back in the API response body
outside of `production`, so local dev and integration tests can complete
the OTP flow without any external provider.
"""

import logging
from typing import Protocol

logger = logging.getLogger("clinic_erp.auth.otp")


class OtpSender(Protocol):
    async def send(self, *, phone: str, code: str) -> None: ...


class ConsoleOtpSender:
    async def send(self, *, phone: str, code: str) -> None:
        logger.warning("OTP for %s: %s (ConsoleOtpSender — dev/test only, not production-safe)", phone, code)


def get_otp_sender() -> OtpSender:
    return ConsoleOtpSender()

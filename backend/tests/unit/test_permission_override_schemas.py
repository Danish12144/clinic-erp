import os
import uuid

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

import pytest
from pydantic import ValidationError

from app.modules.auth.schemas import PermissionOverrideSetRequest


class TestPermissionOverrideSetRequest:
    def test_accepts_a_role_targeted_payload(self) -> None:
        req = PermissionOverrideSetRequest(role_code="RECEPTIONIST", permission_code="vitals.record", granted=True)
        assert req.role_code == "RECEPTIONIST"
        assert req.user_id is None
        assert req.granted is True

    def test_accepts_a_user_targeted_payload(self) -> None:
        user_id = uuid.uuid4()
        req = PermissionOverrideSetRequest(user_id=user_id, permission_code="vitals.record", granted=False)
        assert req.user_id == user_id
        assert req.role_code is None

    def test_rejects_both_role_code_and_user_id(self) -> None:
        with pytest.raises(ValidationError):
            PermissionOverrideSetRequest(role_code="NURSE", user_id=uuid.uuid4(), permission_code="vitals.record", granted=True)

    def test_rejects_neither_role_code_nor_user_id(self) -> None:
        with pytest.raises(ValidationError):
            PermissionOverrideSetRequest(permission_code="vitals.record", granted=True)

    def test_rejects_a_blank_permission_code(self) -> None:
        with pytest.raises(ValidationError):
            PermissionOverrideSetRequest(role_code="NURSE", permission_code="", granted=True)

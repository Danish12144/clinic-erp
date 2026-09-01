import os
import uuid
from datetime import datetime, timedelta

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

import jwt
import pytest
import time_machine

from app.core import security
from app.core.config import get_settings

settings = get_settings()


def test_hash_password_roundtrip() -> None:
    raw = "correct-horse-battery-staple"
    hashed = security.hash_password(raw)

    assert hashed != raw
    assert security.verify_password(raw, hashed) is True
    assert security.verify_password("wrong-password", hashed) is False


def test_hash_password_produces_different_hashes_each_time() -> None:
    # argon2 salts each hash — two hashes of the same input must differ,
    # otherwise a leaked hash table trivially reveals duplicate passwords.
    hash_a = security.hash_password("same-password")
    hash_b = security.hash_password("same-password")
    assert hash_a != hash_b


def test_access_token_roundtrip() -> None:
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    token = security.create_access_token(
        user_id=user_id, tenant_id=tenant_id, role_code="DOCTOR", permissions=["vitals.record", "prescription.manage"]
    )

    payload = security.decode_access_token(token)

    assert payload["sub"] == str(user_id)
    assert payload["tenant_id"] == str(tenant_id)
    assert payload["role"] == "DOCTOR"
    assert set(payload["permissions"]) == {"vitals.record", "prescription.manage"}


def test_expired_access_token_is_rejected() -> None:
    start = datetime(2026, 1, 1, 0, 0, 0)
    with time_machine.travel(start, tick=False):
        token = security.create_access_token(
            user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), role_code="OWNER", permissions=[]
        )

    past_expiry = start + timedelta(minutes=settings.access_token_expire_minutes + 1)
    with time_machine.travel(past_expiry, tick=False):
        with pytest.raises(jwt.ExpiredSignatureError):
            security.decode_access_token(token)


def test_a_refresh_style_random_token_is_never_accepted_as_access_token() -> None:
    opaque = security.generate_opaque_token()
    with pytest.raises(jwt.InvalidTokenError):
        security.decode_access_token(opaque)


def test_opaque_token_hash_is_deterministic_and_one_way() -> None:
    token = security.generate_opaque_token()
    hash_a = security.hash_opaque_token(token)
    hash_b = security.hash_opaque_token(token)

    assert hash_a == hash_b
    assert hash_a != token


def test_opaque_tokens_are_unique() -> None:
    tokens = {security.generate_opaque_token() for _ in range(1000)}
    assert len(tokens) == 1000


def test_otp_code_is_six_digits() -> None:
    for _ in range(200):
        code = security.generate_otp_code()
        assert len(code) == 6
        assert code.isdigit()


def test_otp_code_hash_matches_only_the_original_code() -> None:
    code = security.generate_otp_code()
    hashed = security.hash_otp_code(code)

    assert security.hash_otp_code(code) == hashed
    assert security.hash_otp_code("000000" if code != "000000" else "111111") != hashed

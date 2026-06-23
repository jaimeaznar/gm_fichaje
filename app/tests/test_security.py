"""PIN bcrypt, generación no trivial y JWT (REQ-05, 21)."""

from __future__ import annotations

import jwt
import pytest

from app.core.security import (
    create_access_token,
    decode_token,
    generate_pin,
    hash_pin,
    is_trivial_pin,
    verify_pin,
)


def test_hash_and_verify_pin():
    h = hash_pin("428913")
    assert h != "428913"  # nunca en claro
    assert verify_pin("428913", h)
    assert not verify_pin("000000", h)


def test_verify_pin_handles_bad_hash():
    assert verify_pin("123456", "not-a-bcrypt-hash") is False


@pytest.mark.parametrize(
    "pin",
    ["123456", "000000", "111111", "12345", "12345a", "1234567"],
)
def test_trivial_pins_rejected(pin):
    assert is_trivial_pin(pin)


def test_pin_derived_from_code_is_trivial():
    assert is_trivial_pin("123456", code_norm="123456abc")


def test_generated_pin_is_valid_and_nontrivial():
    for _ in range(50):
        pin = generate_pin("pega")
        assert len(pin) == 6 and pin.isdigit()
        assert not is_trivial_pin(pin, "pega")


def test_jwt_roundtrip_contains_claims():
    token = create_access_token("w-123", "admin", pin_temporary=True)
    claims = decode_token(token)
    assert claims["worker_id"] == "w-123"
    assert claims["role"] == "admin"
    assert claims["pin_temporary"] is True


def test_invalid_token_raises():
    with pytest.raises(jwt.PyJWTError):
        decode_token("garbage.token.value")

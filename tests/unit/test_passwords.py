"""Local-account password storage (scrypt, per-user salt, recorded parameters) and policy."""

from __future__ import annotations

import base64
import re

import pytest

from eurogas_nexus.security import passwords
from eurogas_nexus.security.passwords import PasswordPolicyError, check_password_policy


def test_policy_accepts_a_long_phrase_without_composition_rules():
    check_password_policy("correct horse battery staple", username="alice")
    check_password_policy("x" * 11 + "y")  # twelve characters, no digit or capital needed
    check_password_policy("a" * 127 + "b")


@pytest.mark.parametrize(
    ("password", "code"),
    [
        ("short-pass1", "password_too_short"),
        ("12345678", "password_too_short"),
        ("ab" * 65, "password_too_long"),
        ("alice.smith-2026!", "password_contains_username"),
        ("ALICE.SMITHxxxx", "password_contains_username"),
        ("password1234", "password_too_common"),
        ("Password1234", "password_too_common"),
        ("123456789012", "password_too_common"),
        ("zzzzzzzzzzzzzz", "password_too_common"),
    ],
)
def test_policy_refusals_name_their_reason(password, code):
    with pytest.raises(PasswordPolicyError) as raised:
        check_password_policy(password, username="alice.smith")
    assert raised.value.code == code


def test_length_is_measured_after_unicode_normalisation():
    # Twelve full-width digits are twelve characters, and normalise to ASCII digits.
    with pytest.raises(PasswordPolicyError) as raised:
        check_password_policy("１２３４５６７８９０１２")
    assert raised.value.code == "password_too_common"
    stored = passwords.hash_password("café au lait 2026", params=_FAST)
    decomposed = "café au lait 2026"
    assert passwords.verify_password(decomposed, stored)


_FAST = {"n": 2**10, "r": 8, "p": 1, "dklen": 32}


def test_hash_records_the_kdf_its_parameters_and_a_per_user_salt():
    stored = passwords.hash_password("a long enough password")
    assert stored.kdf == "scrypt"
    assert stored.params == {"n": 2**15, "r": 8, "p": 1, "dklen": 32}
    assert len(base64.b64decode(stored.salt_b64)) == 16
    assert len(base64.b64decode(stored.digest_b64)) == 32
    again = passwords.hash_password("a long enough password")
    assert again.salt_b64 != stored.salt_b64 and again.digest_b64 != stored.digest_b64
    assert "a long enough password" not in repr(stored)


def test_verification_is_exact_and_detects_old_parameters():
    stored = passwords.hash_password("the right password", params=_FAST)
    assert passwords.verify_password("the right password", stored)
    assert not passwords.verify_password("the right passworD", stored)
    assert not passwords.verify_password("", stored)
    assert passwords.needs_rehash(stored)  # fast test parameters are not the current ones
    assert not passwords.needs_rehash(passwords.hash_password("x" * 12))
    unknown_kdf = passwords.PasswordHash("md5", {}, stored.salt_b64, stored.digest_b64)
    assert not passwords.verify_password("the right password", unknown_kdf)


def test_one_time_secret_is_readable_long_and_unambiguous():
    secrets_seen = {passwords.generate_one_time_secret() for _ in range(50)}
    assert len(secrets_seen) == 50
    for secret in secrets_seen:
        assert re.fullmatch(r"[a-z2-9]{4}(-[a-z2-9]{4}){3}", secret)
        assert not set(secret) & set("01ilo")
        assert len(secret) >= passwords.MIN_PASSWORD_LENGTH


def test_tokens_are_stored_as_digests():
    token = passwords.generate_token()
    assert len(token) >= 40
    assert passwords.hash_token(token) != token and len(passwords.hash_token(token)) == 64

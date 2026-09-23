import hashlib
import hmac
import string

import pytest
from cryptography.fernet import Fernet

from app import security
from app.security import (
    DecryptionError,
    PasswordPolicyError,
    check_csrf_token,
    decrypt,
    encrypt,
    hash_password,
    make_csrf_token,
    verify_meta_signature,
    verify_password,
    verify_telegram_secret,
)

KEY = Fernet.generate_key().decode()
OTHER_KEY = Fernet.generate_key().decode()
PASSWORD = "Correct-Horse-7"  # meets every rule
SESSION_SECRET = "s" * 40


@pytest.fixture(scope="module")
def stored():
    return hash_password(PASSWORD)  # hashing is slow on purpose; do it once


# ---------- encryption ----------


@pytest.mark.parametrize(
    "text", ["EAAB-page-token-123", "", "বাংলা টোকেন", "x" * 10_000, '{"token": "a"}']
)
def test_encrypt_round_trip(text):
    token = encrypt(KEY, text)
    assert isinstance(token, bytes)
    assert text.encode() not in token or text == ""
    assert decrypt(KEY, token) == text


def test_same_text_encrypts_differently_each_time():
    assert encrypt(KEY, "same") != encrypt(KEY, "same")


def test_wrong_key_raises_specific_error():
    with pytest.raises(DecryptionError):
        decrypt(OTHER_KEY, encrypt(KEY, "secret"))


def test_tampered_ciphertext_raises():
    token = bytearray(encrypt(KEY, "secret"))
    token[len(token) // 2] ^= 0x01  # flip one bit in the middle
    with pytest.raises(DecryptionError):
        decrypt(KEY, bytes(token))


@pytest.mark.parametrize("garbage", [b"", b"not-a-token", b"\x00\xff\x10"])
def test_garbage_ciphertext_raises(garbage):
    with pytest.raises(DecryptionError):
        decrypt(KEY, garbage)


def test_decryption_error_hides_the_key():
    with pytest.raises(DecryptionError) as exc:
        decrypt(OTHER_KEY, encrypt(KEY, "secret"))
    assert OTHER_KEY not in str(exc.value)
    assert KEY not in str(exc.value)


# ---------- passwords ----------


def test_correct_password_verifies(stored):
    assert verify_password(PASSWORD, stored) is True


@pytest.mark.parametrize(
    "attempt",
    ["correct-Horse-7", "Correct-Horse-7 ", " Correct-Horse-7", "", "Correct-Horse-", "Aa1!aaaa"],
)
def test_wrong_password_fails(stored, attempt):
    assert verify_password(attempt, stored) is False


@pytest.mark.parametrize("attempt", ["Correct-Horse-৭", "Correct-Horse-7😀", "Córrect-Horse-7"])
def test_non_ascii_login_attempt_fails_cleanly(stored, attempt):
    assert verify_password(attempt, stored) is False


def test_two_hashes_of_same_password_differ():
    assert hash_password(PASSWORD) != hash_password(PASSWORD)  # random salt


def test_hash_format_records_parameters(stored):
    scheme, n, r, p, salt, digest = stored.split("$")
    assert scheme == "scrypt"
    assert (int(n), int(r), int(p)) == (2**14, 8, 5)  # OWASP-equivalent, low-memory row
    assert PASSWORD not in stored


def test_hashing_memory_fits_a_small_server():
    # 128 * N * r bytes per login. At 16 MiB, five simultaneous logins use 80 MiB, safe on a
    # 512 MB container; the old N=2^17 setting needed 128 MiB each (D-011, C-013).
    assert 128 * security.SCRYPT_N * security.SCRYPT_R <= 16 * 2**20
    # Same OWASP strength: N * p must match the OWASP table row (2^14 with p=5).
    assert (security.SCRYPT_N, security.SCRYPT_R, security.SCRYPT_P) == (2**14, 8, 5)


def test_old_hashes_still_verify_after_parameters_change():
    salt = b"0123456789abcdef"
    digest = hashlib.scrypt(PASSWORD.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    old = "$".join(["scrypt", str(2**14), "8", "1", salt.hex(), digest.hex()])
    assert verify_password(PASSWORD, old) is True


@pytest.mark.parametrize(
    "password",
    [
        "Aa1!aaaa",  # exactly 8
        "Aa1!" + "a" * 252,  # exactly 256
        "Aa1 aaaa!",  # spaces allowed
        string.punctuation + "Aa1",  # every ASCII symbol accepted
    ],
)
def test_valid_passwords_accepted(password):
    assert verify_password(password, hash_password(password)) is True


@pytest.mark.parametrize(
    "password, rule",
    [
        ("Aa1!aaa", "at least 8 characters"),
        ("Aa1!" + "a" * 253, "at most 256 characters"),
        ("aa1!aaaa", "an uppercase letter"),
        ("AA1!AAAA", "a lowercase letter"),
        ("Aa!!aaaa", "a number"),
        ("Aa1aaaaa", "a symbol"),
        ("Aa1 aaaa", "a symbol"),  # a space is not a symbol
    ],
)
def test_each_rule_enforced(password, rule):
    with pytest.raises(PasswordPolicyError, match=rule):
        hash_password(password)


@pytest.mark.parametrize(
    "password",
    [
        "Aa1!আমারপাস",  # Bangla letters
        "Aa!aaaa১",  # a Bangla digit must not count as a number
        "Aa1!aaaa😀",  # emoji
        "Aa1!résumé",  # accented letter
        "Aa1!aa\taa",  # tab
        "Aa1!aa\naa",  # newline
        "Aa1!aa\x00aa",  # NUL
        "Aa1!aa\u00a0aa",  # non-breaking space
    ],
)
def test_only_standard_keyboard_characters(password):
    with pytest.raises(PasswordPolicyError, match="English letters, numbers, symbols"):
        hash_password(password)


@pytest.mark.parametrize("password", ["Aa!aaaa১", "Aa!aaaa٣", "Aa!aaaa１"])
def test_non_ascii_digit_does_not_satisfy_number_rule(password):
    # Regression (P1.3 mutation check): Bangla, Arabic-Indic and full-width digits pass
    # str.isdigit(); the number rule must still demand an ASCII digit on its own.
    with pytest.raises(PasswordPolicyError) as exc:
        hash_password(password)
    assert "a number" in str(exc.value)


def test_all_problems_reported_together():
    with pytest.raises(PasswordPolicyError) as exc:
        hash_password("a")
    for rule in ("at least 8", "an uppercase letter", "a number", "a symbol"):
        assert rule in str(exc.value)


def test_overlong_attempt_fails_without_hashing(stored, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("must not run scrypt on an overlong attempt")

    monkeypatch.setattr(hashlib, "scrypt", boom)
    assert verify_password("Aa1!" * 25_000, stored) is False


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "plain-text-password",
        "bcrypt$10$abc",
        "scrypt$x$8$1$00$00",
        "scrypt$16384$8$1$zz$00",  # salt not hex
        "scrypt$16384$8$1$00",  # missing part
        "scrypt$0$8$1$00$00",  # impossible cost
        "scrypt$3$8$1$00$00",  # cost in range but not a power of two (scrypt refuses)
        "scrypt$16384$0$1$00$00",  # block size 0
        "scrypt$16384$8$0$00$00",  # parallelism 0
        "scrypt$999999999999$8$1$00$00",  # absurd cost (would exhaust memory)
    ],
)
def test_malformed_stored_hash_fails_cleanly(bad):
    assert verify_password(PASSWORD, bad) is False


def test_verify_uses_constant_time_comparison(stored, monkeypatch):
    calls = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append(1)
        return real(a, b)

    monkeypatch.setattr(hmac, "compare_digest", spy)
    verify_password(PASSWORD, stored)
    assert calls == [1]


# ---------- Meta webhook signature ----------

APP_SECRET = "meta-app-secret"
BODY = b'{"object":"page","entry":[{"id":"123"}]}'
GOOD = "sha256=" + hmac.new(APP_SECRET.encode(), BODY, hashlib.sha256).hexdigest()


def test_valid_meta_signature():
    assert verify_meta_signature(APP_SECRET, BODY, GOOD) is True


def test_uppercase_hex_accepted():
    assert verify_meta_signature(APP_SECRET, BODY, "sha256=" + GOOD[7:].upper()) is True


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        GOOD[7:],  # no prefix
        "sha1=" + GOOD[7:],
        "SHA256=" + GOOD[7:] + "x",
        GOOD[:-1],  # one hex char short
        GOOD + "0",  # one too long
        "sha256=" + "g" * 64,  # not hex
        "sha256=" + "é" * 64,  # non-ASCII
        "sha256=" + GOOD[7:].replace(GOOD[8], "0" if GOOD[8] != "0" else "1", 1),  # 1 char off
    ],
)
def test_bad_meta_signature_headers_rejected(header):
    assert verify_meta_signature(APP_SECRET, BODY, header) is False


def test_body_changed_by_one_byte_rejected():
    changed = BODY[:-2] + b"4" + BODY[-1:]
    assert changed != BODY
    assert verify_meta_signature(APP_SECRET, changed, GOOD) is False


def test_wrong_app_secret_rejected():
    assert verify_meta_signature("other-secret", BODY, GOOD) is False


def test_empty_app_secret_never_verifies():
    signature = "sha256=" + hmac.new(b"", BODY, hashlib.sha256).hexdigest()
    assert verify_meta_signature("", BODY, signature) is False


def test_empty_body_with_valid_signature():
    signature = "sha256=" + hmac.new(APP_SECRET.encode(), b"", hashlib.sha256).hexdigest()
    assert verify_meta_signature(APP_SECRET, b"", signature) is True


# ---------- Telegram secret header ----------

TG_SECRET = "Tg_secret-token_ABC123"


def test_telegram_exact_match():
    assert verify_telegram_secret(TG_SECRET, TG_SECRET) is True


@pytest.mark.parametrize(
    "header",
    [None, "", TG_SECRET.lower(), TG_SECRET + " ", " " + TG_SECRET, TG_SECRET[:-1], "টোকেন"],
)
def test_telegram_anything_else_rejected(header):
    assert verify_telegram_secret(TG_SECRET, header) is False


def test_telegram_empty_expected_never_matches():
    assert verify_telegram_secret("", "") is False


def test_telegram_uses_constant_time_comparison(monkeypatch):
    calls = []
    real = hmac.compare_digest
    monkeypatch.setattr(hmac, "compare_digest", lambda a, b: calls.append(1) or real(a, b))
    verify_telegram_secret(TG_SECRET, TG_SECRET)
    assert calls == [1]


# ---------- CSRF ----------

NOW = 1_800_000_000.0


def test_csrf_token_valid_for_its_session():
    token = make_csrf_token(SESSION_SECRET, "session-1", now=NOW)
    assert check_csrf_token(SESSION_SECRET, "session-1", token, now=NOW + 60) is True


def test_csrf_token_rejected_for_another_session():
    token = make_csrf_token(SESSION_SECRET, "session-1", now=NOW)
    assert check_csrf_token(SESSION_SECRET, "session-2", token, now=NOW) is False


def test_csrf_token_rejected_with_another_secret():
    token = make_csrf_token(SESSION_SECRET, "session-1", now=NOW)
    assert check_csrf_token("x" * 40, "session-1", token, now=NOW) is False


def test_csrf_tokens_last_8_hours():
    assert security.CSRF_MAX_AGE == 8 * 3600  # owner decision (D-011)


def test_csrf_token_expiry_boundary():
    token = make_csrf_token(SESSION_SECRET, "s", now=NOW)
    age = security.CSRF_MAX_AGE
    assert check_csrf_token(SESSION_SECRET, "s", token, now=NOW + age) is True
    assert check_csrf_token(SESSION_SECRET, "s", token, now=NOW + age + 1) is False


def test_csrf_token_from_the_future_rejected():
    token = make_csrf_token(SESSION_SECRET, "s", now=NOW + 120)
    assert check_csrf_token(SESSION_SECRET, "s", token, now=NOW) is False
    near = make_csrf_token(SESSION_SECRET, "s", now=NOW + 30)  # small clock skew is fine
    assert check_csrf_token(SESSION_SECRET, "s", near, now=NOW) is True


def test_csrf_timestamp_cannot_be_edited():
    token = make_csrf_token(SESSION_SECRET, "s", now=NOW)
    stamp, signature = token.split(".")
    forged = f"{int(stamp) + 3600}.{signature}"
    assert check_csrf_token(SESSION_SECRET, "s", forged, now=NOW + 3600) is False


@pytest.mark.parametrize(
    "token",
    [None, "", ".", "abc", "123.", ".abc", "12x.abcdef", "1.2.3", "-5.abc", "১২৩.abc"],
)
def test_csrf_malformed_tokens_rejected(token):
    assert check_csrf_token(SESSION_SECRET, "s", token, now=NOW) is False


def test_csrf_empty_session_id_rejected():
    token = make_csrf_token(SESSION_SECRET, "", now=NOW)
    assert check_csrf_token(SESSION_SECRET, "", token, now=NOW) is False


def test_csrf_uses_its_own_key():
    # The signature must not be a plain HMAC with the session secret (domain separation).
    token = make_csrf_token(SESSION_SECRET, "s", now=NOW)
    stamp, signature = token.split(".")
    plain = hmac.new(SESSION_SECRET.encode(), f"s:{stamp}".encode(), hashlib.sha256).hexdigest()
    assert signature != plain


def test_csrf_uses_real_clock_by_default():
    token = make_csrf_token(SESSION_SECRET, "s")
    assert check_csrf_token(SESSION_SECRET, "s", token) is True

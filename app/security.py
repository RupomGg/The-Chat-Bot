"""Small security helpers: encryption at rest, passwords, webhook signatures, CSRF.

Every check returns False for bad input instead of raising, except where the caller must
act on the difference (DecryptionError, PasswordPolicyError). Comparisons of secrets use
hmac.compare_digest so their timing doesn't reveal how many characters matched.
"""

import hashlib
import hmac
import secrets
import string
import time

from cryptography.fernet import Fernet, InvalidToken

# ---------- encryption at rest (channel tokens, CRM secrets) ----------


class DecryptionError(Exception):
    """The ciphertext is corrupt or was encrypted with another key."""


def encrypt(key: str, plaintext: str) -> bytes:
    return Fernet(key).encrypt(plaintext.encode("utf-8"))


def decrypt(key: str, token: bytes) -> str:
    try:
        return Fernet(key).decrypt(token).decode("utf-8")
    except InvalidToken as err:
        raise DecryptionError("cannot decrypt: wrong key or corrupted data") from err


# ---------- passwords (staff logins) ----------

# OWASP-equivalent row with low memory: 16 MiB per login instead of 128 MiB at N=2^17, p=1,
# so several simultaneous logins can't exhaust a small server. Stored in each hash.
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 5
SCRYPT_MAX_N = 2**20  # refuse stored hashes that would need absurd memory
SALT_BYTES, HASH_BYTES = 16, 32
PASSWORD_MIN, PASSWORD_MAX = 8, 256  # owner decision (D-011)
PASSWORD_CHARS = frozenset(chr(c) for c in range(0x20, 0x7F))  # standard keyboard (ASCII)


class PasswordPolicyError(ValueError):
    """The new password breaks a rule; the message lists every rule it breaks."""


def check_password_policy(password: str) -> None:
    """Raise PasswordPolicyError listing every broken rule (D-011)."""
    problems = []
    if len(password) < PASSWORD_MIN:
        problems.append(f"at least {PASSWORD_MIN} characters")
    if len(password) > PASSWORD_MAX:
        problems.append(f"at most {PASSWORD_MAX} characters")
    if not set(password) <= PASSWORD_CHARS:
        problems.append("only English letters, numbers, symbols and spaces")
    # Checked on ASCII only, so a Bangla digit or letter never counts toward a rule.
    if not any("A" <= c <= "Z" for c in password):
        problems.append("an uppercase letter")
    if not any("a" <= c <= "z" for c in password):
        problems.append("a lowercase letter")
    if not any("0" <= c <= "9" for c in password):
        problems.append("a number")
    if not any(c in string.punctuation for c in password):
        problems.append("a symbol")
    if problems:
        raise PasswordPolicyError("password must have: " + "; ".join(problems))


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    maxmem = 256 * n * r + 1024 * 1024  # scrypt needs 128*n*r bytes; allow headroom
    data = password.encode("utf-8")
    return hashlib.scrypt(data, salt=salt, n=n, r=r, p=p, maxmem=maxmem, dklen=HASH_BYTES)


def hash_password(password: str) -> str:
    """Check the rules, then return 'scrypt$N$r$p$salthex$hashhex'."""
    check_password_policy(password)
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _scrypt(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return "$".join(
        ["scrypt", str(SCRYPT_N), str(SCRYPT_R), str(SCRYPT_P), salt.hex(), digest.hex()]
    )


def verify_password(password: str, stored: str) -> bool:
    """True only for the right password. Malformed stored hashes and overlong input: False."""
    if len(password) > 4 * PASSWORD_MAX:  # don't spend scrypt time on junk input
        return False
    parts = stored.split("$")
    if len(parts) != 6 or parts[0] != "scrypt":
        return False
    try:
        n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
        salt, expected = bytes.fromhex(parts[4]), bytes.fromhex(parts[5])
    except ValueError:
        return False
    if not (2 <= n <= SCRYPT_MAX_N and 1 <= r <= 32 and 1 <= p <= 16):
        return False
    try:
        actual = _scrypt(password, salt, n, r, p)
    except ValueError:  # e.g. n not a power of two
        return False
    return hmac.compare_digest(actual, expected)


# ---------- webhook authenticity ----------


def verify_meta_signature(app_secret: str, body: bytes, header: str | None) -> bool:
    """Check Meta's X-Hub-Signature-256 header ('sha256=<64 hex>') against the raw body."""
    if not app_secret or not header or not header.startswith("sha256="):
        return False
    given = header[len("sha256=") :].lower()
    if len(given) != 64 or any(c not in "0123456789abcdef" for c in given):
        return False
    expected = hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(given, expected)


def verify_telegram_secret(expected: str, header: str | None) -> bool:
    """Check Telegram's X-Telegram-Bot-Api-Secret-Token header: exact match only."""
    if not expected or header is None:
        return False
    return hmac.compare_digest(header.encode("utf-8"), expected.encode("utf-8"))


# ---------- CSRF (staff forms) ----------

CSRF_MAX_AGE = 8 * 3600  # seconds; one working day (owner decision, D-011)
CSRF_MAX_SKEW = 60  # seconds a token's time may be ahead of ours (clock drift)


def _csrf_signature(session_secret: str, session_id: str, stamp: str) -> str:
    key = hmac.new(session_secret.encode("utf-8"), b"csrf-v1", hashlib.sha256).digest()
    message = f"{stamp}:{session_id}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def make_csrf_token(session_secret: str, session_id: str, now: float | None = None) -> str:
    stamp = str(int(time.time() if now is None else now))
    return f"{stamp}.{_csrf_signature(session_secret, session_id, stamp)}"


def check_csrf_token(
    session_secret: str, session_id: str, token: str | None, now: float | None = None
) -> bool:
    """Valid only for the same session, signed by us, and not older than CSRF_MAX_AGE."""
    if not session_id or not token or token.count(".") != 1:
        return False
    stamp, signature = token.split(".")
    if not (stamp.isascii() and stamp.isdigit()):
        return False
    age = (time.time() if now is None else now) - int(stamp)
    if age > CSRF_MAX_AGE or age < -CSRF_MAX_SKEW:
        return False
    expected = _csrf_signature(session_secret, session_id, stamp)
    return hmac.compare_digest(signature.encode(), expected.encode())

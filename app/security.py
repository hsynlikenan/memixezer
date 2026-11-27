"""Password hashing, generators, flag hashing and small safety helpers."""
import hashlib
import hmac
import re
import secrets
import unicodedata
from urllib.parse import urlparse

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from flask import current_app

_ph = PasswordHasher()

# No look-alike characters (0/O, 1/l/I) so credentials printed on paper are readable.
_PW_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
_PW_SYMBOLS = "!@#$%^&*-_=+"


# ---------- passwords ----------
def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        return _ph.verify(stored_hash, password)
    except (VerificationError, InvalidHashError):
        return False


# A real argon2 hash used to burn equal time when the username does not exist,
# so response time does not reveal which usernames are valid.
_DUMMY_HASH = _ph.hash(secrets.token_hex(16))


def burn_password_check(password: str) -> None:
    verify_password(_DUMMY_HASH, password)


def generate_password(length: int = 16) -> str:
    length = max(length, 14)
    while True:
        chars = [secrets.choice(_PW_ALPHABET) for _ in range(length - 2)]
        chars += [secrets.choice(_PW_SYMBOLS), secrets.choice("23456789")]
        secrets.SystemRandom().shuffle(chars)
        pw = "".join(chars)
        # First char must not be a symbol: spreadsheets treat leading = + - @ as formulas.
        if pw[0] not in _PW_SYMBOLS and any(c.islower() for c in pw) and any(c.isupper() for c in pw):
            return pw


def password_problems(password: str, min_length: int, username: str = "") -> list[str]:
    problems = []
    if len(password) < min_length:
        problems.append(f"Password must be at least {min_length} characters.")
    if len(password) > 128:
        problems.append("Password must be at most 128 characters.")
    if not (any(c.islower() for c in password) and any(c.isupper() for c in password)):
        problems.append("Use both upper and lower case letters.")
    if not any(c.isdigit() for c in password):
        problems.append("Include at least one digit.")
    if username and username.lower() in password.lower():
        problems.append("Password must not contain your username.")
    return problems


# ---------- usernames ----------
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")


def slugify_name(name: str) -> str:
    """'Əli Məmmədov' -> 'ali.memmedov' (ASCII, lower-case)."""
    folded = (name.replace("ə", "e").replace("Ə", "E").replace("ı", "i").replace("İ", "I")
              .replace("ş", "s").replace("Ş", "S").replace("ç", "c").replace("Ç", "C")
              .replace("ğ", "g").replace("Ğ", "G").replace("ö", "o").replace("Ö", "O")
              .replace("ü", "u").replace("Ü", "U"))
    ascii_name = unicodedata.normalize("NFKD", folded).encode("ascii", "ignore").decode()
    parts = re.findall(r"[a-z0-9]+", ascii_name.lower())
    return ".".join(parts)[:24]


def generate_username(name: str, taken: set[str]) -> str:
    """Unique username from a display name. `taken` is mutated with the result."""
    base = slugify_name(name) or "player"
    if len(base) < 3:
        base = f"{base}{secrets.choice('23456789')}{secrets.choice('23456789')}"
    candidate = base
    while candidate in taken:
        candidate = f"{base}{secrets.randbelow(900) + 100}"
    taken.add(candidate)
    return candidate


# ---------- flags ----------
def _pepper() -> bytes:
    return current_app.config["FLAG_PEPPER"].encode()


def new_salt() -> str:
    return secrets.token_hex(16)


def hash_flag(flag: str, salt: str) -> str:
    return hmac.new(_pepper(), f"{salt}:{flag}".encode(), hashlib.sha256).hexdigest()


def check_flag(submitted: str, salt: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_flag(submitted, salt), stored_hash)


# ---------- misc ----------
def csv_safe(value: str) -> str:
    """Neutralise spreadsheet formula injection in exported cells."""
    if value and value[0] in "=+-@\t\r":
        return "'" + value
    return value


def is_safe_next(target: str | None) -> bool:
    if not target:
        return False
    parsed = urlparse(target)
    return not parsed.scheme and not parsed.netloc and target.startswith("/") and not target.startswith("//") \
        and "\\" not in target

"""Bulk account creation and credential CSV export."""
import csv
import io

from ..extensions import db
from ..models import User, audit
from ..security import csv_safe, generate_password, generate_username, hash_password

MAX_BULK_USERS = 50
PASSWORD_LENGTH = 16
CSV_HEADER = ("display_name", "username", "password")


def parse_names(raw: str) -> list[str]:
    """One display name per line; blank lines dropped, whitespace collapsed."""
    names = []
    for line in (raw or "").splitlines():
        name = " ".join(line.split())
        if name:
            names.append(name)
    return names


def create_users(names: list[str], length: int = PASSWORD_LENGTH) -> list[dict]:
    """Stage one user per name in the session (caller commits). Returns plaintext credentials."""
    taken = {u for (u,) in db.session.query(User.username).all()}
    rows = []
    for name in names:
        username = generate_username(name, taken)
        password = generate_password(length)
        db.session.add(User(username=username, display_name=name, password_hash=hash_password(password),
                            role="user", must_change_password=True))
        rows.append({"display_name": name, "username": username, "password": password})
    return rows


def bulk_create_users(names: list[str], actor=None, ip: str | None = None) -> list[dict]:
    """Create one user per name (max MAX_BULK_USERS) in a single transaction.

    Returns [{"display_name", "username", "password"}]. The plaintext passwords exist
    only in this return value; only argon2 hashes are stored. All-or-nothing.
    """
    if not names:
        raise ValueError("No names given.")
    if len(names) > MAX_BULK_USERS:
        raise ValueError(f"At most {MAX_BULK_USERS} accounts can be created at once.")
    if any(len(n) > 80 for n in names):
        raise ValueError("Display names must be at most 80 characters.")

    try:
        created = create_users(names, PASSWORD_LENGTH)
        audit("users.bulk_create", f"count={len(created)}", actor=actor, ip=ip)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return created


def credentials_csv(rows: list[dict]) -> str:
    """CSV text of freshly created credentials, with formula-injection protection."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_HEADER)
    for r in rows:
        writer.writerow([csv_safe(r["display_name"]), csv_safe(r["username"]), csv_safe(r["password"])])
    return buf.getvalue()

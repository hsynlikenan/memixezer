import secrets
from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy import CheckConstraint, UniqueConstraint

from .extensions import db, login_manager

CATEGORIES = ("Web", "Crypto", "Forensics", "Linux", "Networking", "Misc")
DIFFICULTIES = ("Easy", "Medium", "Hard", "Insane")
ROLES = ("admin", "user")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # stored as naive UTC


def _in(column: str, values) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class User(UserMixin, db.Model):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(_in("role", ROLES), name="ck_users_role"),)

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(80), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(10), nullable=False, default="user")
    is_enabled = db.Column(db.Boolean, nullable=False, default=True)
    must_change_password = db.Column(db.Boolean, nullable=False, default=True)
    # Rotated on password change/reset/disable; part of the session id, so old sessions die.
    auth_token = db.Column(db.String(32), nullable=False, default=lambda: secrets.token_hex(16))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    last_login_at = db.Column(db.DateTime)

    solves = db.relationship("Solve", back_populates="user", cascade="all, delete-orphan")
    submissions = db.relationship("Submission", back_populates="user", cascade="all, delete-orphan")

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_active(self) -> bool:  # Flask-Login: disabled users cannot keep a session
        return self.is_enabled

    def get_id(self) -> str:
        return f"{self.id}:{self.auth_token}"

    def rotate_token(self) -> None:
        self.auth_token = secrets.token_hex(16)


@login_manager.user_loader
def load_user(session_id: str):
    try:
        raw_id, token = session_id.split(":", 1)
        user = db.session.get(User, int(raw_id))
    except (ValueError, AttributeError):
        return None
    if user is None or not user.is_enabled or not secrets.compare_digest(user.auth_token, token):
        return None
    return user


class Challenge(db.Model):
    __tablename__ = "challenges"
    __table_args__ = (
        CheckConstraint(_in("category", CATEGORIES), name="ck_challenges_category"),
        CheckConstraint(_in("difficulty", DIFFICULTIES), name="ck_challenges_difficulty"),
        CheckConstraint("points > 0", name="ck_challenges_points"),
    )

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(20), nullable=False, index=True)
    difficulty = db.Column(db.String(10), nullable=False)
    points = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    flag_salt = db.Column(db.String(32), nullable=False)
    flag_hash = db.Column(db.String(64), nullable=False)  # never sent to the browser
    file_path = db.Column(db.String(255))  # stored name inside uploads/
    file_name = db.Column(db.String(255))  # original name shown to users
    is_visible = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    solves = db.relationship("Solve", back_populates="challenge", cascade="all, delete-orphan")
    submissions = db.relationship("Submission", back_populates="challenge", cascade="all, delete-orphan")


class Solve(db.Model):
    """One row per (user, challenge). Points are awarded only by existence of this row."""
    __tablename__ = "solves"
    __table_args__ = (UniqueConstraint("user_id", "challenge_id", name="uq_solve_user_challenge"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    challenge_id = db.Column(db.Integer, db.ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False, index=True)
    points_awarded = db.Column(db.Integer, nullable=False)  # snapshot at solve time
    solved_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    user = db.relationship("User", back_populates="solves")
    challenge = db.relationship("Challenge", back_populates="solves")


class Submission(db.Model):
    """Every flag attempt. The submitted text is stored (truncated) for auditing."""
    __tablename__ = "submissions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    challenge_id = db.Column(db.Integer, db.ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False, index=True)
    submitted = db.Column(db.String(200), nullable=False)
    is_correct = db.Column(db.Boolean, nullable=False, default=False)
    ip = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    user = db.relationship("User", back_populates="submissions")
    challenge = db.relationship("Challenge", back_populates="submissions")


class Setting(db.Model):
    __tablename__ = "settings"

    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.String(255), nullable=False)

    DEFAULTS = {"scoreboard_visible": "1", "scoreboard_frozen_at": ""}

    @classmethod
    def get(cls, key: str) -> str:
        row = db.session.get(cls, key)
        return row.value if row else cls.DEFAULTS.get(key, "")

    @classmethod
    def set(cls, key: str, value: str) -> None:
        row = db.session.get(cls, key)
        if row:
            row.value = value
        else:
            db.session.add(cls(key=key, value=value))

    @classmethod
    def get_bool(cls, key: str) -> bool:
        return cls.get(key) == "1"


class AuditLog(db.Model):
    """Admin actions and security-relevant events."""
    __tablename__ = "audit_log"

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    action = db.Column(db.String(60), nullable=False, index=True)
    detail = db.Column(db.String(500), default="")
    ip = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    actor = db.relationship("User")


def audit(action: str, detail: str = "", actor=None, ip: str | None = None) -> None:
    """Queue an audit row on the session; the caller commits."""
    db.session.add(AuditLog(actor_id=getattr(actor, "id", None), action=action, detail=detail[:500], ip=ip))

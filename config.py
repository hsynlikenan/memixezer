"""Configuration. All secrets come from the environment (.env), never from code."""
import os
from datetime import timedelta


def _flag(name: str, default: bool = False) -> bool:
    return os.environ.get(name, "1" if default else "0").strip().lower() in ("1", "true", "yes", "on")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    FLAG_PEPPER = os.environ.get("FLAG_PEPPER")
    APP_NAME = os.environ.get("APP_NAME", "Cyber Arena")

    # Filled in by create_app() (instance/ctf.db) when DATABASE_URL is not set.
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Session / cookies
    SESSION_COOKIE_NAME = "ctf_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _flag("SESSION_COOKIE_SECURE", False)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_REFRESH_EACH_REQUEST = True

    # CSRF
    WTF_CSRF_TIME_LIMIT = 8 * 3600

    # Uploads (used from Step 4 on)
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024

    # Rate limiting
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = True
    LOGIN_LIMIT_PER_IP = "10/minute"
    LOGIN_LIMIT_PER_USER = "5/minute"

    # Accounts
    BULK_MAX_USERS = 50
    MIN_PASSWORD_LENGTH = 12
    GENERATED_PASSWORD_LENGTH = 16

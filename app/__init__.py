"""Application factory."""
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for
from flask_login import current_user
from sqlalchemy import event
from sqlalchemy.engine import Engine

from .extensions import csrf, db, limiter, login_manager

BASE_DIR = Path(__file__).resolve().parent.parent

_ALLOWED_WHEN_PW_CHANGE = {"auth.change_password", "auth.logout", "static"}


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_conn, _record):
    if dbapi_conn.__class__.__module__.startswith("sqlite3"):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


def create_app(test_config: dict | None = None) -> Flask:
    load_dotenv(BASE_DIR / ".env")
    from config import Config  # imported late: reads env at import time

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    for key in ("SECRET_KEY", "FLAG_PEPPER"):
        value = app.config.get(key) or ""
        if len(value) < 16:
            raise RuntimeError(f"{key} is missing or too short. Run `python setup_env.py` to generate a .env file.")

    os.makedirs(app.instance_path, exist_ok=True)
    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + (Path(app.instance_path) / "ctf.db").as_posix()

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    limiter.init_app(app)

    from .blueprints.admin import bp as admin_bp
    from .blueprints.auth import bp as auth_bp
    from .blueprints.challenges import bp as challenges_bp
    from .blueprints.main import bp as main_bp
    from .blueprints.scoreboard import bp as scoreboard_bp
    from .cli import register_cli

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(challenges_bp)
    app.register_blueprint(scoreboard_bp)
    app.register_blueprint(admin_bp)
    register_cli(app)

    @app.context_processor
    def _globals():
        return {"app_name": app.config["APP_NAME"]}

    @app.before_request
    def _force_password_change():
        if (current_user.is_authenticated and current_user.must_change_password
                and request.endpoint is not None
                and request.endpoint not in _ALLOWED_WHEN_PW_CHANGE):
            return redirect(url_for("auth.change_password"))

    @app.after_request
    def _headers(resp):
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; script-src 'self'; style-src 'self'; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        if app.config.get("SESSION_COOKIE_SECURE"):
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.endpoint != "static":
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    messages = {400: "Bad request.", 403: "You do not have access to this page.", 404: "Page not found.",
                405: "Method not allowed.", 413: "Upload too large.", 429: "Too many requests. Slow down."}

    def _make_handler(code):
        def handler(_err):
            if code == 500:
                db.session.rollback()
            return render_template("errors/error.html", code=code,
                                   message=messages.get(code, "Something went wrong.")), code
        return handler

    for code in (400, 403, 404, 405, 413, 429, 500):
        app.register_error_handler(code, _make_handler(code))

    with app.app_context():
        from . import models  # noqa: F401
        db.create_all()

    return app

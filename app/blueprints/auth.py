"""Login-only authentication: login, logout, forced first-login password change.

There is no self-registration; accounts are created by an admin (bulk service).
"""
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField
from wtforms.validators import DataRequired, EqualTo, Length

from ..extensions import client_ip, db, limiter
from ..models import User, audit, utcnow
from ..security import burn_password_check, hash_password, is_safe_next, password_problems, verify_password

bp = Blueprint("auth", __name__)

DEFAULT_LOGIN_LIMIT = "5 per minute"


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(max=64)])
    password = PasswordField("Password", validators=[DataRequired(), Length(max=128)])


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Current password", validators=[DataRequired(), Length(max=128)])
    new_password = PasswordField("New password", validators=[DataRequired(), Length(max=128)])
    confirm = PasswordField(
        "Confirm new password",
        validators=[DataRequired(), EqualTo("new_password", message="Passwords do not match.")],
    )


class CsrfOnlyForm(FlaskForm):
    """Carries only the CSRF token (used for logout)."""


def _ip_limit():
    return current_app.config.get("LOGIN_LIMIT_PER_IP", DEFAULT_LOGIN_LIMIT)


def _user_limit():
    return current_app.config.get("LOGIN_LIMIT_PER_USER", DEFAULT_LOGIN_LIMIT)


def _user_key():
    return "u:" + request.form.get("username", "").strip().lower()[:64]


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit(_ip_limit, methods=["POST"], scope="login-ip")
@limiter.limit(_user_limit, methods=["POST"], scope="login-user", key_func=_user_key)
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data.strip().lower()
        user = db.session.scalar(db.select(User).where(User.username == username))
        ok = False
        if user is None:
            burn_password_check(form.password.data)  # equalise timing for unknown users
        else:
            ok = verify_password(user.password_hash, form.password.data) and user.is_enabled
        if ok:
            session.clear()
            login_user(user)
            user.last_login_at = utcnow()
            audit("auth.login", actor=user, ip=client_ip())
            db.session.commit()
            if user.must_change_password:
                return redirect(url_for("auth.change_password"))
            nxt = request.args.get("next")
            return redirect(nxt if is_safe_next(nxt) else url_for("main.index"))
        audit("auth.login_failed", f"username={username[:64]}", ip=client_ip())
        db.session.commit()
        flash("Invalid username or password.", "error")
    return render_template("auth/login.html", form=form)


@bp.post("/logout")
@login_required
def logout():
    if CsrfOnlyForm().validate_on_submit():
        audit("auth.logout", actor=current_user, ip=client_ip())
        db.session.commit()
        logout_user()
        session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        user = current_user._get_current_object()
        new = form.new_password.data
        if not verify_password(user.password_hash, form.current_password.data):
            flash("Current password is incorrect.", "error")
        elif new == form.current_password.data:
            flash("New password must differ from the current one.", "error")
        else:
            problems = password_problems(new, current_app.config["MIN_PASSWORD_LENGTH"], user.username)
            if problems:
                for p in problems:
                    flash(p, "error")
            else:
                user.password_hash = hash_password(new)
                user.must_change_password = False
                user.rotate_token()  # invalidates every other session
                audit("auth.password_changed", actor=user, ip=client_ip())
                db.session.commit()
                login_user(user)  # fresh session carrying the new token
                flash("Password updated.", "success")
                return redirect(url_for("main.index"))
    return render_template(
        "auth/change_password.html",
        form=form,
        forced=current_user.must_change_password,
        min_length=current_app.config["MIN_PASSWORD_LENGTH"],
    )

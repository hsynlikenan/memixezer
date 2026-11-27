import json
import secrets
from functools import wraps
from pathlib import Path

from flask import (Blueprint, Response, abort, current_app, flash, redirect,
                   render_template, request, url_for)
from flask_login import current_user
from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from werkzeug.utils import secure_filename
from wtforms import BooleanField, IntegerField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange

from ..extensions import client_ip, db, login_manager
from ..forms import BulkUserForm
from sqlalchemy import func

from ..models import (CATEGORIES, DIFFICULTIES, AuditLog, Challenge, Setting, Solve, Submission, User,
                      audit, utcnow)
from ..security import generate_password, hash_flag, hash_password, new_salt
from ..services.users import MAX_BULK_USERS, PASSWORD_LENGTH, bulk_create_users, credentials_csv

bp = Blueprint("admin", __name__, url_prefix="/admin")

ALLOWED_EXT = {".txt", ".zip", ".pcap", ".pcapng", ".png", ".jpg", ".jpeg", ".gif", ".pdf",
               ".gz", ".tar", ".7z", ".bin", ".elf", ".py", ".c", ".pem", ".log", ".json"}
PER_PAGE = 50


class CsrfForm(FlaskForm):
    """Empty form: CSRF validation for POST-only actions."""


class ChallengeForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=120)])
    category = SelectField("Category", choices=[(c, c) for c in CATEGORIES])
    difficulty = SelectField("Difficulty", choices=[(d, d) for d in DIFFICULTIES])
    points = IntegerField("Points", validators=[DataRequired(), NumberRange(min=1, max=10000)])
    description = TextAreaField("Description", validators=[Length(max=10000)])
    flag = StringField("Flag (leave blank to keep current)", validators=[Length(max=200)])
    file = FileField("Attachment")
    is_visible = BooleanField("Visible", default=True)


def admin_required(view):
    @wraps(view)
    def wrapped(*a, **k):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        if not current_user.is_admin:
            abort(403)
        return view(*a, **k)
    return wrapped


def _upload_dir() -> Path:
    d = Path(current_app.config.get("UPLOAD_FOLDER") or Path(current_app.root_path).parent / "uploads")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_upload(f) -> tuple[str, str] | None:
    """Store an upload under a random name; returns (stored_name, original_name)."""
    if not f or not f.filename:
        return None
    original = secure_filename(f.filename)
    ext = Path(original).suffix.lower()
    if not original or ext not in ALLOWED_EXT:
        raise ValueError("File type not allowed.")
    stored = secrets.token_hex(16) + ext
    f.save(_upload_dir() / stored)
    return stored, original[:255]


def _remove_file(stored: str | None) -> None:
    if stored and Path(stored).name == stored:
        (_upload_dir() / stored).unlink(missing_ok=True)


def _log(action: str, detail: str = "") -> None:
    audit(action, detail, actor=current_user, ip=client_ip())


@bp.get("/")
@admin_required
def index():
    def count(stmt):
        return db.session.scalar(stmt) or 0
    kpis = {
        "players": count(db.select(func.count(User.id)).where(User.role == "user")),
        "challenges": count(db.select(func.count(Challenge.id))),
        "solves": count(db.select(func.count(Solve.id))),
        "submissions": count(db.select(func.count(Submission.id))),
    }
    recent = db.session.scalars(db.select(Submission).order_by(Submission.id.desc()).limit(10)).all()
    return render_template("admin/dashboard.html", kpis=kpis, recent=recent, form=CsrfForm(),
                           scoreboard_visible=Setting.get_bool("scoreboard_visible"),
                           frozen=bool(Setting.get("scoreboard_frozen_at")))


# ---- challenges -----------------------------------------------------------------------------

@bp.get("/challenges")
@admin_required
def challenges():
    rows = db.session.scalars(db.select(Challenge).order_by(Challenge.category, Challenge.points, Challenge.id)).all()
    return render_template("admin/challenges.html", challenges=rows, form=CsrfForm())


def _apply(form: ChallengeForm, ch: Challenge, creating: bool) -> bool:
    if creating and not form.flag.data.strip():
        form.flag.errors.append("Flag is required.")
        return False
    try:
        saved = _save_upload(form.file.data)
    except ValueError as e:
        form.file.errors.append(str(e))
        return False
    ch.title, ch.category, ch.difficulty = form.title.data.strip(), form.category.data, form.difficulty.data
    ch.points, ch.description, ch.is_visible = form.points.data, form.description.data or "", form.is_visible.data
    if form.flag.data.strip():
        ch.flag_salt = new_salt()
        ch.flag_hash = hash_flag(form.flag.data.strip(), ch.flag_salt)
    if saved:
        old, ch.file_path, ch.file_name = ch.file_path, *saved
        _remove_file(old)
    return True


@bp.route("/challenges/new", methods=["GET", "POST"])
@admin_required
def challenge_new():
    form = ChallengeForm()
    if form.validate_on_submit():
        ch = Challenge()
        if _apply(form, ch, creating=True):
            db.session.add(ch)
            db.session.flush()
            _log("challenge.create", f"id={ch.id} title={ch.title}")
            db.session.commit()
            flash("Challenge created.", "success")
            return redirect(url_for("admin.challenges"))
    return render_template("admin/challenge_form.html", form=form, challenge=None)


@bp.route("/challenges/<int:challenge_id>/edit", methods=["GET", "POST"])
@admin_required
def challenge_edit(challenge_id: int):
    ch = db.get_or_404(Challenge, challenge_id)
    form = ChallengeForm(obj=ch)
    if form.validate_on_submit():
        if _apply(form, ch, creating=False):
            _log("challenge.edit", f"id={ch.id}")
            db.session.commit()
            flash("Challenge updated.", "success")
            return redirect(url_for("admin.challenges"))
        db.session.rollback()
    return render_template("admin/challenge_form.html", form=form, challenge=ch)


@bp.post("/challenges/<int:challenge_id>/visibility")
@admin_required
def challenge_visibility(challenge_id: int):
    if CsrfForm().validate_on_submit():
        ch = db.get_or_404(Challenge, challenge_id)
        ch.is_visible = not ch.is_visible
        _log("challenge.show" if ch.is_visible else "challenge.hide", f"id={ch.id}")
        db.session.commit()
    return redirect(url_for("admin.challenges"))


@bp.post("/challenges/<int:challenge_id>/delete")
@admin_required
def challenge_delete(challenge_id: int):
    if CsrfForm().validate_on_submit():
        ch = db.get_or_404(Challenge, challenge_id)
        stored, title = ch.file_path, ch.title
        db.session.delete(ch)
        _log("challenge.delete", f"id={challenge_id} title={title}")
        db.session.commit()
        _remove_file(stored)
        flash("Challenge deleted.", "success")
    return redirect(url_for("admin.challenges"))


# ---- users ----------------------------------------------------------------------------------

@bp.get("/users")
@admin_required
def users():
    rows = db.session.scalars(db.select(User).order_by(User.id)).all()
    return render_template("admin/users.html", users=rows, form=CsrfForm())


def _credentials_page(rows: list[dict], title: str):
    return render_template("admin/credentials.html", title=title, rows=rows,
                           payload=json.dumps(rows), csrf_form=CsrfForm())


@bp.route("/users/bulk", methods=["GET", "POST"])
@admin_required
def bulk_create():
    form = BulkUserForm()
    if form.validate_on_submit():
        try:
            rows = bulk_create_users(form.parsed_names, actor=current_user, ip=client_ip())
        except ValueError as e:
            flash(str(e), "error")
        else:
            return _credentials_page(rows, "New accounts")
    return render_template("admin/bulk.html", form=form, max_users=MAX_BULK_USERS)


@bp.post("/credentials.csv")
@bp.post("/users/credentials.csv")
@admin_required
def credentials_download():
    if not CsrfForm().validate_on_submit():
        abort(400)
    try:
        rows = json.loads(request.form.get("payload", "[]"))
        keys = ("display_name", "username", "password")
        if not isinstance(rows, list) or not rows or len(rows) > MAX_BULK_USERS:
            raise ValueError("payload must be a non-empty list")
        if any(not isinstance(r, dict) or set(r) != set(keys) for r in rows):
            raise ValueError("unexpected row shape")
        rows = [{k: str(r[k]) for k in keys} for r in rows]
    except (ValueError, KeyError, TypeError):
        abort(400)
    _log("users.credentials_export", f"count={len(rows)}")
    db.session.commit()
    return Response(credentials_csv(rows), mimetype="text/csv", headers={
        "Content-Disposition": 'attachment; filename="credentials.csv"', "Cache-Control": "no-store"})


def _target_user(user_id: int) -> User:
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id:
        abort(403)  # admins cannot disable or reset themselves
    return user


@bp.post("/users/<int:user_id>/reset")
@admin_required
def reset_password(user_id: int):
    if not CsrfForm().validate_on_submit():
        abort(400)
    user = _target_user(user_id)
    password = generate_password(PASSWORD_LENGTH)
    user.password_hash = hash_password(password)
    user.must_change_password = True
    user.rotate_token()
    _log("user.reset_password", f"user={user.username}")
    db.session.commit()
    return _credentials_page([{"display_name": user.display_name, "username": user.username,
                               "password": password}], "Password reset")


@bp.post("/users/<int:user_id>/toggle")
@admin_required
def toggle_user(user_id: int):
    if CsrfForm().validate_on_submit():
        user = _target_user(user_id)
        user.is_enabled = not user.is_enabled
        if not user.is_enabled:
            user.rotate_token()
        _log("user.enable" if user.is_enabled else "user.disable", f"user={user.username}")
        db.session.commit()
    return redirect(url_for("admin.users"))


# ---- logs -----------------------------------------------------------------------------------

@bp.get("/submissions")
@admin_required
def submissions():
    page = db.paginate(db.select(Submission).order_by(Submission.id.desc()), per_page=PER_PAGE, error_out=False)
    return render_template("admin/submissions.html", page=page)


@bp.get("/audit")
@admin_required
def audit_log():
    page = db.paginate(db.select(AuditLog).order_by(AuditLog.id.desc()), per_page=PER_PAGE, error_out=False)
    return render_template("admin/audit.html", page=page)


# ---- scoreboard switches --------------------------------------------------------------------

@bp.post("/scoreboard/visibility")
@admin_required
def toggle_scoreboard():
    if CsrfForm().validate_on_submit():
        on = not Setting.get_bool("scoreboard_visible")
        Setting.set("scoreboard_visible", "1" if on else "0")
        _log("scoreboard.show" if on else "scoreboard.hide")
        db.session.commit()
    return redirect(url_for("admin.index"))


@bp.post("/scoreboard/freeze")
@admin_required
def toggle_freeze():
    if CsrfForm().validate_on_submit():
        frozen = bool(Setting.get("scoreboard_frozen_at"))
        Setting.set("scoreboard_frozen_at", "" if frozen else utcnow().isoformat())
        _log("scoreboard.unfreeze" if frozen else "scoreboard.freeze")
        db.session.commit()
    return redirect(url_for("admin.index"))

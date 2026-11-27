from pathlib import Path

from flask import Blueprint, abort, current_app, jsonify, render_template, request, send_from_directory
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from ..extensions import client_ip, db, limiter
from ..models import CATEGORIES, DIFFICULTIES, Challenge, Solve, Submission
from ..security import check_flag

bp = Blueprint("challenges", __name__, url_prefix="/challenges")


def _get_challenge(challenge_id: int) -> Challenge:
    """Fetch a challenge; hidden ones look like they don't exist to non-admins."""
    ch = db.session.get(Challenge, challenge_id)
    if ch is None or (not ch.is_visible and not current_user.is_admin):
        abort(404)
    return ch


def _is_solved(challenge_id: int) -> bool:
    return db.session.query(Solve.id).filter_by(user_id=current_user.id, challenge_id=challenge_id).first() is not None


@bp.get("/")
@login_required
def index():
    category = request.args.get("category")
    if category not in CATEGORIES:
        category = None
    difficulty = request.args.get("difficulty")
    if difficulty not in DIFFICULTIES:
        difficulty = None
    query = db.select(Challenge).order_by(Challenge.category, Challenge.points, Challenge.id)
    if not current_user.is_admin:
        query = query.where(Challenge.is_visible.is_(True))
    # All challenges are rendered; non-matching ones get a hidden class so the
    # page works without JS and challenges.js can re-filter instantly.
    solved = set(db.session.scalars(db.select(Solve.challenge_id).where(Solve.user_id == current_user.id)))
    return render_template("challenges/list.html", challenges=db.session.scalars(query).all(),
                           categories=CATEGORIES, difficulties=DIFFICULTIES, category=category,
                           difficulty=difficulty, solved=solved)


@bp.get("/<int:challenge_id>")
@login_required
def detail(challenge_id: int):
    ch = _get_challenge(challenge_id)
    return jsonify(id=ch.id, title=ch.title, category=ch.category, difficulty=ch.difficulty,
                   points=ch.points, description=ch.description, solved=_is_solved(ch.id),
                   has_file=bool(ch.file_path), file_name=ch.file_name)


@bp.post("/<int:challenge_id>/submit")
@login_required
@limiter.limit("10 per minute")
def submit(challenge_id: int):
    ch = _get_challenge(challenge_id)
    if _is_solved(ch.id):
        return jsonify(correct=True, points=0, message="Already solved.")

    submitted = (request.form.get("flag") or "").strip()[:200]
    correct = bool(submitted) and check_flag(submitted, ch.flag_salt, ch.flag_hash)
    db.session.add(Submission(user_id=current_user.id, challenge_id=ch.id, submitted=submitted,
                              is_correct=correct, ip=client_ip()))
    awarded = 0
    if correct:
        db.session.add(Solve(user_id=current_user.id, challenge_id=ch.id, points_awarded=ch.points))
        awarded = ch.points
    try:
        db.session.commit()
    except IntegrityError:  # concurrent duplicate solve: unique constraint blocks double points
        db.session.rollback()
        return jsonify(correct=True, points=0, message="Already solved.")
    if not correct:
        return jsonify(correct=False, points=0, message="Incorrect flag."), 200
    return jsonify(correct=True, points=awarded, message=f"Correct! +{awarded} points.")


@bp.get("/<int:challenge_id>/file")
@login_required
def download(challenge_id: int):
    ch = _get_challenge(challenge_id)
    if not ch.file_path:
        abort(404)
    folder = current_app.config.get("UPLOAD_FOLDER") or Path(current_app.root_path).parent / "uploads"
    return send_from_directory(folder, ch.file_path, as_attachment=True,
                               download_name=ch.file_name or ch.file_path)

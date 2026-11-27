from flask import Blueprint, abort, jsonify, render_template
from flask_login import current_user, login_required

from sqlalchemy import func

from ..extensions import db
from ..models import Challenge, Setting, User
from ..services import scoring

bp = Blueprint("main", __name__)


@bp.get("/")
def index():
    stats = {
        "players": db.session.scalar(db.select(func.count(User.id)).where(
            User.role == "user", User.is_enabled.is_(True))) or 0,
        "challenges": db.session.scalar(db.select(func.count(Challenge.id)).where(
            Challenge.is_visible.is_(True))) or 0,
        "points": db.session.scalar(db.select(func.coalesce(func.sum(Challenge.points), 0)).where(
            Challenge.is_visible.is_(True))) or 0,
    }
    return render_template("index.html", stats=stats,
                           scoreboard_visible=Setting.get_bool("scoreboard_visible"))


@bp.get("/scoreboard.json")
@login_required
def scoreboard():
    if not Setting.get_bool("scoreboard_visible") and not current_user.is_admin:
        abort(404)
    frozen = scoring.frozen_at()
    return jsonify(
        frozen_at=frozen.isoformat() if frozen else None,
        you=scoring.user_score(current_user.id),
        entries=scoring.leaderboard(),
    )

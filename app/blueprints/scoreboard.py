from flask import Blueprint, abort, render_template
from flask_login import current_user, login_required

from ..models import Setting
from ..services import scoring

bp = Blueprint("scoreboard", __name__)


@bp.get("/scoreboard")
@login_required
def index():
    if not Setting.get_bool("scoreboard_visible") and not current_user.is_admin:
        abort(404)
    return render_template("scoreboard.html", entries=scoring.leaderboard(),
                           frozen=scoring.frozen_at(), you=scoring.user_score(current_user.id))

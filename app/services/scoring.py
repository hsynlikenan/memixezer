from datetime import datetime

from sqlalchemy import func, select

from ..extensions import db
from ..models import Setting, Solve, User


def frozen_at() -> datetime | None:
    """Freeze time set by an admin (naive UTC ISO string), or None."""
    raw = Setting.get("scoreboard_frozen_at")
    try:
        return datetime.fromisoformat(raw) if raw else None
    except ValueError:
        return None


def leaderboard(limit: int = 100) -> list[dict]:
    """Ranked players. Ties go to whoever reached the score first. Honors the freeze time."""
    score = func.coalesce(func.sum(Solve.points_awarded), 0)
    last = func.max(Solve.solved_at)
    join_on = Solve.user_id == User.id
    if (cutoff := frozen_at()) is not None:
        join_on = join_on & (Solve.solved_at <= cutoff)
    rows = db.session.execute(
        select(User.id, User.display_name, score, last, func.count(Solve.id))
        .outerjoin(Solve, join_on)
        .where(User.role == "user", User.is_enabled.is_(True))
        .group_by(User.id)
        .having(func.count(Solve.id) > 0)
        .order_by(score.desc(), last.asc(), User.id)
        .limit(limit)
    ).all()
    return [
        {"rank": i, "user_id": uid, "name": name, "score": int(pts), "solves": n,
         "last_solve": ts.isoformat() if ts else None}
        for i, (uid, name, pts, ts, n) in enumerate(rows, 1)
    ]


def user_score(user_id: int) -> int:
    return int(db.session.scalar(
        select(func.coalesce(func.sum(Solve.points_awarded), 0)).where(Solve.user_id == user_id)
    ))

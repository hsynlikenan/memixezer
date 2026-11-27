import json

import pytest

from app import create_app
from app.extensions import db
from app.models import User
from app.security import verify_password
from tests.conftest import ADMIN_PW, USER_PW, login, make_user


def get_user(app, username):
    with app.app_context():
        return User.query.filter_by(username=username).first()


# ---------- login ----------

def test_login_success_redirects(app, client):
    make_user(app, "alice", USER_PW)
    r = login(client, "alice", USER_PW)
    assert r.status_code == 302


def test_login_failures_share_generic_message(app, client):
    make_user(app, "alice", USER_PW)
    make_user(app, "bob", USER_PW, enabled=False)
    bodies = []
    for u, p in [("alice", "wrong-password-1"), ("nobody", "whatever-pass-1"), ("bob", USER_PW)]:
        r = login(client, u, p)
        assert r.status_code == 200
        assert b"Invalid username or password." in r.data
        bodies.append(r.data)


def test_logout_requires_post(client, admin_client):
    assert admin_client.get("/logout").status_code == 405
    assert admin_client.post("/logout").status_code == 302


def test_safe_next_only(app, client):
    make_user(app, "alice", USER_PW)
    r = client.post("/login?next=https://evil.example/", data={"username": "alice", "password": USER_PW})
    assert r.status_code == 302
    assert "evil.example" not in r.headers["Location"]


# ---------- forced password change ----------

def test_must_change_forces_redirect_and_flow(app, client):
    make_user(app, "carol", USER_PW, must_change=True)
    assert login(client, "carol", USER_PW).status_code == 302
    r = client.get("/")
    assert r.status_code == 302 and "change-password" in r.headers["Location"]

    new_pw = "Brand-New-Passw0rd!!"
    r = client.post(
        "/change-password",
        data={"current_password": USER_PW, "new_password": new_pw, "confirm": new_pw},
        follow_redirects=True,
    )
    assert b"Password updated." in r.data
    assert client.get("/").status_code == 200
    u = get_user(app, "carol")
    assert not u.must_change_password
    assert verify_password(u.password_hash, new_pw)


def test_change_password_rejects_weak_and_mismatch(app, client):
    make_user(app, "carol", USER_PW, must_change=True)
    login(client, "carol", USER_PW)
    r = client.post("/change-password", data={"current_password": USER_PW, "new_password": "short", "confirm": "short"})
    assert r.status_code == 200
    assert get_user(app, "carol").must_change_password
    r = client.post(
        "/change-password",
        data={"current_password": USER_PW, "new_password": "Another-Passw0rd!!", "confirm": "Different-Passw0rd!!"},
    )
    assert r.status_code == 200
    assert get_user(app, "carol").must_change_password


def test_change_password_rotates_token_and_kills_other_session(app):
    make_user(app, "dave", USER_PW)
    c1, c2 = app.test_client(), app.test_client()
    login(c1, "dave", USER_PW)
    login(c2, "dave", USER_PW)
    new_pw = "Brand-New-Passw0rd!!"
    c1.post("/change-password", data={"current_password": USER_PW, "new_password": new_pw, "confirm": new_pw})
    r = c2.get("/admin/users")
    assert r.status_code in (302, 401)  # no longer authenticated


# ---------- admin access ----------

def test_admin_routes_protected(app, client):
    assert client.get("/admin/users").status_code == 302
    make_user(app, "alice", USER_PW)
    login(client, "alice", USER_PW)
    assert client.get("/admin/users").status_code == 403
    assert client.get("/admin/users/bulk").status_code == 403
    assert client.post("/admin/users/bulk", data={"names": "X Y"}).status_code == 403


def test_admin_can_view_users(admin_client):
    assert admin_client.get("/admin/users").status_code == 200


# ---------- bulk creation ----------

def test_bulk_create(app, admin_client):
    names = "Ali Valiyev\nAli Valiyev\nLeyla Məmmədova\nJohn Smith"
    r = admin_client.post("/admin/users/bulk", data={"names": names})
    assert r.status_code == 200
    assert "no-store" in r.headers.get("Cache-Control", "")
    with app.app_context():
        users = User.query.filter(User.role == "user").all()
        assert len(users) == 4
        assert len({u.username for u in users}) == 4
        assert all(u.must_change_password for u in users)


def test_bulk_limit(app, admin_client):
    names = "\n".join(f"Player Number{i}" for i in range(51))
    r = admin_client.post("/admin/users/bulk", data={"names": names})
    assert r.status_code == 200
    with app.app_context():
        assert User.query.filter_by(role="user").count() == 0


def test_bulk_empty(app, admin_client):
    r = admin_client.post("/admin/users/bulk", data={"names": "  \n "})
    assert r.status_code == 200
    with app.app_context():
        assert User.query.filter_by(role="user").count() == 0


def test_generated_passwords_long_and_work(app, admin_client):
    from app.services.users import create_users

    with app.app_context():
        rows = create_users(["Test Person"], 16)
        db.session.commit()
        row = rows[0]
        assert len(row["password"]) >= 14
        u = User.query.filter_by(username=row["username"]).first()
        assert verify_password(u.password_hash, row["password"])


# ---------- CSV ----------

def _csv(client, rows):
    return client.post("/admin/credentials.csv", data={"payload": json.dumps(rows)})


def test_csv_valid(admin_client):
    r = _csv(admin_client, [{"display_name": "=cmd", "username": "u1", "password": "pw"}])
    assert r.status_code == 200
    assert r.mimetype == "text/csv"
    assert "attachment" in r.headers["Content-Disposition"]
    assert b"'=cmd" in r.data


@pytest.mark.parametrize(
    "payload",
    ["not json", "[]", '{"a":1}', '[{"display_name":"x"}]', '[{"display_name":"x","username":"y","password":"z","extra":"1"}]'],
)
def test_csv_invalid(admin_client, payload):
    assert admin_client.post("/admin/credentials.csv", data={"payload": payload}).status_code == 400


def test_csv_requires_admin(app, client):
    make_user(app, "alice", USER_PW)
    login(client, "alice", USER_PW)
    assert _csv(client, [{"display_name": "a", "username": "b", "password": "c"}]).status_code == 403


# ---------- reset / toggle ----------

def test_reset_password(app, admin_client):
    uid = make_user(app, "erin", USER_PW)
    old = get_user(app, "erin")
    old_token = old.auth_token
    r = admin_client.post(f"/admin/users/{uid}/reset")
    assert r.status_code == 200
    u = get_user(app, "erin")
    assert u.must_change_password
    assert u.auth_token != old_token
    assert not verify_password(u.password_hash, USER_PW)


def test_toggle_disable_blocks_login_and_session(app, admin_client):
    uid = make_user(app, "frank", USER_PW)
    other = app.test_client()
    login(other, "frank", USER_PW)
    assert other.get("/change-password").status_code == 200
    assert admin_client.post(f"/admin/users/{uid}/toggle").status_code == 302
    assert not get_user(app, "frank").is_enabled
    assert other.get("/change-password").status_code in (302, 401)
    r = login(app.test_client(), "frank", USER_PW)
    assert r.status_code == 200 and b"Invalid username or password." in r.data


def test_self_actions_forbidden_and_unknown_404(app, admin_client):
    aid = get_user(app, "admin").id
    assert admin_client.post(f"/admin/users/{aid}/toggle").status_code == 403
    assert admin_client.post(f"/admin/users/{aid}/reset").status_code == 403
    assert admin_client.post("/admin/users/99999/toggle").status_code == 404


# ---------- CLI ----------

def test_cli_create_admin(app):
    runner = app.test_cli_runner()
    res = runner.invoke(args=["create-admin", "--username", "boss", "--password", "Sup3r-Long-Passw0rd!"])
    assert res.exit_code == 0, res.output
    assert "Admin 'boss' created." in res.output
    u = get_user(app, "boss")
    assert u.is_admin and verify_password(u.password_hash, "Sup3r-Long-Passw0rd!")


# ---------- CSRF & rate limit (dedicated apps) ----------

def _strict_app(tmp_path, **extra):
    cfg = {
        "TESTING": True,
        "SECRET_KEY": "test-secret-key-0123456789",
        "FLAG_PEPPER": "test-pepper-0123456789",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'strict.db'}",
    }
    cfg.update(extra)
    return create_app(cfg)


def test_csrf_enforced(tmp_path):
    app = _strict_app(tmp_path, WTF_CSRF_ENABLED=True, RATELIMIT_ENABLED=False)
    make_user(app, "alice", USER_PW)
    r = app.test_client().post("/login", data={"username": "alice", "password": USER_PW})
    assert r.status_code == 400
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def test_login_rate_limited(tmp_path):
    app = _strict_app(tmp_path, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=True)
    make_user(app, "alice", USER_PW)
    c = app.test_client()
    codes = [login(c, "alice", "wrong-password-xx").status_code for _ in range(12)]
    assert 429 in codes
    with app.app_context():
        db.session.remove()
        db.engine.dispose()

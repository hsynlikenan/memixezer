"""Smoke tests: every page renders, the player flow works end to end, admin pages load."""
import io
import re

from app.extensions import db
from app.models import Challenge
from app.security import hash_flag, new_salt

from tests.conftest import USER_PW, login, make_user

FLAG = "flag{smoke_test}"


def make_challenge(app, title="Smoke", category="Web", difficulty="Easy", points=100, **kw):
    with app.app_context():
        salt = new_salt()
        ch = Challenge(title=title, category=category, difficulty=difficulty, points=points,
                       description="Line one\n\nLine two", flag_salt=salt,
                       flag_hash=hash_flag(FLAG, salt), **kw)
        db.session.add(ch)
        db.session.commit()
        return ch.id


def no_inline_code(html: str):
    # Strict CSP: no inline scripts or style attributes.
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), "inline <script> found"
    assert " style=" not in html, "inline style attribute found"


def test_public_pages(client, app):
    make_challenge(app)
    r = client.get("/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    no_inline_code(html)
    assert 'data-count="100"' in html  # total points stat
    assert client.get("/login").status_code == 200
    assert client.get("/challenges/").status_code == 302  # login required
    assert client.get("/does-not-exist").status_code == 404


def test_player_flow(client, app):
    cid = make_challenge(app)
    make_challenge(app, title="Other", category="Crypto", difficulty="Hard", points=300)
    make_user(app, "player1", USER_PW)
    assert login(client, "player1", USER_PW).status_code == 302

    r = client.get("/challenges/")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Smoke" in html and "Other" in html
    no_inline_code(html)

    r = client.get("/challenges/?category=Crypto&difficulty=Hard")
    assert "Other" in r.get_data(as_text=True)

    d = client.get(f"/challenges/{cid}").get_json()
    assert d["title"] == "Smoke" and d["solved"] is False and "flag_hash" not in d

    bad = client.post(f"/challenges/{cid}/submit", data={"flag": "flag{nope}"}).get_json()
    assert bad["correct"] is False
    ok = client.post(f"/challenges/{cid}/submit", data={"flag": FLAG}).get_json()
    assert ok["correct"] is True and ok["points"] == 100
    again = client.post(f"/challenges/{cid}/submit", data={"flag": FLAG}).get_json()
    assert again["points"] == 0

    r = client.get("/scoreboard")
    assert r.status_code == 200
    no_inline_code(r.get_data(as_text=True))
    sb = client.get("/scoreboard.json").get_json()
    assert sb["you"] == 100 and sb["entries"][0]["score"] == 100

    assert client.get("/change-password").status_code == 200
    assert client.get("/admin/").status_code in (403, 404)


def test_admin_pages(admin_client, app):
    cid = make_challenge(app)
    for url in ["/admin/", "/admin/challenges", "/admin/challenges/new",
                f"/admin/challenges/{cid}/edit", "/admin/users", "/admin/users/bulk",
                "/admin/submissions", "/admin/audit", "/scoreboard"]:
        r = admin_client.get(url)
        assert r.status_code == 200, url
        html = r.get_data(as_text=True)
        no_inline_code(html)
        if url.startswith("/admin"):
            assert "css/admin.css" in html, url


def test_admin_creates_challenge_with_file(admin_client, app):
    r = admin_client.post("/admin/challenges/new", data={
        "title": "Uploaded", "category": "Forensics", "difficulty": "Medium", "points": "250",
        "description": "Look inside.", "flag": "flag{file}", "is_visible": "y",
        "file": (io.BytesIO(b"hello"), "evidence.txt"),
    }, content_type="multipart/form-data")
    assert r.status_code == 302
    with app.app_context():
        ch = Challenge.query.filter_by(title="Uploaded").one()
        assert ch.file_name == "evidence.txt"
        cid = ch.id
    r = admin_client.get(f"/challenges/{cid}/file")
    assert r.status_code == 200 and r.data == b"hello"


def test_bulk_create(admin_client):
    r = admin_client.post("/admin/users/bulk", data={"names": "Ada Lovelace\nAlan Turing"})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "ada" in html.lower() and "alan" in html.lower()

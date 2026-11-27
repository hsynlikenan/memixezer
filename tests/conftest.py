import pytest

from app import create_app
from app.extensions import db
from app.models import User
from app.security import hash_password


@pytest.fixture()
def app(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key-0123456789",
            "FLAG_PEPPER": "test-pepper-0123456789",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
            "WTF_CSRF_ENABLED": False,
            "RATELIMIT_ENABLED": False,
        }
    )
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture()
def client(app):
    return app.test_client()


def make_user(app, username, password, role="user", must_change=False, enabled=True):
    with app.app_context():
        u = User(
            username=username,
            display_name=username.title(),
            role=role,
            password_hash=hash_password(password),
            must_change_password=must_change,
            is_enabled=enabled,
        )
        db.session.add(u)
        db.session.commit()
        return u.id


def login(client, username, password, **kw):
    return client.post("/login", data={"username": username, "password": password}, **kw)


ADMIN_PW = "Adm1n-Str0ng-Pass!"
USER_PW = "Us3r-Str0ng-Pass!!"


@pytest.fixture()
def admin(app):
    make_user(app, "admin", ADMIN_PW, role="admin")
    return "admin"


@pytest.fixture()
def admin_client(app, client, admin):
    r = login(client, "admin", ADMIN_PW)
    assert r.status_code == 302
    return client

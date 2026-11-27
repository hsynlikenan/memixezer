from flask import request
from flask_limiter import Limiter
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect


def client_ip() -> str:
    # Uses the direct peer address. If you deploy behind a reverse proxy, wrap the
    # app in werkzeug's ProxyFix so remote_addr is the real client address.
    return request.remote_addr or "unknown"


db = SQLAlchemy()
csrf = CSRFProtect()
login_manager = LoginManager()
limiter = Limiter(key_func=client_ip)

login_manager.login_view = "auth.login"
login_manager.session_protection = "strong"
login_manager.login_message = "Please sign in to continue."
login_manager.login_message_category = "info"

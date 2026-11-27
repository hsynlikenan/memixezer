import click

from .extensions import db
from .models import User, audit
from .security import USERNAME_RE, hash_password, password_problems


def register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """Create all database tables (safe to run repeatedly)."""
        db.create_all()
        click.echo("Database initialised.")

    @app.cli.command("create-admin")
    @click.option("--username", envvar="ADMIN_USERNAME", prompt=True, help="Admin username.")
    @click.option("--password", envvar="ADMIN_PASSWORD", prompt=True, hide_input=True,
                  confirmation_prompt=True, help="Admin password.")
    def create_admin(username, password):
        """Create the first (or another) admin account."""
        username = username.strip().lower()
        if not USERNAME_RE.match(username):
            raise click.ClickException("Username: 3-32 chars, a-z 0-9 . _ - and must start with a letter/digit.")
        problems = password_problems(password, app.config["MIN_PASSWORD_LENGTH"], username)
        if problems:
            raise click.ClickException(" ".join(problems))
        if db.session.scalar(db.select(User).where(User.username == username)):
            raise click.ClickException(f"User '{username}' already exists.")
        db.session.add(User(username=username, display_name=username, role="admin",
                            password_hash=hash_password(password), must_change_password=False))
        audit("admin.create_cli", f"username={username}")
        db.session.commit()
        click.echo(f"Admin '{username}' created.")

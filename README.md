# Cyber Arena — CTF Platform

A self-hosted Capture-the-Flag platform built with Flask. It uses a dark navy and gold interface:

- `#060B14` navy background
- `#0F2035` panels
- `#C9A44C` gold accents
- `#F5EEE2` cream headlines

## Features

- **Challenge board**:
  - Category and difficulty filters.
  - Hover-lift cards.
  - A detail modal with file downloads.
  - Flag submission over AJAX.
- **Live scoreboard**:
  - Polls every 15 seconds and animates rank changes.
  - Admins can freeze it or hide it.
- **Admin panel**:
  - Dashboard.
  - Challenge management: create, edit, hide, delete and attach files.
  - User management: enable or disable accounts, reset passwords, and bulk-create accounts with a CSV credentials export.
  - Submission log and audit log.
- **Accounts**: administrators create all accounts. There is no self-registration. A user given a temporary password must change it at first login.

## Quick start

All commands run from the project root. These are Windows examples; on macOS or Linux, activate the venv with `source .venv/bin/activate`.

```bash
# 1. Virtual environment + dependencies
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 2. Configuration: generates .env with random SECRET_KEY and FLAG_PEPPER
python setup_env.py
#    (or copy .env.example to .env and fill in the secrets yourself)

# 3. Database
flask init-db

# 4. Admin account (prompts for a password if not given; 12+ chars, upper, lower, digit)
flask create-admin --username admin

# 5. Optional: demo data
python seed.py

# 6. Run
flask run
```

Open http://127.0.0.1:5000. `FLASK_APP=wsgi.py` is already set in `.flaskenv`.

### Demo data (`seed.py`)

`seed.py` adds the following, and you can safely run it more than once:

- 5 players.
- 12 challenges covering every category (Web, Crypto, Forensics, Linux, Networking, Misc) and every difficulty (Easy to Insane).
- Some solves and wrong guesses, so the scoreboard and admin logs have content.

It prints all the flags when it finishes.

| Username | Password |
|---|---|
| neo | Matrix-Red-Pill-2026 |
| trinity | Rabbit-Hole-Follow-77 |
| morpheus | Free-Your-Mind-1999 |
| cipher | Steak-Is-Real-404 |
| oracle | Cookies-And-Tea-31 |

Use this for local demos only. Never seed a database that real players use.

## Configuration (`.env`)

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Signs sessions and CSRF tokens (required). |
| `FLAG_PEPPER` | Server-side secret mixed into flag hashes. Changing it invalidates all stored flags. |
| `APP_NAME` | Site name shown in the UI. |
| `SESSION_COOKIE_SECURE` | Set to `1` when served over HTTPS. |
| `DATABASE_URL` | Optional; defaults to `instance/ctf.db` (SQLite). |
| `RATELIMIT_STORAGE_URI` | Optional; use `redis://…` with multiple workers. |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Optional defaults for `flask create-admin`. |

## Project structure

```
app/
  __init__.py        app factory, security headers (CSP), error handlers
  blueprints/        main, auth, challenges, scoreboard, admin
  services/          scoring, user bulk-creation helpers
  models.py          User, Challenge, Solve, Submission, AuditLog, Setting
  forms.py           Flask-WTF forms
  security.py        argon2 password hashing, peppered flag HMAC
  cli.py             flask init-db / create-admin
  templates/         Jinja templates (auth/, challenges/, admin/, errors/)
  static/css/        tokens, base, components, pages, admin
  static/js/         boot, main, reveal, counters, challenges, scoreboard
seed.py              demo data
setup_env.py         generates .env
tests/               pytest suite
```

## Security notes

- **Strict Content-Security-Policy** (`script-src 'self'; style-src 'self'`): there is no inline JavaScript or CSS. Pages pass data to scripts through `data-*` attributes.
- **CSRF protection** on every form and AJAX POST. The token is in `<meta name="csrf-token">` and is sent as the `X-CSRFToken` header.
- **Passwords** are hashed with argon2id.
- **Flags** are stored only as a salted, peppered HMAC and compared in constant time.
- **Rate limits** apply to login, per IP and per username, and to flag submission at 10 per minute.
- **Session tokens** rotate when a password is reset or an account is disabled, which logs that user out everywhere.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Production

Serve `wsgi:app` with a WSGI server, for example `waitress-serve --port 8000 wsgi:app` or gunicorn. Put it behind HTTPS and set `SESSION_COOKIE_SECURE=1`. Use Redis for `RATELIMIT_STORAGE_URI` when you run more than one worker.

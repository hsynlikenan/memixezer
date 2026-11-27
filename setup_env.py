"""Create .env from .env.example with freshly generated secrets.

Usage: python setup_env.py
Refuses to overwrite an existing .env.
"""
import secrets
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
target = root / ".env"
template = root / ".env.example"

if target.exists():
    sys.exit(".env already exists - not overwriting it.")

lines = []
for line in template.read_text(encoding="utf-8").splitlines():
    if line.startswith("SECRET_KEY="):
        line = f"SECRET_KEY={secrets.token_hex(32)}"
    elif line.startswith("FLAG_PEPPER="):
        line = f"FLAG_PEPPER={secrets.token_hex(32)}"
    lines.append(line)

target.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("Created .env with new SECRET_KEY and FLAG_PEPPER.")

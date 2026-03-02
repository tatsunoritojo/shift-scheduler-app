"""Run database migrations during Vercel build.

Called by vercel.json buildCommand:
  pip install -r requirements.txt && python scripts/migrate.py

Requires DATABASE_URL and SECRET_KEY environment variables.
"""

import os
import sys
from pathlib import Path

# Ensure project root is on Python path (scripts/ is one level below root)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("SKIP: DATABASE_URL not set - skipping migration")
        return

    # Prefer unpooled URL for DDL operations (pgbouncer can interfere with migrations)
    unpooled = os.environ.get("DATABASE_URL_UNPOOLED")
    if unpooled:
        os.environ["DATABASE_URL"] = unpooled
        print("Using DATABASE_URL_UNPOOLED for migration (bypasses pgbouncer)")

    os.environ.setdefault("FLASK_ENV", "production")

    from app import create_app
    from flask_migrate import upgrade

    app = create_app()
    with app.app_context():
        upgrade()
        print("Migrations complete.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Migration failed: {e}", file=sys.stderr)
        sys.exit(1)

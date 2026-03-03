import logging
import os

os.environ.setdefault('FLASK_ENV', 'production')

from app import create_app

app = create_app()

# Run pending migrations on cold start (no-op if already up to date)
try:
    from flask_migrate import upgrade
    with app.app_context():
        upgrade()
except Exception as e:
    logging.getLogger(__name__).warning("Auto-migration skipped: %s", e)

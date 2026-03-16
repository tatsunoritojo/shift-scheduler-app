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
        logging.getLogger(__name__).info("Auto-migration completed successfully")
except Exception as e:
    logging.getLogger(__name__).error("Auto-migration failed: %s", e, exc_info=True)

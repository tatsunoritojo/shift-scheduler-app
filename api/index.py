import logging
import os

os.environ.setdefault('FLASK_ENV', 'production')

from app import create_app

app = create_app()

logger = logging.getLogger(__name__)


def _run_auto_migration():
    """Run pending Alembic migrations on cold start.

    Why this is wrapped with explicit URL handling:
    Vercel's standard Neon integration sets DATABASE_URL to the **pooled**
    endpoint (host contains '-pooler'). Pooled connections (PgBouncer
    transaction-mode pooling) reject DDL inside transactions with
    "psycopg2.errors.ReadOnlySqlTransaction: cannot execute ALTER TABLE in
    a read-only transaction". This silently broke production once when an
    ADD COLUMN migration was deployed but never applied; queries against
    the new column 500'd until the deploy was reverted.

    Fix: use DATABASE_URL_UNPOOLED (also provided by the integration) for
    DDL only, via ALEMBIC_OVERRIDE_DB_URL which migrations/env.py honors.
    Runtime queries continue to use the pooled URL via the app's engine.
    """
    unpooled = os.environ.get('DATABASE_URL_UNPOOLED')
    pooled = os.environ.get('DATABASE_URL')
    migration_url = unpooled or pooled

    if not migration_url:
        logger.warning("Auto-migration skipped: no DATABASE_URL or DATABASE_URL_UNPOOLED set")
        return

    if migration_url == pooled and '-pooler' in migration_url:
        logger.warning(
            "Auto-migration is using a POOLED endpoint. DDL may be rejected. "
            "Set DATABASE_URL_UNPOOLED to a direct (non-pooler) URL to fix."
        )

    # Tell migrations/env.py to use this URL instead of the app's engine.
    os.environ['ALEMBIC_OVERRIDE_DB_URL'] = migration_url
    try:
        from flask_migrate import upgrade
        with app.app_context():
            upgrade()
        logger.info(
            "Auto-migration completed (endpoint: %s)",
            'unpooled' if migration_url == unpooled else 'pooled-fallback',
        )
    finally:
        os.environ.pop('ALEMBIC_OVERRIDE_DB_URL', None)


try:
    _run_auto_migration()
except Exception as e:
    # Log loudly so the failure is visible (used to be swallowed silently).
    # Keep the app starting so users see endpoint errors instead of full
    # outage; manual intervention is still required to fix the schema.
    logger.error("Auto-migration FAILED: %s", e, exc_info=True)

import logging
import os
import traceback

os.environ.setdefault('FLASK_ENV', 'production')

from app import create_app

app = create_app()

# Run pending migrations on cold start (no-op if already up to date)
_migration_status = None
try:
    from flask_migrate import upgrade
    with app.app_context():
        upgrade()
        _migration_status = "ok"
except Exception as e:
    _migration_status = traceback.format_exc()
    logging.getLogger(__name__).error("Auto-migration failed: %s", e, exc_info=True)


@app.route('/api/debug/migration-status')
def _debug_migration_status():
    """Temporary diagnostic endpoint — remove after confirming migrations work."""
    from flask import jsonify, session
    from app.extensions import db

    result = {'migration_result': _migration_status}

    try:
        row = db.session.execute(db.text(
            "SELECT version_num FROM alembic_version"
        )).fetchone()
        result['alembic_version'] = row[0] if row else None
    except Exception as e:
        result['alembic_version_error'] = str(e)

    try:
        cols = db.session.execute(db.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'shift_schedule_entries' ORDER BY ordinal_position"
        )).fetchall()
        result['shift_schedule_entries_columns'] = [c[0] for c in cols]
    except Exception as e:
        result['columns_error'] = str(e)

    return jsonify(result)

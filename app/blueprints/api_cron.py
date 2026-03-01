"""Cron endpoint — processes async task queue.

Protected by a shared secret (CRON_SECRET env var) to prevent
unauthorized invocation.  Vercel Cron or an external cron service
hits this endpoint periodically.
"""

import os
import logging

from flask import Blueprint, jsonify, request

api_cron_bp = Blueprint('api_cron', __name__)
logger = logging.getLogger(__name__)


def _verify_cron_secret():
    """Check Authorization header against CRON_SECRET."""
    secret = os.environ.get('CRON_SECRET')
    if not secret:
        # If no secret configured, allow only in debug mode
        from flask import current_app
        return current_app.debug

    auth = request.headers.get('Authorization', '')
    return auth == f'Bearer {secret}'


@api_cron_bp.route('/api/cron/process-tasks', methods=['POST'])
def process_tasks():
    """Process pending async tasks.  Protected by CRON_SECRET."""
    if not _verify_cron_secret():
        return jsonify({'error': 'Unauthorized'}), 401

    from app.services.task_runner import process_pending_tasks
    stats = process_pending_tasks(batch_size=20)

    logger.info("Cron run: %s", stats)
    return jsonify(stats), 200

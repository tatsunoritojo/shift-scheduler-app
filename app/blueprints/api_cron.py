"""Cron endpoint — processes async task queue.

Protected by a shared secret (CRON_SECRET env var) to prevent
unauthorized invocation.  Vercel Cron or an external cron service
hits this endpoint periodically.
"""

import hmac
import os
import logging

from flask import Blueprint, jsonify, request
from app.utils.errors import error_response

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
    expected = f'Bearer {secret}'
    return hmac.compare_digest(auth, expected)


@api_cron_bp.route('/api/cron/process-tasks', methods=['POST'])
def process_tasks():
    """Process pending async tasks.  Protected by CRON_SECRET."""
    if not _verify_cron_secret():
        return error_response('Unauthorized', 401, code="AUTH_REQUIRED")

    from app.services.task_runner import process_pending_tasks
    stats = process_pending_tasks(batch_size=20)

    # Process reminders (integrated into same cron for Vercel Hobby 1/day limit)
    reminder_stats = {}
    try:
        from app.services.reminder_service import (
            check_and_send_submission_reminders,
            check_and_send_preshift_reminders,
        )
        reminder_stats['submission'] = check_and_send_submission_reminders()
        reminder_stats['preshift'] = check_and_send_preshift_reminders()
    except Exception as e:
        logger.error("Reminder processing failed: %s", e)
        reminder_stats['error'] = str(e)

    stats['reminders'] = reminder_stats
    logger.info("Cron run: %s", stats)
    return jsonify(stats), 200

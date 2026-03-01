from flask import Blueprint, request, jsonify, session, current_app
from datetime import datetime

from app.middleware.auth_middleware import require_auth, get_current_user
from app.services.auth_service import get_credentials_for_user
from app.services.calendar_service import fetch_events
from googleapiclient.errors import HttpError

api_calendar_bp = Blueprint('api_calendar', __name__, url_prefix='/api/calendar')


@api_calendar_bp.route('/events')
@require_auth
def get_calendar_events():
    user = get_current_user()

    try:
        credentials = get_credentials_for_user(user)
    except RuntimeError as e:
        current_app.logger.error(f"Credential error for user {user.id}: {e}")
        return jsonify({"error": "認証情報の取得に失敗しました。再ログインしてください。"}), 500

    if not credentials:
        return jsonify({"error": "Refresh token not found for user"}), 404

    start_date_str = request.args.get('startDate')
    end_date_str = request.args.get('endDate')
    calendar_id = request.args.get('calendarId', 'primary')

    if not start_date_str or not end_date_str:
        return jsonify({"error": "startDate and endDate are required"}), 400

    try:
        datetime.fromisoformat(start_date_str)
        datetime.fromisoformat(end_date_str)
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS"}), 400

    try:
        events = fetch_events(credentials, start_date_str, end_date_str, calendar_id)
        return jsonify(events)
    except HttpError as error:
        current_app.logger.error(f"Google Calendar API error: {error.content.decode()}")
        return jsonify({"error": "カレンダーAPIでエラーが発生しました。"}), error.resp.status
    except Exception as e:
        current_app.logger.error(f"Calendar event fetch error: {e}")
        return jsonify({"error": "カレンダーイベントの取得に失敗しました。"}), 500

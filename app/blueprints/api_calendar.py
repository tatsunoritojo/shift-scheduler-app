from flask import Blueprint, request, jsonify, session, current_app
from datetime import datetime

from app.middleware.auth_middleware import require_auth, get_current_user
from app.utils.errors import error_response
from app.services.auth_service import get_credentials_for_user, CredentialsExpiredError
from app.services.calendar_service import fetch_events
from googleapiclient.errors import HttpError

api_calendar_bp = Blueprint('api_calendar', __name__, url_prefix='/api/calendar')


@api_calendar_bp.route('/events')
@require_auth
def get_calendar_events():
    user = get_current_user()

    try:
        credentials = get_credentials_for_user(user)
    except CredentialsExpiredError as e:
        return error_response(str(e), 401, code="CREDENTIALS_EXPIRED")
    except RuntimeError as e:
        current_app.logger.error(f"Credential error for user {user.id}: {e}")
        return error_response("認証情報の取得に失敗しました。再ログインしてください。", 500, code="INTERNAL_ERROR")

    if not credentials:
        return error_response("Refresh token not found for user", 404, code="NOT_FOUND")

    start_date_str = request.args.get('startDate')
    end_date_str = request.args.get('endDate')
    calendar_id = request.args.get('calendarId', 'primary')

    if not start_date_str or not end_date_str:
        return error_response("startDate and endDate are required", 400, code="VALIDATION_ERROR")

    try:
        datetime.fromisoformat(start_date_str)
        datetime.fromisoformat(end_date_str)
    except ValueError:
        return error_response("Invalid date format. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS", 400, code="VALIDATION_ERROR")

    try:
        events = fetch_events(credentials, start_date_str, end_date_str, calendar_id)
        return jsonify(events)
    except HttpError as error:
        current_app.logger.error(f"Google Calendar API error: {error.content.decode()}")
        return error_response("カレンダーAPIでエラーが発生しました。", error.resp.status, code="INTERNAL_ERROR")
    except Exception as e:
        current_app.logger.error(f"Calendar event fetch error: {e}")
        return error_response("カレンダーイベントの取得に失敗しました。", 500, code="INTERNAL_ERROR")

from flask import Flask, redirect, request, url_for, session, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
from pathlib import Path

# 本番環境では OAUTHLIB_INSECURE_TRANSPORT を設定しない
# os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import json
import requests

# Google API imports
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

app = Flask(__name__)
CORS(app)

# 本番環境用のセッションキー設定
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

# セッション設定（本番環境用）
app.config['SESSION_COOKIE_SECURE'] = True  # HTTPS必須
app.config['SESSION_COOKIE_HTTPONLY'] = True  # XSS対策
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # CSRF対策
# セッションのタイムアウト設定
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)

# データベース設定（本番環境用）
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://')
app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///tokens.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# 環境変数からGoogle APIの認証情報を取得（本番環境専用）
CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI")

if not CLIENT_ID or not CLIENT_SECRET or not REDIRECT_URI:
    raise ValueError("Google OAuth認証情報が設定されていません。環境変数を確認してください。")

# OAuth 2.0 スコープ
SCOPES = [
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/calendar.events.readonly',
]

# ユーザーのrefresh_tokenを保存するモデル
class UserToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(255), unique=True, nullable=False)
    refresh_token = db.Column(db.String(512), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<UserToken {self.user_id}>'

# データベースの初期化
with app.app_context():
    db.create_all()

@app.route('/')
def index():
    return redirect(url_for('app_page'))

@app.route('/app')
def app_page():
    return app.send_static_file('shift_scheduler_app.html')

# Google認証開始エンドポイント
@app.route('/auth/google/login')
def login():
    client_config = {
        "web": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": [REDIRECT_URI]
        }
    }
    
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )

    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    session['state'] = state
    return redirect(authorization_url)

# Google認証コールバックエンドポイント
@app.route('/auth/google/callback')
def callback():
    state = session.get('state')
    if not state or state != request.args.get('state'):
        return jsonify({"error": "State mismatch"}), 400

    client_config = {
        "web": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": [REDIRECT_URI]
        }
    }
    
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        state=state,
        redirect_uri=REDIRECT_URI
    )

    try:
        flow.fetch_token(authorization_response=request.url)
    except Exception as e:
        return jsonify({"error": f"Failed to fetch token: {str(e)}"}), 500

    credentials = flow.credentials

    # refresh_tokenをデータベースに保存
    if credentials.refresh_token:
        user_id = credentials.id_token.get('sub') if credentials.id_token else 'default_user'
        user_token = UserToken.query.filter_by(user_id=user_id).first()
        if user_token:
            user_token.refresh_token = credentials.refresh_token
        else:
            user_token = UserToken(user_id=user_id, refresh_token=credentials.refresh_token)
        db.session.add(user_token)
        db.session.commit()
        session['user_id'] = user_id
    else:
        user_id = credentials.id_token.get('sub') if credentials.id_token else 'default_user'
        session['user_id'] = user_id

    # access_tokenをセッションに保存
    session['credentials'] = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }

    return redirect(url_for('app_page'))

# Google Calendar APIイベント取得エンドポイント
@app.route('/api/calendar/events')
def get_calendar_events():
    print(f"[DEBUG] API endpoint called: /api/calendar/events")
    print(f"[DEBUG] Session: {dict(session)}")
    
    user_id = session.get('user_id')
    print(f"[DEBUG] User ID: {user_id}")
    
    if not user_id:
        print("[DEBUG] User not authenticated - returning 401")
        return jsonify({"error": "User not authenticated"}), 401

    user_token = UserToken.query.filter_by(user_id=user_id).first()
    if not user_token:
        return jsonify({"error": "Refresh token not found for user"}), 404

    # 保存されたrefresh_tokenからCredentialsオブジェクトを再構築
    creds_data = session.get('credentials')
    if not creds_data:
        creds_data = {
            'token': None,
            'refresh_token': user_token.refresh_token,
            'token_uri': 'https://oauth2.googleapis.com/token',
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'scopes': SCOPES
        }
    else:
        creds_data['refresh_token'] = user_token.refresh_token
    
    credentials = Credentials(**creds_data)

    # access_tokenが期限切れの場合、refresh_tokenで更新
    if not credentials.valid:
        try:
            from google.auth.transport.requests import Request
            credentials.refresh(Request())
            session['credentials'] = {
                'token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri,
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scopes': credentials.scopes
            }
        except Exception as e:
            return jsonify({"error": f"Failed to refresh access token: {str(e)}"}), 500

    try:
        service = build('calendar', 'v3', credentials=credentials)

        # クエリパラメータから期間とカレンダーIDを取得
        start_date_str = request.args.get('startDate')
        end_date_str = request.args.get('endDate')
        calendar_id = request.args.get('calendarId', 'primary')

        if not start_date_str or not end_date_str:
            return jsonify({"error": "startDate and endDate are required"}), 400

        # 日付文字列をRFC3339形式に変換
        try:
            start_time = datetime.fromisoformat(start_date_str).isoformat() + 'Z'
            end_time = datetime.fromisoformat(end_date_str).isoformat() + 'Z'
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS"}), 400

        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=start_time,
            timeMax=end_time,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])

        # 必要な情報のみを抽出して返す
        event_list = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            end = event['end'].get('dateTime', event['end'].get('date'))
            event_list.append({
                'id': event['id'],
                'summary': event.get('summary', 'No Title'),
                'start': start,
                'end': end,
                'location': event.get('location'),
                'description': event.get('description')
            })
        return jsonify(event_list)

    except HttpError as error:
        return jsonify({"error": f"Google Calendar API error: {error.content.decode()}"}), error.resp.status
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

# デバッグ用エンドポイント
@app.route('/api/debug/routes')
def debug_routes():
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,
            'methods': list(rule.methods),
            'rule': str(rule)
        })
    return jsonify(routes)

# セッション確認エンドポイント
@app.route('/api/debug/session')
def debug_session():
    return jsonify({
        'user_id': session.get('user_id'),
        'has_credentials': 'credentials' in session,
        'session_keys': list(session.keys())
    })

# カレンダー認証状態確認エンドポイント
@app.route('/api/debug/auth-check')
def auth_check():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({
            'authenticated': False,
            'error': 'No user_id in session',
            'session_keys': list(session.keys())
        })
    
    user_token = UserToken.query.filter_by(user_id=user_id).first()
    return jsonify({
        'authenticated': bool(user_token),
        'user_id': user_id,
        'has_refresh_token': bool(user_token.refresh_token if user_token else False),
        'token_created': user_token.created_at.isoformat() if user_token else None
    })

# ヘルスチェックエンドポイント
@app.route('/health')
def health():
    return jsonify({"status": "healthy", "version": "1.0.0"})

if __name__ == '__main__':
    # 本番環境ではGunicornが使用されるため、この部分は開発時のみ実行される
    # 開発時の起動: python app_production.py
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
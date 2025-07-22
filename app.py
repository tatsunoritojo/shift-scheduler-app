from flask import Flask, redirect, request, url_for, session, jsonify
from dotenv import load_dotenv
import os
from pathlib import Path

# .envファイルの絶対パスを指定して読み込み
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

# 開発環境でHTTPを許可（本番環境では削除すること）
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

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
app.secret_key = os.urandom(24) # セッション管理のためのシークレットキー

# データベース設定
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tokens.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# 環境変数からGoogle APIの認証情報を取得
# 本番環境では、これらの情報は安全な方法で管理する必要があります
CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:5000/auth/google/callback")

# 本番環境では環境変数が必須
if not CLIENT_ID or not CLIENT_SECRET:
    raise ValueError("Google OAuth認証情報が設定されていません。環境変数を確認してください。")

# OAuth 2.0 スコープ
SCOPES = [
    'https://www.googleapis.com/auth/calendar.events.readonly',
    # 将来的なシフト書き込みのために 'https://www.googleapis.com/auth/calendar.events' を追加する可能性あり
]

# ユーザーのrefresh_tokenを保存するモデル
class UserToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(255), unique=True, nullable=False) # ユーザーを識別するID (例: Google ID)
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
    return "シフト計算アプリのバックエンドです。/auth/google/login から認証を開始してください。"

@app.route('/app')
def app_page():
    return app.send_static_file('shift_scheduler_app.html')

# デバッグ用エンドポイント
@app.route('/debug/config')
def debug_config():
    return jsonify({
        'env_file_path': str(env_path),
        'env_file_exists': env_path.exists(),
        'CLIENT_ID_raw': CLIENT_ID,
        'CLIENT_SECRET_raw': CLIENT_SECRET[:10] + '...' if CLIENT_SECRET else None,
        'CLIENT_ID_exists': bool(CLIENT_ID and CLIENT_ID != 'your_google_client_id_here'),
        'CLIENT_SECRET_exists': bool(CLIENT_SECRET and CLIENT_SECRET != 'your_google_client_secret_here'),
        'REDIRECT_URI': REDIRECT_URI,
        'all_env_vars': {k: v for k, v in os.environ.items() if 'GOOGLE' in k}
    })

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
        include_granted_scopes='true'
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
        # ここでは仮にuser_idをcredentials.id_token['sub']とする
        # 実際には、アプリケーションのユーザー管理システムと連携させる
        user_id = credentials.id_token.get('sub') if credentials.id_token else 'default_user'
        print(f"Saving user_id: {user_id}")  # デバッグ用
        user_token = UserToken.query.filter_by(user_id=user_id).first()
        if user_token:
            user_token.refresh_token = credentials.refresh_token
        else:
            user_token = UserToken(user_id=user_id, refresh_token=credentials.refresh_token)
        db.session.add(user_token)
        db.session.commit()
        session['user_id'] = user_id # セッションにuser_idを保存
        print(f"Session after setting user_id: {dict(session)}")  # デバッグ用
    else:
        # refresh_tokenがない場合でも、既存のトークンがあれば使用する
        user_id = credentials.id_token.get('sub') if credentials.id_token else 'default_user'
        print(f"No refresh_token, but setting user_id: {user_id}")  # デバッグ用
        session['user_id'] = user_id

    # access_tokenをセッションに保存 (短期間有効なので、refresh_tokenで更新する)
    session['credentials'] = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }

    # 認証後、フロントエンドアプリページにリダイレクト
    return redirect(url_for('app_page'))

# Google Calendar APIイベント取得エンドポイント
@app.route('/api/calendar/events')
def get_calendar_events():
    print(f"Session contents: {dict(session)}")  # デバッグ用
    user_id = session.get('user_id')
    print(f"User ID from session: {user_id}")  # デバッグ用
    
    if not user_id:
        print("No user_id in session")  # デバッグ用
        return jsonify({"error": "User not authenticated", "session_keys": list(session.keys())}), 401

    user_token = UserToken.query.filter_by(user_id=user_id).first()
    if not user_token:
        print(f"No refresh token found for user: {user_id}")  # デバッグ用
        return jsonify({"error": "Refresh token not found for user"}), 404

    # 保存されたrefresh_tokenからCredentialsオブジェクトを再構築
    creds_data = session.get('credentials')
    if not creds_data:
        print("No credentials in session, creating new from refresh_token")  # デバッグ用
        # セッションにcredentialsがない場合、refresh_tokenから新たに作成
        creds_data = {
            'token': None,  # 初期状態では無効
            'refresh_token': user_token.refresh_token,
            'token_uri': 'https://oauth2.googleapis.com/token',
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'scopes': SCOPES
        }
    else:
        creds_data['refresh_token'] = user_token.refresh_token # DBから取得したrefresh_tokenを使用
    
    credentials = Credentials(**creds_data)

    # access_tokenが期限切れの場合、refresh_tokenで更新
    if not credentials.valid:
        try:
            from google.auth.transport.requests import Request
            credentials.refresh(Request())
            # 更新されたaccess_tokenをセッションに保存
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
        calendar_id = request.args.get('calendarId', 'primary') # デフォルトはprimary

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

if __name__ == '__main__':
    # 開発サーバーの起動
    # 本番環境ではGunicornなどのWSGIサーバーを使用します
    app.run(debug=True)

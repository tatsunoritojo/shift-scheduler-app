from flask import Flask, redirect, request, url_for, session, jsonify
from dotenv import load_dotenv
import os
import logging
from pathlib import Path

# .envファイルの絶対パスを指定して読み込み
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime, timedelta
import json
import requests

# Google API imports
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Vercelリバースプロキシ対応（OAuthコールバックでHTTPSが正しく認識されるようにする）
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# 本番環境用のセッションキー設定
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

# セッション設定
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', '1') == '1'
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

# 環境変数からGoogle APIの認証情報を取得
# 本番環境では、これらの情報は安全な方法で管理する必要があります
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
    return redirect(url_for('app_page'))

@app.route('/app')
def app_page():
    return app.send_static_file('shift_scheduler_app.html')

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "version": "1.0.0"})

# デバッグエンドポイント（環境変数 ENABLE_DEBUG=1 で有効化）
if os.environ.get('ENABLE_DEBUG') == '1':
    @app.route('/debug/config')
    def debug_config():
        return jsonify({
            'env_file_path': str(env_path),
            'env_file_exists': env_path.exists(),
            'CLIENT_ID_set': bool(CLIENT_ID),
            'CLIENT_ID_preview': CLIENT_ID[:20] + '...' if CLIENT_ID else None,
            'CLIENT_SECRET_set': bool(CLIENT_SECRET),
            'REDIRECT_URI': REDIRECT_URI,
            'SCOPES': SCOPES,
            'app_url': request.url_root
        })

    @app.route('/api/debug/session')
    def debug_session():
        return jsonify({
            'user_id': session.get('user_id'),
            'has_credentials': 'credentials' in session,
            'session_keys': list(session.keys())
        })

# Google認証開始エンドポイント
@app.route('/auth/google/login')
def login():
    logger.info("[AUTH] Starting Google OAuth flow")
    logger.info(f"[AUTH] CLIENT_ID: {CLIENT_ID[:20]}...")
    logger.info(f"[AUTH] REDIRECT_URI: {REDIRECT_URI}")
    
    try:
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
            prompt='consent'  # 強制的に同意画面を表示
        )
        
        logger.info(f"[AUTH] Generated authorization URL: {authorization_url[:80]}...")
        
        session['state'] = state
        return redirect(authorization_url)
        
    except Exception as e:
        logger.error(f"[AUTH] Failed to create authorization URL: {e}")
        return jsonify({"error": f"Failed to start OAuth flow: {str(e)}"}), 500

# Google認証コールバックエンドポイント
@app.route('/auth/google/callback')
def callback():
    logger.info("[CALLBACK] OAuth callback received")
    
    state = session.get('state')
    request_state = request.args.get('state')
    
    if not state:
        logger.error("[CALLBACK] No state in session")
        return jsonify({"error": "No state in session"}), 400
        
    if state != request_state:
        logger.error(f"[CALLBACK] State mismatch: session={state}, request={request_state}")
        return jsonify({"error": "State mismatch"}), 400
        
    logger.info("[CALLBACK] State validation passed")

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
        logger.info("[CALLBACK] Token fetched successfully")
    except Exception as e:
        logger.error(f"[CALLBACK] Failed to fetch token: {e}")
        return jsonify({"error": f"Failed to fetch token: {str(e)}"}), 500

    credentials = flow.credentials
    logger.info("[CALLBACK] Credentials obtained")

    # Google User IDを取得（より確実な方法）
    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests
        
        # IDトークンからユーザー情報を取得
        if credentials.id_token:
            decoded_token = id_token.verify_oauth2_token(
                credentials.id_token, google_requests.Request(), CLIENT_ID
            )
            user_id = decoded_token.get('sub')
            user_email = decoded_token.get('email')
            logger.info(f"[CALLBACK] User authenticated: {user_email}")
        else:
            # フォールバック: Google+ APIでユーザー情報取得
            from googleapiclient.discovery import build
            service = build('oauth2', 'v2', credentials=credentials)
            user_info = service.userinfo().get().execute()
            user_id = user_info.get('id')
            user_email = user_info.get('email')
            logger.info(f"[CALLBACK] User authenticated via userinfo: {user_email}")
            
    except Exception as e:
        logger.error(f"[CALLBACK] Failed to get user info: {e}")
        user_id = 'default_user'

    # refresh_tokenをデータベースに保存
    if credentials.refresh_token:
        logger.info(f"[CALLBACK] Saving refresh token for user: {user_id}")
        user_token = UserToken.query.filter_by(user_id=user_id).first()
        if user_token:
            user_token.refresh_token = credentials.refresh_token
            user_token.updated_at = datetime.utcnow()
        else:
            user_token = UserToken(user_id=user_id, refresh_token=credentials.refresh_token)
        db.session.add(user_token)
        db.session.commit()
        session['user_id'] = user_id
    else:
        logger.warning(f"[CALLBACK] No refresh token, setting user_id: {user_id}")
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
    logger.info("[API] /api/calendar/events called")

    user_id = session.get('user_id')

    if not user_id:
        logger.warning("[API] User not authenticated")
        return jsonify({"error": "User not authenticated"}), 401

    user_token = UserToken.query.filter_by(user_id=user_id).first()
    if not user_token:
        return jsonify({"error": "Refresh token not found for user"}), 404

    # 保存されたrefresh_tokenからCredentialsオブジェクトを再構築
    creds_data = session.get('credentials')
    if not creds_data:
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
    # ローカル開発時の起動: python app.py
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

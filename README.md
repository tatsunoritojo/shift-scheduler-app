# シフリー — シフト管理アプリ

Google Calendarと連携し、シフトの提出・作成・承認をワンストップで管理するWebアプリケーション（PWA対応）。

**🔗 https://shifree.vercel.app**

## 概要

飲食店や塾など小規模店舗のシフト管理を効率化するアプリです。

- **ワーカー**はGoogleカレンダーの予定から空き時間を自動計算し、シフト希望を提出
- **管理者**は提出状況を見ながらシフト表を作成し、オーナーへ承認申請
- **オーナー**は内容を確認してワンクリックで承認・差し戻し
- 確定したシフトはワーカーのGoogleカレンダーに自動登録

## 機能一覧

### ロール別機能

| ロール | 主な機能 |
|---|---|
| **ワーカー** | Googleカレンダー連携による空き時間自動計算、シフト希望提出、手動時間調整 |
| **管理者** | 営業時間管理、シフト期間の作成・公開、提出状況の確認、シフト表作成、承認申請 |
| **オーナー** | シフト表の承認・差し戻し（コメント付き） |

### システム機能

- Google OAuth 2.0 認証
- DB駆動RBAC（OrganizationMember + 招待トークン）
- 営業時間のGoogleカレンダー双方向同期（インポート/エクスポート）
- 確定シフトのGoogleカレンダー自動登録
- 非同期タスクキュー（メール通知・カレンダー同期のバックグラウンド実行）
- 運用ダッシュボード（タスク成功率・承認ワークフロー統計）
- メール通知（承認申請時・承認結果通知、非同期配信対応）
- PWA対応（スマホからホーム画面に追加可能）
- Flask-Migrate によるDBマイグレーション管理
- レート制限・セキュリティヘッダー・CSP対応
- 自動テスト 128件（pytest）

## 技術構成

| カテゴリ | 技術 |
|---|---|
| バックエンド | Python 3.9+ / Flask 3.1 |
| ORM / マイグレーション | Flask-SQLAlchemy / Flask-Migrate (Alembic) |
| DB | SQLite（ローカル）/ PostgreSQL（本番） |
| 認証 | Google OAuth 2.0 |
| 外部API | Google Calendar API v3 |
| テスト | pytest（128件） |
| フロントエンド | HTML5 / CSS3 / JavaScript（ロール別SPA） |
| デプロイ | Vercel（Serverless Python + Cron Jobs） |

## プロジェクト構成

```
shift-scheduler-app/
├── app/
│   ├── __init__.py                 # アプリケーションファクトリ
│   ├── config.py                   # 環境別設定
│   ├── extensions.py               # Flask拡張（DB, Migrate, CORS, Limiter, Session）
│   ├── blueprints/
│   │   ├── auth.py                 # Google OAuth認証 + 招待トークン受入
│   │   ├── api_common.py           # 共通ルート（ルーティング, ヘルスチェック）
│   │   ├── api_admin.py            # 管理者API（メンバー管理・招待含む）
│   │   ├── api_owner.py            # オーナーAPI
│   │   ├── api_worker.py           # ワーカーAPI
│   │   ├── api_calendar.py         # カレンダーAPI
│   │   ├── api_cron.py             # 非同期タスク処理（Cronエンドポイント）
│   │   └── api_dashboard.py        # 運用ダッシュボードAPI
│   ├── models/
│   │   ├── user.py                 # User, UserToken
│   │   ├── organization.py         # Organization
│   │   ├── membership.py           # OrganizationMember, InvitationToken
│   │   ├── opening_hours.py        # OpeningHours, 例外, 同期ログ
│   │   ├── shift.py                # ShiftPeriod, Submission, Schedule, Entry
│   │   ├── approval.py             # ApprovalHistory
│   │   └── async_task.py           # AsyncTask（非同期ジョブキュー）
│   ├── services/
│   │   ├── auth_service.py         # OAuth・ユーザー管理
│   │   ├── calendar_service.py     # Googleカレンダー操作
│   │   ├── shift_service.py        # シフト提出・スケジュール作成
│   │   ├── approval_service.py     # 承認ワークフロー
│   │   ├── notification_service.py # メール通知（非同期キュー対応）
│   │   ├── task_runner.py          # タスクランナー（キュー処理・リトライ）
│   │   └── opening_hours_sync_service.py  # 営業時間カレンダー同期
│   ├── middleware/
│   │   └── auth_middleware.py      # @require_auth, @require_role デコレータ
│   └── utils/
│       ├── errors.py               # APIError, error_response（標準化エラー）
│       ├── time_utils.py           # 時刻変換ヘルパー
│       └── validators.py           # バリデーション
├── static/
│   ├── pages/                      # ロール別HTMLページ
│   ├── js/                         # ロール別JS + 共通モジュール
│   ├── css/                        # ロール別CSS
│   ├── icons/                      # PWAアイコン
│   ├── manifest.json               # PWAマニフェスト
│   └── sw.js                       # Service Worker
├── api/
│   └── index.py                    # Vercelエントリポイント
├── wsgi.py                         # ローカル開発用エントリポイント
├── migrations/                     # Alembicマイグレーション
├── tests/                          # pytest テストスイート（128件）
├── vercel.json                     # Vercelルーティング + Cron設定
├── pytest.ini                      # pytest設定
├── requirements.txt
└── app_v1_legacy.py                # v1レガシー版（保存用）
```

## ローカル開発

### 前提条件

- Python 3.9以上
- Google Cloud Projectで Calendar API を有効化済み

### セットアップ

```bash
pip install -r requirements.txt
```

`.env` を作成し、以下を設定:

```env
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REDIRECT_URI=http://localhost:5000/auth/google/callback
SECRET_KEY=your_secret_key
ADMIN_EMAIL=admin@example.com
OWNER_EMAIL=owner@example.com
SESSION_COOKIE_SECURE=0
```

> Google Cloud Console > APIとサービス > 認証情報 で OAuth 2.0 クライアントIDを作成し、
> リダイレクトURIに `http://localhost:5000/auth/google/callback` を追加してください。

### 起動

```bash
python wsgi.py
```

`http://localhost:5000` にアクセス。ログイン後、メールアドレスに応じたロール画面にリダイレクトされます。

## デプロイ（Vercel）

### 1. プロジェクトをインポート

```bash
vercel
```

### 2. 環境変数を設定

Vercelダッシュボード > Settings > Environment Variables:

| 変数名 | 説明 |
|---|---|
| `GOOGLE_CLIENT_ID` | OAuth クライアントID |
| `GOOGLE_CLIENT_SECRET` | OAuth クライアントシークレット |
| `GOOGLE_REDIRECT_URI` | `https://your-domain.vercel.app/auth/google/callback` |
| `SECRET_KEY` | ランダムな秘密鍵 |
| `DATABASE_URL` | PostgreSQL接続文字列 |
| `ADMIN_EMAIL` | 管理者メールアドレス（カンマ区切りで複数可） |
| `OWNER_EMAIL` | オーナーメールアドレス（カンマ区切りで複数可） |
| `CRON_SECRET` | 非同期タスク処理用Cronエンドポイントの認証トークン |

メール通知を有効にする場合:

| 変数名 | 説明 |
|---|---|
| `SMTP_HOST` | SMTPサーバーホスト |
| `SMTP_PORT` | ポート（デフォルト: 587） |
| `SMTP_USER` | SMTPユーザー名 |
| `SMTP_PASS` | SMTPパスワード |

### 3. デプロイ

```bash
vercel --prod
```

> Google Cloud ConsoleのリダイレクトURIにVercelのURLを追加するのを忘れずに。

## シフト管理のワークフロー

```
管理者: シフト期間を作成 → 公開
         ↓
ワーカー: 空き時間を確認 → シフト希望を提出
         ↓
管理者: 提出状況を確認 → シフト表を作成 → オーナーへ承認申請
         ↓
オーナー: 確認 → 承認 or 差し戻し
         ↓
管理者: 確定 → ワーカーのGoogleカレンダーに自動登録
```

## ライセンス

MIT

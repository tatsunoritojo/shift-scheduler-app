# シフリー (Shifree)

Googleカレンダーと連携し、シフトの提出・作成・承認をワンストップで管理するWebアプリケーション。

<p align="center">
  <a href="https://shifree.vercel.app/lp"><strong>🌐 ランディングページ</strong></a>
  &nbsp;|&nbsp;
  <a href="https://shifree.vercel.app"><strong>🚀 アプリを使う</strong></a>
</p>

## なぜシフリーか

飲食店や塾など小規模チームのシフト管理は、LINEグループでの希望収集 → Excelで転記 → 口頭で共有、という手作業の連鎖になりがちです。シフリーはこのフローを **Googleカレンダー1つで完結** させます。

```
管理者: シフト期間を作成・公開
  ↓
ワーカー: Googleカレンダーの予定から空き時間を自動計算 → シフト希望を提出
  ↓
管理者: 提出状況を確認 → シフト表を作成 → オーナーへ承認申請
  ↓
オーナー: 確認 → 承認 or 差し戻し
  ↓
確定シフトがワーカーのGoogleカレンダーに自動登録
```

## 機能一覧

### ロール別

| ロール | 主な機能 |
|---|---|
| **ワーカー** | Googleカレンダー連携による空き時間自動計算、シフト希望提出、手動時間調整 |
| **管理者** | 営業時間管理、シフト期間の作成・公開、提出状況の確認、シフト表作成、承認申請、メンバー招待・管理、リマインダー設定、欠員補充 |
| **オーナー** | シフト表の承認・差し戻し（コメント付き） |

### システム

- **認証**: Google OAuth 2.0 + 招待コード/トークンによるオンボーディング
- **RBAC**: DB駆動ロール管理（OrganizationMember + ミドルウェア強制）
- **カレンダー同期**: 営業時間の双方向同期 + 確定シフトの自動登録
- **非同期タスク**: メール通知・カレンダー同期のバックグラウンド実行（指数バックオフリトライ）
- **リマインダー**: 提出期限・シフト前通知（重複排除・Cron自動実行）
- **欠員補充**: 候補者自動検索（公平性ソート）・トークン応答・変更ログ
- **運用ダッシュボード**: タスク成功率・承認統計・監査ログ
- **通知**: メール通知（承認申請・結果通知・招待・欠員依頼、非同期配信対応）
- **セキュリティ**: レート制限・CSP・CORS本番フェイルクローズ・組織未参加ユーザー遮断
- **PWA対応**: スマホからホーム画面に追加可能
- **自動テスト**: pytest 207件

## 技術構成

| カテゴリ | 技術 |
|---|---|
| バックエンド | Python 3.9+ / Flask 3.1 |
| ORM / マイグレーション | Flask-SQLAlchemy / Flask-Migrate (Alembic) |
| DB | SQLite（ローカル）/ PostgreSQL（本番） |
| 認証 | Google OAuth 2.0 |
| 外部API | Google Calendar API v3 |
| フロントエンド | HTML5 / CSS3 / Vanilla JS（ロール別SPA、ES Modules） |
| テスト | pytest（207件） |
| デプロイ | Vercel（Serverless Python + Cron Jobs） |

## プロジェクト構成

```
shift-scheduler-app/
├── app/
│   ├── __init__.py                 # アプリケーションファクトリ
│   ├── config.py                   # 環境別設定
│   ├── extensions.py               # Flask拡張
│   ├── blueprints/
│   │   ├── auth.py                 # Google OAuth + 招待トークン受入
│   │   ├── api_common.py           # ルーティング, ヘルスチェック, 招待LP
│   │   ├── api_admin.py            # 管理者API（メンバー・招待・欠員・リマインダー）
│   │   ├── api_owner.py            # オーナーAPI（承認・差し戻し）
│   │   ├── api_worker.py           # ワーカーAPI（シフト希望提出）
│   │   ├── api_calendar.py         # カレンダー同期API
│   │   ├── api_cron.py             # Cronエンドポイント（タスク処理・リマインダー）
│   │   └── api_dashboard.py        # 運用ダッシュボードAPI
│   ├── models/
│   │   ├── user.py                 # User, UserToken
│   │   ├── organization.py         # Organization（設定JSON含む）
│   │   ├── membership.py           # OrganizationMember, InvitationToken
│   │   ├── opening_hours.py        # OpeningHours, 例外, 同期ログ
│   │   ├── shift.py                # ShiftPeriod, Submission, Schedule, Entry
│   │   ├── approval.py             # ApprovalHistory
│   │   ├── async_task.py           # AsyncTask（非同期ジョブキュー）
│   │   ├── audit_log.py            # AuditLog（監査ログ）
│   │   ├── reminder.py             # Reminder（通知リマインダー）
│   │   └── vacancy.py              # VacancyRequest, VacancyCandidate, ShiftChangeLog
│   ├── services/
│   │   ├── auth_service.py         # OAuth・ユーザー管理
│   │   ├── calendar_service.py     # Googleカレンダー操作
│   │   ├── shift_service.py        # シフト提出・スケジュール作成
│   │   ├── approval_service.py     # 承認ワークフロー
│   │   ├── notification_service.py # メール通知（非同期キュー対応）
│   │   ├── task_runner.py          # タスクランナー（キュー処理・リトライ）
│   │   ├── opening_hours_sync_service.py  # 営業時間カレンダー同期
│   │   ├── audit_service.py        # 監査ログ記録
│   │   ├── reminder_service.py     # リマインダー管理・自動送信
│   │   └── vacancy_service.py      # 欠員補充（候補検索・応答処理）
│   ├── middleware/
│   │   └── auth_middleware.py      # @require_auth, @require_role
│   └── utils/
│       ├── errors.py               # APIError, error_response
│       ├── time_utils.py           # 時刻変換ヘルパー
│       └── validators.py           # バリデーション
├── static/
│   ├── pages/                      # ロール別HTML + ランディングページ
│   ├── js/                         # ロール別JS + 共通モジュール
│   ├── css/                        # ロール別CSS
│   ├── icons/                      # PWAアイコン
│   ├── manifest.json               # PWAマニフェスト
│   └── sw.js                       # Service Worker
├── api/
│   └── index.py                    # Vercelエントリポイント
├── wsgi.py                         # ローカル開発用エントリポイント
├── migrations/                     # Alembicマイグレーション
├── tests/                          # pytest テストスイート（207件）
└── vercel.json                     # Vercelルーティング + Cron設定
```

## ローカル開発

### 前提条件

- Python 3.9以上
- Google Cloud Projectで Calendar API を有効化済み

### セットアップ

```bash
pip install -r requirements.txt
```

`.env` を作成:

```env
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REDIRECT_URI=http://localhost:5000/auth/google/callback
SECRET_KEY=your_secret_key
ADMIN_EMAIL=admin@example.com
OWNER_EMAIL=owner@example.com
SESSION_COOKIE_SECURE=0
```

> Google Cloud Console > APIとサービス > 認証情報 で OAuth 2.0 クライアントIDを作成し、リダイレクトURIに `http://localhost:5000/auth/google/callback` を追加してください。

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
| `CRON_SECRET` | Cronエンドポイント認証トークン |

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

## URL一覧

| パス | 説明 |
|---|---|
| `/lp` | ランディングページ |
| `/login` | ログイン画面 |
| `/admin` | 管理者画面 |
| `/worker` | ワーカー画面 |
| `/owner` | オーナー画面 |
| `/invite?code=X` | 招待コードによる参加ページ |
| `/no-organization` | 組織未参加ユーザー案内 |
| `/vacancy/respond` | 欠員補充の応答ページ |
| `/health` | ヘルスチェック |

## ライセンス

MIT

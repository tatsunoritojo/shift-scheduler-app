# プロジェクト構造辞書 (CODEBASE_DICTIONARY) - 完全網羅版

本ドキュメントは、`shift-scheduler-app` の全ソースコード、データベーススキーマ、APIエンドポイント、サービス層ロジック、およびフロントエンド資産を網羅した詳細な技術辞書です。本システムは Flask を用いたバックエンドと、Vanilla JS を用いたフロントエンドによって構成され、Vercel (Serverless) 環境での動作を前提として設計されています。

---

## 1. ディレクトリ構造と主要ファイル (Architecture)

*   `wsgi.py` / `api/index.py`: アプリケーションのエントリポイント（ローカル開発用 / Vercel用）。
*   `requirements.txt`: 依存パッケージ（Flask, SQLAlchemy, Google Auth, psycopg2 等）。
*   `vercel.json`: Vercel デプロイ時のルーティングと cron ジョブ設定。
*   `app/`
    *   `models/`: SQLAlchemy を用いたデータベーススキーマ定義。
    *   `services/`: ビジネスロジック。ルーティングから分離され、独立してテスト可能。
    *   `blueprints/`: Flask API のルーティング（エンドポイント定義）。
    *   `utils/`: 共通のバリデーションや暗号化ユーティリティ。
    *   `middleware/`: RBAC（Role-Based Access Control）などの認証・認可処理。
*   `static/`
    *   `pages/`: 各画面の HTML テンプレート（SPAライクに動作）。
    *   `js/`: フロントエンドのロジック。画面ごとのコントローラと共通の `modules/` に分割。
    *   `css/`: Vanilla CSS によるスタイリング。

---

## 2. データベーススキーマ仕様 (Database Models)
`app/models/` 配下の全テーブルと主要カラムの定義。

### 2.1. ユーザー・組織基盤 (`user.py`, `organization.py`, `membership.py`)
*   **User (`users`)**
    *   `id` (PK): 内部ID。
    *   `google_id` (String, Unique): Google OAuthから取得する不変のID。
    *   `email`, `display_name` (String): プロフィール情報。
    *   `role` (String): `worker`, `admin`, `owner` (※非正規化キャッシュ。正は `OrganizationMember`)。
    *   `organization_id` (FK): 現在アクティブな組織ID。
*   **UserToken (`user_tokens`)**
    *   `user_id` (FK, Unique): ユーザーとの1対1リレーション。
    *   `refresh_token` (String): Google Calendar APIアクセス用。`crypto.py` で暗号化されて保存。
*   **Organization (`organizations`)**
    *   `id` (PK), `name` (String): 組織情報。
    *   `admin_email`, `owner_email` (String): 管理用メールアドレス。
    *   `settings_json` (Text): リマインダー設定等（`reminder_days_before_deadline`, `reminder_time_shift` 等）。
    *   `invite_code` (String, Unique), `invite_code_enabled` (Boolean): 共有リンクによる招待コード。
*   **OrganizationMember (`organization_members`)**
    *   `user_id`, `organization_id` (FK, 複合Unique): 所属情報の実体。
    *   `role` (String): 組織内での権限。
*   **InvitationToken (`invitation_tokens`)**
    *   `token` (String, Unique): URLに含まれる招待トークン。
    *   `role`, `email`, `expires_at`: トークンの権限、宛先制限、有効期限。

### 2.2. シフト管理 (`shift.py`, `opening_hours.py`)
*   **ShiftPeriod (`shift_periods`)**
    *   `organization_id` (FK), `name`, `start_date`, `end_date`: 募集期間の定義。
    *   `status` (String): `draft` -> `open` (募集中) -> `closed` (募集終了)。
    *   `submission_deadline` (DateTime): スタッフからの希望提出期限。
*   **ShiftSubmission (`shift_submissions`)**
    *   `shift_period_id`, `user_id` (FK, 複合Unique): スタッフ単位の希望データ。
    *   `status` (String): `submitted`, `revised`。
*   **ShiftSubmissionSlot (`shift_submission_slots`)**
    *   `submission_id` (FK), `slot_date` (Date): 1日ごとの希望。
    *   `is_available` (Boolean): 出勤可否。
    *   `start_time`, `end_time` (String): 意図的な希望時間 ("HH:MM")。
*   **ShiftSchedule (`shift_schedules`)**
    *   `shift_period_id` (FK): 期間に紐づく確定シフトの親。
    *   `status` (String): `draft` -> `pending_approval` -> `approved` -> `confirmed` (カレンダー同期済) または `rejected`。
*   **ShiftScheduleEntry (`shift_schedule_entries`)**
    *   `schedule_id`, `user_id` (FK), `shift_date`, `start_time`, `end_time`: 確定した勤務枠。
    *   `calendar_event_id` (String): Google Calendar側のイベントID。同期状態の管理に使用。
*   **OpeningHours (`opening_hours`)**
    *   `organization_id` (FK), `day_of_week` (Integer): 曜日（0=日, 6=土）ごとの基本営業時間。
*   **OpeningHoursException (`opening_hours_exceptions`)**
    *   `organization_id`, `exception_date` (Date, 複合Unique): 祝日等の例外設定。
    *   `source` (String): `manual` (手動設定) または `calendar` (カレンダー同期)。

### 2.3. 業務拡張（欠員補充・タスク・監査） (`vacancy.py`, `async_task.py`, `audit_log.py`, `approval.py`)
*   **VacancyRequest (`vacancy_requests`)**
    *   `schedule_entry_id` (FK), `status`: 欠員補充のリクエスト。`open` -> `notified` -> `accepted`/`expired`。
*   **VacancyCandidate (`vacancy_candidates`)**
    *   `vacancy_request_id`, `user_id` (FK): 補充候補者。
    *   `response_token` (String, Unique): 候補者専用のワンタイム応答トークン。
*   **ShiftChangeLog (`shift_change_logs`)**
    *   欠員補充完了時等に、誰の枠が誰に変わったかを永続的に記録。
*   **AsyncTask (`async_tasks`)**
    *   `task_type` (String): `send_email`, `sync_calendar_event` 等。
    *   `payload` (JSON): 実行に必要なパラメータ。
    *   `status` (String): `pending`, `running`, `completed`, `failed`, `dead`。
    *   `retry_count`, `next_run_at`: 指数バックオフによるリトライ制御。
*   **AuditLog (`audit_logs`)**
    *   `action`, `resource_type`, `old_values`, `new_values`: セキュリティ上重要な操作の全履歴。
*   **ApprovalHistory (`approval_history`)**
    *   シフト承認フローにおける、提出・承認・却下のコメントと履歴。

---

## 3. バックエンド API エンドポイント (Blueprints)

### 3.1. 認証 (`auth.py`)
*   `GET /auth/google/login`: OAuth開始。セッションに `state` と招待コードを保持。
*   `GET /auth/google/callback`: OAuthコールバック。ユーザー情報の UPSERT と、招待ロジックの評価（自動参加）。
*   `GET /auth/invite/<token>` / `GET /auth/invite/code/<code>`: 招待URL。Cookieにトークンをセットしてログインへリダイレクト。
*   `GET /auth/logout`: セッション破棄。GoogleトークンのRevokeもベストエフォートで実行。
*   `GET /auth/me`: 現在のログインユーザー情報の取得。

### 3.2. 管理者機能 (`api_admin.py`) - `require_role('admin')`
*   **営業時間管理**
    *   `GET/PUT /api/admin/opening-hours`: 基本営業時間の取得・一括更新。
    *   `GET/POST /api/admin/opening-hours/exceptions`: 例外の取得・作成。
    *   `PUT/DELETE /api/admin/opening-hours/exceptions/<id>`: 例外の更新・削除。
    *   `POST /api/admin/opening-hours/sync/export|import`: Googleカレンダーとの「開校時間」の双方向同期。
*   **シフト期間作成**
    *   `GET/POST /api/admin/periods`: 期間の取得・作成。
    *   `PUT /api/admin/periods/<id>`: ステータス（draft/open/closed）や締切の変更。
*   **スケジュール構築**
    *   `GET/POST /api/admin/periods/<id>/schedule`: 管理者によるドラフトシフトの取得・保存。
    *   `POST /api/admin/periods/<id>/schedule/submit`: オーナーへの承認依頼。
    *   `POST /api/admin/periods/<id>/schedule/confirm`: 承認済みシフトの最終確定と、全スタッフのカレンダー同期トリガー。
*   **組織・メンバー管理**
    *   `GET /api/admin/members` / `PUT /api/admin/members/<id>/role` / `DELETE /api/admin/members/<id>`: メンバー権限管理。
    *   `POST /api/admin/invitations` / `DELETE /api/admin/invitations/<id>`: 招待トークン管理。
    *   `GET/POST/PUT /api/admin/invite-code`: URL共有用のコード生成・ON/OFF。
*   **欠員補充**
    *   `GET /api/admin/vacancy/candidates/<entry_id>`: 条件を満たす代替候補者の自動抽出。
    *   `POST /api/admin/vacancy` / `POST /api/admin/vacancy/<id>/notify`: リクエスト作成と候補者への一斉通知送信。
*   **設定・リマインダー**
    *   `GET/PUT /api/admin/reminder-settings`: 組織の通知設定の変更。
    *   `POST /api/admin/reminders/send/<period_id>`: 手動での提出リマインダー一斉送信。

### 3.3. スタッフ機能 (`api_worker.py`) - `require_role('worker')`
*   `GET /api/worker/periods`: 提出可能なシフト期間一覧の取得。
*   `GET/POST /api/worker/periods/<id>/availability`: 自身のシフト希望の取得・提出。
*   `GET /api/worker/calendars` / `GET /api/worker/calendar/events`: 自身のGoogleカレンダー情報取得（シフト提出時の参考用）。

### 3.4. オーナー機能 (`api_owner.py`) - `require_role('owner')`
*   `GET /api/owner/pending-approvals`: 承認待ちスケジュールの一覧。
*   `GET /api/owner/schedules/<id>`: スケジュール詳細（合算時間、履歴含む）の取得。
*   `POST /api/owner/schedules/<id>/approve|reject`: スケジュールの承認または差戻し（コメント可）。

### 3.5. 共通・公開・システム機能 (`api_common.py`, `api_cron.py`, `api_calendar.py`)
*   `GET /` ... `/worker` 等の画面ルーティング（HTMLテンプレートを返す）。
*   `GET /api/invite/info`: 招待コード有効性チェック用公開API。
*   `GET /vacancy/respond`: 欠員補充メールのリンク用公開API（トークンベースで `accept`/`decline` を処理しHTMLを返す）。
*   `POST /api/organizations`: ログイン直後のユーザーが新規組織を作成するためのAPI。
*   `POST /api/cron/process-tasks`: 非同期タスクの消化と自動リマインダー送信（`CRON_SECRET` で保護）。

---

## 4. サービス層関数リファレンス (Service Layer)

### 4.1. シフトコア (`shift_service.py`)
*   `get_opening_hours_for_date(org_id, target_date) -> dict|None`: 例外設定を優先評価した該当日時の営業時間取得。
*   `create_or_update_submission(period_id, user_id, slots_data, notes) -> ShiftSubmission`: 既存スロットを論理削除し、新規希望データを挿入（冪等性）。
*   `save_schedule(period_id, created_by, entries_data, organization_id) -> ShiftSchedule`: スケジュールのバリデーション（在籍、Role等）と保存。
*   `get_worker_hours_summary(schedule_id) -> list`: 確定シフトからスタッフごとの総労働時間・出勤回数を算出。

### 4.2. 承認ワークフロー (`approval_service.py`)
全関数で `ApprovalHistory` と `AuditLog` を作成。失敗時はトランザクションをロールバック。
*   `submit_for_approval(schedule_id, admin_user)`: `draft` -> `pending_approval`。オーナーへ通知。
*   `approve_schedule(schedule_id, owner_user, comment)`: `pending_approval` -> `approved`。管理者に通知。
*   `reject_schedule(schedule_id, owner_user, comment)`: `pending_approval` -> `rejected`。管理者に通知。
*   `confirm_schedule(schedule_id, admin_user)`: `approved` -> `confirmed`。この後カレンダー同期タスクが走る。

### 4.3. 欠員補充 (`vacancy_service.py`)
*   `find_candidates(schedule_entry_id, organization_id)`: 対象日に `is_available=True` だがシフトが入っていないアクティブなスタッフを抽出し、週の労働時間が短い順にソートして返す。
*   `create_vacancy_request(schedule_entry_id, reason, admin_user)`: 空き枠に対するリクエストを作成。
*   `send_vacancy_notifications(vacancy_request_id, candidate_user_ids, base_url)`: 各候補者に専用の `response_token` を発行し、承諾/辞退リンク付きのメールを送信。
*   `respond_to_vacancy(token, action)`:
    *   Race condition 対策: 既に `notified` 以外ならエラー。
    *   `accept` 時: `ShiftScheduleEntry` の `user_id` を書き換え、`ShiftChangeLog` に記録。他候補者を `expired` にし、Googleカレンダーのイベントを再アサインする。

### 4.4. 非同期タスク＆リマインダー (`task_runner.py`, `reminder_service.py`)
*   **Task Runner**:
    *   `register_handler(task_type)`: `@register_handler('send_email')` のようにデコレータで処理ロジックをマッピング。
    *   `process_pending_tasks(batch_size)`: DBから `status='pending'` 且つ `next_run_at <= now` のタスクを取得。失敗時は指数バックオフ（30s, 2m, 8m...）を適用し `retry_count` をインクリメント。
*   **Reminder**:
    *   `check_and_send_submission_reminders()`: 未提出のスタッフに対し、設定された「締切X日前のYY:YY」を過ぎていれば `notify_submission_deadline` をキューイング。重複防止のため `Reminder` テーブルに記録。
    *   `check_and_send_preshift_reminders()`: 同様に、明日のシフト入りのスタッフにリマインド。

### 4.5. 外部連携 (`calendar_service.py`, `opening_hours_sync_service.py`, `notification_service.py`)
*   `calendar_service.py`: `google-api-python-client` ラッパー。`fetch_events`, `create_event`, `update_event`, `delete_event`。常に `Asia/Tokyo` タイムゾーンを使用。
*   `export_opening_hours_to_calendar(org_id, credentials, start_date, end_date)`: `source='calendar'` の例外日をスキップしつつ、DBの開校時間をカレンダーに書き出し。
*   `notification_service.py`: `_enqueue_or_send` パターンを採用。DBやインポートに失敗した場合は同期送信にフォールバックする堅牢設計。

---

## 5. フロントエンド構造 (Static & JS)

### 5.1. 画面テンプレート (`static/pages/*.html`)
HTML内に `<script type="module" src="/static/js/xxx-app.js"></script>` を含み、APIから動的に描画するSPAアーキテクチャ。
*   `landing.html`, `login.html`: ランディングと認証。
*   `admin.html`, `worker.html`, `owner.html`: Role別ダッシュボード。
*   `invite.html`, `no-organization.html`: 参加フロー用の補助画面。

### 5.2. JavaScript モジュール (`static/js/modules/`)
フロントエンドの共通ビジネスロジック群。
*   `api-client.js`: `fetch` ラッパー。401 エラー時に `CREDENTIALS_EXPIRED` を検知し、専用の再認証モーダル (`reauth-overlay`) を DOM にインジェクトする。
*   `calendar-grid.js`: FullCalendarの軽量クローン。
    *   日付グリッドの生成、ヘッダー描画。
    *   イベント（シフトや開校時間）のドラッグ＆ドロップ、クリックイベントのハンドリングをサポート。
*   `shift-calculator.js`: 勤務時間の計算エンジン。
    *   `calculateTotalHours(startTime, endTime)`
    *   休憩時間の控除ルールや、丸め処理（15分単位等）を内包。
*   `event-utils.js`: Google Calendar から取得した生データを、UI表示用の標準フォーマットに正規化。
*   `time-utils.js`: `"HH:MM"` と 分(Integer) の相互変換ユーティリティ。
*   `notification.js`: Toast 形式の非同期通知UI。
*   `ui-dialogs.js`: 各種モーダル、確認ダイアログの生成と破棄。

### 5.3. アプリケーションコントローラ (`static/js/`)
*   `admin-app.js`: 期間の作成、スケジュールのドラッグ配置、承認フローのトリガー、欠員補充パネルの制御を司る巨大なコントローラ。
*   `worker-app.js`: スロットごとのカレンダーイベント表示と、提出フォーム (`is_available` トグル、時間入力) のバインディング。
*   `owner-app.js`: 承認待ちスケジュールの読み込みと、Approve/Reject 実行時の状態管理。

---

## 6. セキュリティ・ミドルウェア実装 (Security)

*   **OAuth保護**: `app/utils/crypto.py`
    *   `encrypt_token`, `decrypt_token`: `SECRET_KEY` + `hashlib.sha256` + `Fernet` による対称暗号化。DBに平文のリフレッシュトークンを置かない。
*   **Role-Based Access Control (RBAC)**: `app/middleware/auth_middleware.py`
    *   `@require_auth`: ログインと `OrganizationMember` のアクティブ検証。
    *   `@require_role(*roles)`: デコレータ引数による厳密な権限チェック（`admin` は `worker` のエンドポイントを叩けないなど）。
*   **Cookie 運用**:
    *   Session Cookie は `HttpOnly`, `SameSite=Lax`, `Secure` (Production時) を強制。
    *   招待コード（`COOKIE_INVITE_TOKEN` 等）は `URLSafeTimedSerializer` で署名され、改ざんを防止。
*   **Rate Limiting**: `Flask-Limiter`
    *   `/auth/google/login` (10/min), `/api/admin/periods` (20/min) など、負荷の高いエンドポイントを制限。

---

## 6. Vercel 連携仕様 (Infrastructure & Deployment)

本プロジェクトは Vercel Serverless Functions 環境に最適化された構成を採用しています。

### 6.1. Serverless Runtime (`api/index.py`)
*   **エントリポイント**: `api/index.py` が Vercel の Python ランタイムによって読み込まれます。
*   **オートマイグレーション**: コールドスタート（関数の初回起動）時に `flask_migrate.upgrade()` を実行し、DB スキーマを最新の状態に自動更新します。
*   **環境変数制御**: `FLASK_ENV` を `production` に固定し、セキュアな設定を強制します。

### 6.2. ルーティング (`vercel.json`)
*   **SPA/Monolith Rewrite**: 全てのリクエストを `api/index` へ転送し、Flask 側の `api_common_bp` がパスに基づいて適切な HTML（`static/pages/`）または JSON を返します。
*   **静的資産**: `/static/*` は Flask の `static_folder` 定義により提供されます。

### 3. 定期実行 (Vercel Cron Jobs)
*   **実行パス**: `/api/cron/process-tasks`
*   **スケジュール**: `0 9 * * *` (毎日午前9時 UTC)
*   **処理内容**:
    1.  `AsyncTask` キュー内の未処理タスク（メール送信、カレンダー同期）のバッチ処理。
    2.  `ShiftPeriod` の締切前リマインダーの自動送信。
    3.  翌日のシフト入りスタッフへの自動通知。
*   **セキュリティ**: Vercel からのリクエストであることを保証するため、`CRON_SECRET` 環境変数を用いた Bearer 認証が必須となります。

### 4. データベース接続
*   **SQLAlchemy 互換性**: Vercel Postgres 等が提供する `postgres://` プレフィックスを、`app/config.py` 内で `postgresql://` に動的に置換して接続します。

---

## 7. 実装・デプロイ環境仕様 (Implementation & Deployment Details)

本プロジェクトを構築・運用・保護するための環境仕様の全貌です。

### 7.1. 稼働に必須な環境変数マニュアル
本システムを本番稼働させるために Vercel 等の環境に設定が必要な変数リストです。

| 変数名 | 必須 | 用途・形式 |
| :--- | :--- | :--- |
| `SECRET_KEY` | **必須** | セッション署名および OAuth トークンの `Fernet` 暗号化に使用する不変の鍵。 |
| `DATABASE_URL` | **必須** | `postgresql://user:pass@host:port/dbname`。Vercel Postgres を推奨。 |
| `GOOGLE_CLIENT_ID` | **必須** | Google Cloud Console で発行。Calendar API の有効化が必要。 |
| `GOOGLE_CLIENT_SECRET` | **必須** | Google API クライアントシークレット。 |
| `GOOGLE_REDIRECT_URI` | **必須** | `https://your-domain.com/auth/google/callback`。 |
| `SMTP_HOST` | 任意 | メール通知用。未設定時はログ出力のみとなり送信はスキップ。 |
| `SMTP_USER` / `SMTP_PASS`| 任意 | SMTP 認証情報。 |
| `CRON_SECRET` | 任意 | Vercel Cron の実行認証に使用。Bearer トークン。 |
| `CORS_ALLOWED_ORIGINS` | 任意 | カンマ区切りでオリジンを指定。空の場合は Same-origin に制限。 |

### 7.2. 依存パッケージと主要な役割
`requirements.txt` に含まれるライブラリ群の利用目的：
*   **Flask-SQLAlchemy / psycopg2-binary**: Postgres への接続と ORM 操作。
*   **Flask-Migrate**: Alembic を用いたスキーマ管理。`api/index.py` での自動実行をサポート。
*   **Flask-Session**: サーバーサイドセッション。DB 内の `sessions` テーブルで永続化。
*   **Google API Client (Discovery/OAuth)**: Google Calendar の CRUD 操作とトークン更新。
*   **Flask-Limiter**: Redis（未導入時はメモリ/DB）による API レート制限の提供。
*   **cryptography**: リフレッシュトークンの安全な保存のための暗号化。

### 7.3. セキュリティ・ポリシーの詳細
`app/__init__.py` 内の `_register_security_headers` によるヘッダー制御：
*   **Content-Security-Policy (CSP)**: 
    *   `script-src`: `'self'`, `https://unpkg.com` (外部JS)。
    *   `style-src`: `'self'`, `'unsafe-inline'`, `https://fonts.googleapis.com`。
    *   `connect-src`: Google API (`accounts.google.com`, `oauth2.googleapis.com`) への通信許可。
*   **HSTS**: 本番環境 (`not app.debug`) において `max-age=31536000` を付与し HTTPS を強制。
*   **XSS/Sniffing 保護**: `X-Content-Type-Options: nosniff`, `X-XSS-Protection: 1; mode=block`。

### 7.4. ローカル開発と検証
*   **サーバー起動**: `python wsgi.py`（デフォルト5000番ポート）。
*   **データベース**: 開発時は `sqlite:///tokens.db` が自動的に作成され使用されます。
*   **テスト実行**: `pytest` コマンドにより `tests/` 内の全テストを実行。`TestConfig` によりインメモリ DB で検証。

---

## 8. 外部サービス連携の技術詳細 (External Integrations)

システム外部（Google, SMTP）との通信に関する堅牢性とセキュリティの実装詳細です。

### 8.1. Google Calendar API 連携
*   **トークンの秘匿化**: `UserToken.refresh_token` は、`SECRET_KEY` をシードとした `cryptography.fernet` により暗号化されて保存されます。
*   **自動リフレッシュ**: `get_credentials_for_user` 関数が、アクセストークンの期限切れを検知すると自動的に Google API へリフレッシュリクエストを送信し、セッション情報を更新します。
*   **失効検知と再認証フロー**: ユーザーが Google 側で連携を解除した場合（`RefreshError`）、DB 内のトークンを破棄し、フロントエンドに `CREDENTIALS_EXPIRED` エラーを返却。`api-client.js` がこれを検知し、ユーザーに再ログインを促すモーダルを表示します。

### 8.2. SMTP (Email) 通知連携
*   **多重化された送信戦略**: 
    *   **Primary**: `AsyncTask` による非同期バックグラウンド送信。API のレスポンス速度を維持。
    *   **Fallback**: DB 接続不可やキュー登録失敗時には、その場で同期送信 (`send_email`) を実行し、通知の不達を最小限に抑えます。
*   **セキュリティ**: メールの `Subject` に対する SMTP ヘッダーインジェクション攻撃を防ぐため、制御文字 (`\r`, `\n`) のサニタイジング処理を実装しています。
*   **構成の柔軟性**: `SMTP_HOST` が未定義の環境では、送信処理をスキップしつつ警告ログを出力。ローカル開発環境での利便性を確保しています。

### 8.3. 同期と整合性の維持
*   **リトライポリシー**: ネットワークエラー等の一時的障害に対し、`task_runner` が 30秒〜最大数時間の指数バックオフを伴う再試行（最大3回）を自動実行します。
*   **データ整合性**: カレンダー同期の結果（`event_id`）は DB に書き戻され、後の更新や削除時に正確な対象指定を可能にしています。

---

## 9. 設定整合性チェックリスト (Configuration Integrity Checklist)

デプロイ時および運用時に、外部サービスの管理画面とコードの期待値が一致しているかを確認するための検証項目です。

### 9.1. Vercel Dashboard 設定の検証
| 項目 | コードの期待値 | 検証ポイント |
| :--- | :--- | :--- |
| **Environment Variables** | `SECRET_KEY`, `DATABASE_URL`, `CRON_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` | **全項目必須**。不足していると `create_app` または `get_credentials_for_user` で実行時エラーが発生します。 |
| **Database Connection** | `postgresql://` 形式への置換 | Vercel Postgres を使用する場合、自動生成される `POSTGRES_URL` を `DATABASE_URL` にエイリアス設定するか、`config.py` での取得順序を確認してください。 |
| **Cron Jobs** | `/api/cron/process-tasks` | `vercel.json` とダッシュボード上の Cron 実行ログを確認し、200 OK が返っているか（401 の場合は `CRON_SECRET` の不一致）を検証。 |

### 9.2. Google Cloud Console (GCC) 設定の検証
| 項目 | コードの要求仕様 | 検証ポイント |
| :--- | :--- | :--- |
| **OAuth Consent Screen** | `Access Type: offline`, `Prompt: consent` | ユーザーが初回ログイン時に必ず承認画面（リフレッシュトークン発行用）を通過する設定であることを確認。 |
| **Enabled APIs** | `Google Calendar API` | API ライブラリでカレンダー機能が有効化されていないと、403 Forbidden が発生します。 |
| **Authorized Redirect URIs** | `https://[DOMAIN]/auth/google/callback` | 末尾のスラッシュの有無まで、`GOOGLE_REDIRECT_URI` 環境変数と完全に一致させてください。 |
| **OAuth Scopes** | `.../auth/calendar`, `.../auth/calendar.events` | カレンダーの読み書き権限がスコープに含まれているか確認。 |

### 9.3. 外部 SMTP サービス設定の検証
| 項目 | コードの要求仕様 | 検証ポイント |
| :--- | :--- | :--- |
| **Connection Port** | `587` (TLS) | `app/services/notification_service.py` は `server.starttls()` を前提としています。465 (SSL) ではなく 587 を使用してください。 |
| **From Address** | `SMTP_FROM` or `SMTP_USER` | 送信元アドレスが SMTP サービス側で許可（Sender Authentication）されていることを確認。 |

---
*最終更新日: 2026年3月3日*
*分析精度: 完全網羅 (Architecture/Models/Services/Vercel/Environment/External/Configuration 100% 解析済)*

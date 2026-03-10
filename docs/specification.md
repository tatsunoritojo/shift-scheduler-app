# Shifree (シフリー) — システム仕様書

> 最終更新: 2026-03-10
> バージョン: 1.0

---

## 1. システム概要

Shifree は小規模事業者向けのシフト管理 Web アプリケーション。
アルバイトスタッフがシフト希望を提出し、管理者がスケジュールを構築、事業主が承認するワークフローを提供する。

### 1.1 技術スタック

| レイヤー | 技術 |
|---------|------|
| バックエンド | Flask 3.1.1 + SQLAlchemy ORM |
| 認証 | Google OAuth 2.0 + Google Calendar API v3 |
| セッション | サーバーサイド (Flask-Session / SQLAlchemy バックエンド) |
| DB | SQLite (開発) / PostgreSQL (本番) |
| フロントエンド | Vanilla HTML/CSS/JS SPA (ES Modules, ロール別ページ) |
| デプロイ | Vercel Serverless (Python Runtime) |
| セキュリティ | Flask-Limiter, CORS, CSP, Fernet 暗号化 |

### 1.2 アーキテクチャ図

```
┌─────────────────────────────────────────────────────┐
│  Vercel Edge                                         │
│  ┌─────────────────────────────────────────────────┐ │
│  │  api/index.py (エントリーポイント)                  │ │
│  │  ├─ Flask-Migrate 自動マイグレーション (cold start) │ │
│  │  └─ create_app('production')                      │ │
│  └─────────────────────────────────────────────────┘ │
│           │                                          │
│  ┌────────▼────────┐  ┌───────────────────────┐      │
│  │  Blueprints      │  │  Static Assets        │      │
│  │  ├─ auth         │  │  ├─ pages/*.html      │      │
│  │  ├─ api_admin    │  │  ├─ js/modules/*.js   │      │
│  │  ├─ api_worker   │  │  ├─ js/*-app.js       │      │
│  │  ├─ api_owner    │  │  └─ css/*.css         │      │
│  │  ├─ api_calendar │  └───────────────────────┘      │
│  │  ├─ api_cron     │                                 │
│  │  ├─ api_dashboard│                                 │
│  │  └─ api_master   │                                 │
│  └────────┬────────┘                                 │
│  ┌────────▼────────┐                                 │
│  │  Services        │  ← ビジネスロジック層            │
│  │  ├─ auth         │                                 │
│  │  ├─ shift        │                                 │
│  │  ├─ approval     │                                 │
│  │  ├─ notification │                                 │
│  │  ├─ calendar     │                                 │
│  │  ├─ reminder     │                                 │
│  │  ├─ vacancy      │                                 │
│  │  ├─ task_runner  │                                 │
│  │  └─ audit        │                                 │
│  └────────┬────────┘                                 │
│  ┌────────▼────────┐                                 │
│  │  Models (13+)    │  ← SQLAlchemy ORM              │
│  └────────┬────────┘                                 │
│           ▼                                          │
│     PostgreSQL (本番) / SQLite (開発)                  │
└─────────────────────────────────────────────────────┘
```

---

## 2. ユーザーロールと権限

### 2.1 ロール定義

| ロール | 日本語 | 主な権限 |
|--------|--------|---------|
| `admin` | 管理者 | シフト期間管理, スケジュール構築, メンバー管理, 招待, 営業時間設定 |
| `owner` | 事業主 | スケジュール承認/差戻し |
| `worker` | アルバイト | シフト希望提出, カレンダー連携 |
| `master` | アプリ管理者 | 全組織横断管理 (MASTER_EMAIL 環境変数で指定) |

### 2.2 ロール判定優先順位

1. DB の `OrganizationMember` レコード (正規化されたソース)
2. 環境変数 `ADMIN_EMAIL` / `OWNER_EMAIL` (初回ブートストラップ用)
3. デフォルト: `worker`

### 2.3 マルチテナント

- `OrganizationMember` が権限のソースオブトゥルース
- `User.role` / `User.organization_id` は非正規化キャッシュ (stale になりうる)
- 全 API エンドポイントで `organization_id` による隔離を強制
- 組織未所属ユーザーは `/no-organization` ページへリダイレクト

---

## 3. データモデル

### 3.1 ER 図 (主要リレーション)

```
Organization (1) ──< OrganizationMember >── (N) User
     │                                          │
     │ (1)                                      │ (1)
     ├──< OpeningHours (7: 曜日別)               ├──< UserToken (1)
     ├──< OpeningHoursException (N)              ├──< ShiftSubmission (N)
     ├──< InvitationToken (N)                    │
     └──< ShiftPeriod (N)                        │
              │                                  │
              └──< ShiftSchedule (N)             │
                       │                         │
                       ├──< ShiftScheduleEntry >─┘
                       ├──< ApprovalHistory (N)
                       └──< VacancyRequest (N)
                                │
                                └──< VacancyCandidate (N)
```

### 3.2 テーブル定義

#### organizations
| カラム | 型 | 説明 |
|--------|-----|------|
| id | Integer PK | |
| name | String(200) | 組織名 |
| admin_email | String(200) | 管理者メール |
| owner_email | String(200) | 事業主メール |
| settings_json | Text | JSON 設定 (リマインダー等) |
| invite_code | String(100) UNIQUE | 招待コード |
| invite_code_enabled | Boolean | 招待コード有効/無効 |

#### users
| カラム | 型 | 説明 |
|--------|-----|------|
| id | Integer PK | |
| google_id | String(100) UNIQUE | Google OAuth ID |
| email | String(200) UNIQUE | メールアドレス |
| display_name | String(200) | 表示名 |
| role | String(20) | キャッシュロール (admin/owner/worker) |
| organization_id | Integer FK | キャッシュ org ID |
| is_active | Boolean | 有効/無効 |

#### organization_members
| カラム | 型 | 説明 |
|--------|-----|------|
| id | Integer PK | |
| user_id | Integer FK | ユーザー |
| organization_id | Integer FK | 組織 |
| role | String(20) | 権限ロール |
| is_active | Boolean | 有効/無効 |
| invited_by | Integer FK | 招待者 |
| joined_at | DateTime | 参加日時 |

#### invitation_tokens
| カラム | 型 | 説明 |
|--------|-----|------|
| id | Integer PK | |
| token | String(200) UNIQUE | secrets.token_urlsafe(32) |
| organization_id | Integer FK | 対象組織 |
| role | String(20) | 付与ロール |
| email | String(200) | 制限メール (省略可) |
| created_by | Integer FK | 作成者 |
| expires_at | DateTime | 有効期限 |
| used_at | DateTime | 使用日時 |
| used_by | Integer FK | 使用者 |

#### shift_periods
| カラム | 型 | 説明 |
|--------|-----|------|
| id | Integer PK | |
| organization_id | Integer FK | 組織 |
| name | String(200) | 期間名 |
| start_date | Date | 開始日 |
| end_date | Date | 終了日 |
| submission_deadline | DateTime | 提出期限 |
| status | String(20) | draft / open / closed / finalized |
| created_by | Integer FK | 作成者 |

#### shift_submissions
| カラム | 型 | 説明 |
|--------|-----|------|
| id | Integer PK | |
| shift_period_id | Integer FK | 対象期間 |
| user_id | Integer FK | ワーカー |
| status | String(20) | draft / submitted / revised |
| submitted_at | DateTime | 提出日時 |
| notes | Text | 備考 |

#### shift_submission_slots
| カラム | 型 | 説明 |
|--------|-----|------|
| id | Integer PK | |
| submission_id | Integer FK | 提出 |
| slot_date | Date | 日付 |
| is_available | Boolean | 出勤可能 |
| start_time | String(5) | 開始時刻 HH:MM |
| end_time | String(5) | 終了時刻 HH:MM |
| is_custom_time | Boolean | カスタム時間指定 |
| notes | Text | 日別備考 |

#### shift_schedules
| カラム | 型 | 説明 |
|--------|-----|------|
| id | Integer PK | |
| shift_period_id | Integer FK | 対象期間 |
| status | String(20) | draft / pending_approval / approved / rejected / confirmed |
| created_by | Integer FK | 作成者 (admin) |
| approved_by | Integer FK | 承認者 (owner) |
| rejection_reason | Text | 差戻し理由 |

#### shift_schedule_entries
| カラム | 型 | 説明 |
|--------|-----|------|
| id | Integer PK | |
| schedule_id | Integer FK | スケジュール |
| user_id | Integer FK | 割当ワーカー |
| shift_date | Date | シフト日 |
| start_time | String(5) | 開始時刻 |
| end_time | String(5) | 終了時刻 |
| calendar_event_id | String(200) | Google Calendar イベント ID |
| synced_at | DateTime | カレンダー同期日時 |

#### opening_hours
| カラム | 型 | 説明 |
|--------|-----|------|
| id | Integer PK | |
| organization_id | Integer FK | 組織 |
| day_of_week | Integer | 0 (日) 〜 6 (土) |
| start_time | String(5) | 営業開始 |
| end_time | String(5) | 営業終了 |
| is_closed | Boolean | 定休日 |

#### opening_hours_exceptions
| カラム | 型 | 説明 |
|--------|-----|------|
| id | Integer PK | |
| organization_id | Integer FK | 組織 |
| exception_date | Date | 対象日 |
| start_time / end_time | String(5) | 時間変更 |
| is_closed | Boolean | 臨時休業 |
| reason | String(2000) | 理由 |
| source | String(20) | manual / calendar |

#### async_tasks
| カラム | 型 | 説明 |
|--------|-----|------|
| id | Integer PK | |
| task_type | String(50) | send_email / sync_calendar_event |
| payload | Text (JSON) | タスクデータ |
| status | String(20) | pending / running / completed / failed / dead |
| priority | Integer | 優先度 (大きいほど先) |
| retry_count | Integer | リトライ回数 |
| max_retries | Integer | 最大リトライ |
| next_run_at | DateTime | 次回実行 |
| error_message | Text | エラー内容 |

#### reminders
| カラム | 型 | 説明 |
|--------|-----|------|
| id | Integer PK | |
| organization_id | Integer FK | 組織 |
| reminder_type | String(50) | submission_deadline / preshift |
| reference_id | Integer | 参照 ID (period_id 等) |
| user_id | Integer FK | 送信先ユーザー |
| sent_at | DateTime | 送信日時 |
| UniqueConstraint | | (type, reference_id, user_id) で重複防止 |

#### vacancy_requests
| カラム | 型 | 説明 |
|--------|-----|------|
| id | Integer PK | |
| schedule_entry_id | Integer FK | 対象シフトエントリ |
| original_user_id | Integer FK | 元の担当者 |
| reason | Text | 欠員理由 |
| status | String(20) | open / notified / accepted / expired / cancelled |
| accepted_by | Integer FK | 受諾者 |
| expires_at | DateTime | 有効期限 |

#### vacancy_candidates
| カラム | 型 | 説明 |
|--------|-----|------|
| id | Integer PK | |
| vacancy_request_id | Integer FK | 欠員リクエスト |
| user_id | Integer FK | 候補者 |
| status | String(20) | pending / notified / accepted / declined / expired |
| response_token | String(200) | 署名付き応答トークン |
| notified_at / responded_at | DateTime | |

#### audit_logs
| カラム | 型 | 説明 |
|--------|-----|------|
| id | Integer PK | |
| organization_id | Integer FK | 組織 |
| actor_id | Integer FK | 操作者 |
| action | String(100) | 操作種別 |
| resource_type / resource_id | String, Integer | 対象リソース |
| old_values / new_values | Text (JSON) | 変更前後 |
| status | String(20) | SUCCESS / FAILED |

---

## 4. API エンドポイント一覧

### 4.1 認証 (auth_bp)

| メソッド | パス | 説明 | レート制限 |
|---------|------|------|-----------|
| GET | `/auth/google/login` | OAuth 開始 | 10/min |
| GET | `/auth/google/callback` | OAuth コールバック | 10/min |
| GET | `/auth/invite/<token>` | 招待トークン受理 | — |
| GET | `/auth/me` | 現在のユーザー情報 | — |
| POST | `/auth/logout` | ログアウト | — |

### 4.2 共通 (api_common_bp)

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/` | ルーティング (ロール別ページへ) |
| GET | `/health` | ヘルスチェック |
| GET | `/login` | ログインページ |
| GET | `/no-organization` | 組織未所属ページ |
| POST | `/api/organizations` | 組織作成 (5/hour) |

### 4.3 管理者 API (api_admin_bp: `/api/admin/*`)

| メソッド | パス | 説明 |
|---------|------|------|
| GET/PUT | `/opening-hours` | 営業時間 CRUD |
| GET/POST | `/opening-hours/exceptions` | 例外日 CRUD |
| PUT/DELETE | `/opening-hours/exceptions/<id>` | 例外日 更新/削除 |
| POST | `/opening-hours/sync/export` | カレンダーへエクスポート |
| POST | `/opening-hours/sync/import` | カレンダーからインポート |
| GET | `/opening-hours/sync/status` | 同期ステータス |
| GET | `/opening-hours/sync/logs` | 同期ログ |
| GET/POST | `/periods` | シフト期間 CRUD |
| PUT | `/periods/<id>` | 期間更新 |
| GET | `/periods/<id>/opening-hours` | 期間別営業時間 |
| GET | `/periods/<id>/submissions` | 提出一覧 |
| GET/POST | `/periods/<id>/schedule` | スケジュール取得/保存 |
| POST | `/periods/<id>/schedule/submit` | 承認依頼 |
| POST | `/periods/<id>/schedule/confirm` | 確定 + カレンダー同期 |
| GET | `/workers` | ワーカー一覧 |
| GET | `/workers/<id>/history` | ワーカー履歴 |
| GET | `/members` | メンバー一覧 |
| PUT | `/members/<id>/role` | ロール変更 |
| DELETE | `/members/<id>` | メンバー削除 |
| GET/POST | `/invitations` | 招待 CRUD |
| DELETE | `/invitations/<id>` | 招待取消 |
| GET/POST/PUT | `/invite-code` | 招待コード管理 |
| GET | `/vacancy/candidates/<entry_id>` | 欠員候補検索 |
| POST | `/vacancy` | 欠員リクエスト作成 |
| POST | `/vacancy/<id>/notify` | 候補者通知 |
| DELETE | `/vacancy/<id>` | 欠員リクエスト取消 |
| GET | `/vacancy` | 欠員リクエスト一覧 |
| GET | `/change-log` | シフト変更履歴 |
| GET/PUT | `/reminder-settings` | リマインダー設定 |
| POST | `/reminders/send/<period_id>` | 手動リマインド送信 |
| GET | `/reminders/stats/<period_id>` | リマインダー統計 |

### 4.4 ワーカー API (api_worker_bp: `/api/worker/*`)

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/periods` | 公開中の期間一覧 |
| GET | `/periods/<id>/opening-hours` | 期間別営業時間 |
| GET | `/calendars` | Google カレンダー一覧 |
| GET | `/calendar/events` | カレンダーイベント取得 |
| GET | `/periods/<id>/availability` | 自分の提出取得 |
| POST | `/periods/<id>/availability` | 希望提出 |

### 4.5 事業主 API (api_owner_bp: `/api/owner/*`)

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/pending-approvals` | 承認待ち一覧 |
| GET | `/schedules/<id>` | スケジュール詳細 |
| POST | `/schedules/<id>/approve` | 承認 |
| POST | `/schedules/<id>/reject` | 差戻し |

### 4.6 Cron (api_cron_bp)

| メソッド | パス | 説明 |
|---------|------|------|
| POST | `/api/cron/process-tasks` | 非同期タスク処理 (Bearer CRON_SECRET) |

### 4.7 ダッシュボード (api_dashboard_bp: `/api/admin/dashboard/*`)

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/overview` | 概要統計 |
| GET | `/tasks` | タスク一覧 |
| GET | `/task-stats` | タスク統計 |
| GET | `/audit-logs` | 監査ログ |

### 4.8 マスター管理 (api_master_bp)

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/master` | マスター管理ページ |
| GET | `/api/master/*` | システム横断管理 API |

---

## 5. 業務フロー

### 5.1 シフト管理ワークフロー

```
管理者: 期間作成 (draft)
    │
    ▼
管理者: 期間公開 (open)
    │
    ▼
ワーカー: シフト希望提出 (submitted)
    │    ← 提出期限リマインダー (自動/手動)
    ▼
管理者: スケジュール構築 (draft)
    │
    ▼
管理者: 承認依頼 (pending_approval)
    │    → 事業主へメール通知
    ▼
事業主: 承認 (approved) or 差戻し (rejected)
    │    → 管理者へメール通知
    ▼
管理者: 確定 (confirmed)
    │    → Google Calendar 自動同期
    ▼
[運用中]
    │
    ▼ (欠員発生時)
管理者: 欠員リクエスト作成
    │
    ▼
システム: 候補者検索 (週間勤務時間の少ない順)
    │
    ▼
管理者: 候補者へ通知メール (トークン付き accept/decline リンク)
    │
    ▼
候補者: 引受け or 辞退
    │    (先着1名のみ受理、レースコンディション防止)
    ▼
管理者へ結果通知 + 変更履歴記録
```

### 5.2 招待フロー

```
管理者: 招待トークン作成 (メール指定 or 汎用)
    │
    ├─ メール指定 → 招待メール送信 (リンク付き)
    │
    └─ 招待コード → QR コード / リンク共有
         │
         ▼
新規ユーザー: /invite?code=X or /auth/invite/<token>
    │
    ▼
Cookie にトークン保存 (itsdangerous 署名, HttpOnly, 10分)
    │
    ▼
Google OAuth ログイン
    │
    ▼
upsert_user(): 招待トークン > 招待コード > env bootstrap
    │
    ▼
OrganizationMember 作成 + ロール割当
```

### 5.3 認証フロー

```
1. GET /auth/google/login
   → OAuth state 生成 (1回使い切り)
   → Google 認証画面へリダイレクト

2. GET /auth/google/callback
   → state 検証 (セッション内の値と一致確認)
   → トークン取得
   → id_token から user info 抽出 (dict or JWT verify)
   → フォールバック: userinfo API

3. upsert_user()
   → ユーザー作成/更新
   → 組織割当 (招待 > コード > env > なし)
   → OrganizationMember 同期

4. セッション設定 (user_id, credentials)
   → ロール別ページへリダイレクト
```

---

## 6. 非同期タスクシステム

### 6.1 アーキテクチャ

DB ベースキュー (外部メッセージブローカー不要、サーバーレス互換)。

```
サービス層: enqueue_email() / enqueue_calendar_sync()
    │
    ▼
AsyncTask テーブル (status: pending)
    │
    ▼ Vercel Cron (1日1回 9:00 JST)
POST /api/cron/process-tasks (Bearer CRON_SECRET)
    │
    ▼
task_runner.process_pending_tasks()
    ├─ 最大20件取得 (priority DESC, created_at ASC)
    ├─ ハンドラ実行 (@register_handler)
    ├─ 成功 → completed
    └─ 失敗 → retry (指数バックオフ: 30s, 2m, 8m) or dead
```

### 6.2 タスクタイプ

| タイプ | ハンドラ | 説明 |
|--------|---------|------|
| `send_email` | SMTP 送信 | メール通知 |
| `sync_calendar_event` | Google Calendar API | カレンダーイベント同期 |

---

## 7. セキュリティ

### 7.1 認証・認可

- Google OAuth 2.0 (id_token + userinfo API フォールバック)
- サーバーサイドセッション (SQLAlchemy, 24時間有効)
- Cookie: HttpOnly, SameSite=Lax, Secure (本番)
- リフレッシュトークン: Fernet 暗号化 (SHA-256 派生鍵)

### 7.2 HTTP セキュリティヘッダー

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
Strict-Transport-Security: max-age=31536000 (本番のみ)
Content-Security-Policy: default-src 'self'; script-src 'self' unpkg.com; ...
```

### 7.3 レート制限

| エンドポイント | 制限 |
|---------------|------|
| OAuth | 10/min |
| 招待情報 | 20/min |
| 組織作成 | 5/hour |
| デフォルト | 200/hour |

### 7.4 CORS

- 開発: 全オリジン許可
- 本番: `CORS_ALLOWED_ORIGINS` 未設定 → same-origin only (fail-closed)

### 7.5 SMTP ヘッダーインジェクション対策

- `_sanitize_subject()`: CR/LF/NUL を除去

---

## 8. フロントエンド構成

### 8.1 ページ構成

| ページ | ファイル | ロール | 説明 |
|--------|---------|--------|------|
| 管理者 | admin.html + admin-app.js | admin | 期間管理, スケジュール構築, メンバー管理 |
| ワーカー | worker.html + worker-app.js | worker | シフト希望提出, カレンダー連携 |
| 事業主 | owner.html + owner-app.js | owner | 承認ワークフロー |
| マスター | master.html + master-app.js | master | システム管理 |
| ログイン | login.html | 全員 | Google OAuth ボタン |
| 招待 | invite.html + invite.js | 未認証 | 招待受理 |
| 組織なし | no-organization.html + no-org.js | 認証済 | 組織作成 |
| LP | landing.html + landing-hero.js | 未認証 | マーケティング |

### 8.2 共有モジュール (static/js/modules/)

| モジュール | 説明 |
|-----------|------|
| api-client.js | HTTP クライアント (fetch ラッパー, 401 ハンドリング) |
| calendar-grid.js | 月間カレンダーレンダラー |
| shift-calculator.js | シフト可能時間帯計算 (バッファゾーン対応) |
| time-utils.js | 時間演算ユーティリティ |
| event-utils.js | Google Calendar イベントフィルタ |
| ui-dialogs.js | 確認ダイアログ |
| notification.js | トースト通知 |
| escape-html.js | XSS 防止 |
| btn-loading.js | ボタンローディング状態管理 |
| date-constants.js | 曜日名定数 (リファクタリングで新設) |

### 8.3 CSS 設計

- デザイントークン: CSS カスタムプロパティ (`:root` 変数)
- カラーパレット: primary, success, warning, danger, neutral
- シャドウスケール: sm, md, lg, xl
- レスポンシブ: モバイル対応メディアクエリ
- コンポーネント: ボタン, カード, テーブル, バッジ, モーダル, ダイアログ

---

## 9. 通知テンプレート

| テンプレート | 件名 | トリガー |
|-------------|------|---------|
| approval_requested | 承認依頼: {期間名} | admin がスケジュール承認依頼 |
| approval_result | 承認/差戻し: {期間名} | owner が承認/差戻し |
| invitation_created | {組織名} への招待 | admin がメール指定招待作成 |
| submission_deadline | 提出期限リマインド: {期間名} | cron or 手動トリガー |
| preshift | シフトリマインド: {日付} | cron (前日通知) |
| vacancy_request | 欠員補充のお願い: {日付} | admin が欠員通知送信 |
| vacancy_accepted | 欠員補充完了: {日付} | 候補者が引受け |

---

## 10. 環境変数

| 変数 | 必須 | 説明 |
|------|------|------|
| `FLASK_ENV` | — | development / production (default: development) |
| `SECRET_KEY` | 本番 | Flask セッション暗号鍵 |
| `DATABASE_URL` | 本番 | PostgreSQL 接続文字列 |
| `GOOGLE_CLIENT_ID` | Yes | OAuth クライアント ID |
| `GOOGLE_CLIENT_SECRET` | Yes | OAuth クライアントシークレット |
| `GOOGLE_REDIRECT_URI` | Yes | OAuth コールバック URI |
| `ADMIN_EMAIL` | — | ブートストラップ管理者メール (カンマ区切り) |
| `OWNER_EMAIL` | — | ブートストラップ事業主メール (カンマ区切り) |
| `MASTER_EMAIL` | — | アプリ管理者メール |
| `CRON_SECRET` | — | Cron エンドポイント認証トークン |
| `SMTP_HOST` | — | SMTP サーバー |
| `SMTP_PORT` | — | SMTP ポート (default: 587) |
| `SMTP_USER` | — | SMTP ユーザー |
| `SMTP_PASS` | — | SMTP パスワード |
| `SMTP_FROM` | — | 送信元メール (default: SMTP_USER) |
| `CORS_ALLOWED_ORIGINS` | — | 許可オリジン (本番推奨) |

---

## 11. テスト

### 11.1 テスト構成

- フレームワーク: pytest
- DB: インメモリ SQLite (テスト専用)
- 認証: `AuthActions.login_as(user)` セッションヘルパー
- 外部 API: 全モック (Google OAuth, Calendar, SMTP)

### 11.2 テストカバレッジ

| テストファイル | テスト数 | カテゴリ |
|---------------|---------|---------|
| test_auth.py | 7 | 認証 + ロールチェック |
| test_rbac.py | 13 | RBAC + 招待 |
| test_multitenant.py | 14 | マルチテナント隔離 |
| test_invite_features.py | 18 | 招待トークン + コード |
| test_approval_workflow.py | 10 | 承認ワークフロー |
| test_validation.py | 38 | 入力バリデーション |
| test_error_format.py | 12 | エラーレスポンス形式 |
| test_async_tasks.py | 18 | 非同期タスク + Cron |
| test_dashboard.py | 8 | ダッシュボード |
| test_audit_log.py | 17 | 監査ログ |
| test_reminder.py | 14 | リマインダー |
| test_vacancy.py | 16 | 欠員補充 |
| **合計** | **207** | |

---

## 12. デプロイ

### 12.1 Vercel 設定

```json
{
  "rewrites": [{ "source": "/(.*)", "destination": "/api/index" }],
  "crons": [{ "path": "/api/cron/process-tasks", "schedule": "0 9 * * *" }]
}
```

### 12.2 コールドスタート

`api/index.py` で `flask db upgrade` を自動実行。失敗してもアプリは起動する (ログ出力のみ)。

### 12.3 制約

- Vercel Hobby プラン: cron は 1日1回のみ
- サーバーレス: 長時間実行不可 (タスクは DB キューで非同期化)
- ファイルシステム: 読み取り専用 (SQLite は開発のみ)

---

## 13. マイグレーション履歴

| リビジョン | 内容 |
|-----------|------|
| 25086bfdac9f | 初期スキーマ (13テーブル) |
| dc3fa46ab193 | organization_members + invitation_tokens |
| a1b2c3d4e5f6 | async_tasks テーブル |
| b2c3d4e5f6a7 | audit_logs テーブル |
| c3d4e5f6a7b8 | Organization.invite_code カラム追加 |
| d4e5f6a7b8c9 | reminders, vacancy_requests, vacancy_candidates, shift_change_logs |

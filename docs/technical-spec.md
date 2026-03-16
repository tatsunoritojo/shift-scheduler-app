# Shifree (シフリー) — L3: 技術仕様書

> 最終更新: 2026-03-16
> 対象読者: 開発者

---

## 1. ディレクトリ構成

```
shift-scheduler-app/
├── api/index.py                  # Vercel エントリポイント (cold start で migrate)
├── wsgi.py                       # ローカル開発エントリポイント
├── app/
│   ├── __init__.py               # App Factory (201行)
│   ├── config.py                 # 環境別設定 (97行)
│   ├── extensions.py             # SQLAlchemy, Migrate, CORS, Limiter, Session
│   ├── models/                   # SQLAlchemy モデル (10ファイル, ~900行)
│   │   ├── user.py               # User, UserToken
│   │   ├── organization.py       # Organization
│   │   ├── membership.py         # OrganizationMember, InvitationToken
│   │   ├── shift.py              # ShiftPeriod, ShiftSubmission, ShiftSubmissionSlot,
│   │   │                         #   ShiftSchedule, ShiftScheduleEntry
│   │   ├── approval.py           # ApprovalHistory
│   │   ├── opening_hours.py      # OpeningHours, OpeningHoursException,
│   │   │                         #   OpeningHoursCalendarSync, SyncOperationLog
│   │   ├── async_task.py         # AsyncTask
│   │   ├── audit_log.py          # AuditLog
│   │   ├── reminder.py           # Reminder
│   │   └── vacancy.py            # VacancyRequest, VacancyCandidate, ShiftChangeLog
│   ├── blueprints/               # Flask ルーティング (9ファイル, ~3,300行)
│   │   ├── auth.py               # Google OAuth + 招待
│   │   ├── api_admin.py          # 管理者API (1,251行) ★最大
│   │   ├── api_worker.py         # スタッフAPI
│   │   ├── api_owner.py          # 事業主API
│   │   ├── api_calendar.py       # カレンダーAPI
│   │   ├── api_common.py         # 共通ルーティング
│   │   ├── api_cron.py           # Cron エンドポイント
│   │   ├── api_dashboard.py      # ダッシュボードAPI
│   │   └── api_master.py         # マスター管理 (965行)
│   ├── services/                 # ビジネスロジック (10ファイル, ~2,250行)
│   │   ├── auth_service.py       # OAuth, upsert_user, トークン管理
│   │   ├── shift_service.py      # 営業時間, 提出, スケジュール保存
│   │   ├── approval_service.py   # 承認ワークフロー状態遷移
│   │   ├── notification_service.py # メール通知 (非同期キュー)
│   │   ├── task_runner.py        # 非同期タスク処理 + ハンドラ登録
│   │   ├── vacancy_service.py    # 欠員補充 (417行)
│   │   ├── reminder_service.py   # リマインダー自動送信
│   │   ├── opening_hours_sync_service.py # Google Calendar 同期
│   │   ├── calendar_service.py   # Google Calendar API ラッパー
│   │   └── audit_service.py      # 監査ログ記録
│   ├── middleware/
│   │   └── auth_middleware.py    # @require_auth, @require_role (64行)
│   └── utils/
│       ├── errors.py             # APIError, error_response
│       ├── validators.py         # 時間/テキストバリデーション
│       ├── time_utils.py         # HH:MM ↔ 分変換
│       └── crypto.py             # Fernet トークン暗号化
├── static/
│   ├── pages/                    # ロール別 HTML (8ファイル)
│   ├── js/
│   │   ├── admin-app.js          # 管理者アプリ (2,035行) ★最大
│   │   ├── worker-app.js         # スタッフアプリ (890行)
│   │   ├── owner-app.js          # 事業主アプリ (217行)
│   │   ├── master-app.js         # マスターアプリ (674行)
│   │   └── modules/              # 共有モジュール (10ファイル, ~550行)
│   └── css/                      # スタイルシート (6ファイル, ~4,600行)
├── tests/                        # pytest (13ファイル, 207テスト)
├── migrations/versions/          # Alembic マイグレーション (6ファイル)
├── vercel.json                   # Vercel 設定
├── requirements.txt              # Python 依存
└── pytest.ini                    # テスト設定
```

---

## 2. データモデル (ER図)

```
Organization (1) ──< OrganizationMember >── (N) User
     │                                          │
     │ (1)                                      │ (1)
     ├──< OpeningHours (7: 曜日別)               ├──< UserToken (1)
     ├──< OpeningHoursException (N)              ├──< ShiftSubmission (N)
     ├──< OpeningHoursCalendarSync (N)           │
     ├──< InvitationToken (N)                    │
     ├──< Reminder (N)                           │
     ├──< AuditLog (N)                           │
     └──< ShiftPeriod (N)                        │
              │                                  │
              ├──< ShiftSubmission (N) ──────────┘
              │        └──< ShiftSubmissionSlot (N)
              │
              └──< ShiftSchedule (N)
                       │
                       ├──< ShiftScheduleEntry >── User
                       │        └──< VacancyRequest (N)
                       │                 └──< VacancyCandidate (N)
                       │
                       ├──< ApprovalHistory (N)
                       └──< ShiftChangeLog (N)

AsyncTask (独立テーブル — 組織横断キュー)
SyncOperationLog (独立テーブル — 同期操作履歴)
```

### 主要なユニーク制約

| テーブル | 制約 |
|---|---|
| users | google_id UNIQUE, email UNIQUE |
| organization_members | (user_id, organization_id) UNIQUE |
| shift_submissions | (shift_period_id, user_id) UNIQUE |
| opening_hours | (organization_id, day_of_week) UNIQUE |
| reminders | (reminder_type, reference_id, user_id) UNIQUE |
| vacancy_candidates | (vacancy_request_id, user_id) UNIQUE |

---

## 3. API エンドポイント一覧

### 3.1 認証 (auth_bp)

| Method | Path | Rate | Description |
|---|---|---|---|
| GET | `/auth/google/login` | 10/min | OAuth 開始 |
| GET | `/auth/google/callback` | 10/min | OAuth コールバック |
| GET | `/auth/invite/<token>` | — | 招待トークン受理 |
| GET | `/auth/invite/code/<code>` | — | 招待コード受理 |
| GET | `/auth/me` | — | 現在のユーザー情報 |
| POST | `/auth/logout` | — | ログアウト |

### 3.2 管理者 API (api_admin_bp: `/api/admin/*`)

**営業時間:**

| Method | Path | Description |
|---|---|---|
| GET/PUT | `/opening-hours` | 基本営業時間 CRUD |
| GET/POST | `/opening-hours/exceptions` | 例外日 CRUD |
| PUT/DELETE | `/opening-hours/exceptions/<id>` | 例外日 更新/削除 |
| POST | `/opening-hours/sync/export` | Calendar エクスポート |
| POST | `/opening-hours/sync/import` | Calendar インポート |
| GET | `/opening-hours/sync/status` | 同期ステータス |
| GET | `/opening-hours/sync/logs` | 同期ログ |

**期間・スケジュール:**

| Method | Path | Description |
|---|---|---|
| GET/POST | `/periods` | 期間 CRUD |
| PUT | `/periods/<id>` | 期間更新 |
| GET | `/periods/<id>/opening-hours` | 期間別営業時間 |
| GET | `/periods/<id>/submissions` | 提出一覧 |
| GET/POST | `/periods/<id>/schedule` | スケジュール取得/保存 |
| POST | `/periods/<id>/schedule/submit` | 承認依頼 |
| POST | `/periods/<id>/schedule/confirm` | 確定 + Calendar同期 |

**メンバー・招待:**

| Method | Path | Description |
|---|---|---|
| GET | `/members` | メンバー一覧 |
| PUT | `/members/<id>/role` | ロール変更 |
| DELETE | `/members/<id>` | メンバー削除 |
| GET/POST | `/invitations` | 招待 CRUD |
| DELETE | `/invitations/<id>` | 招待取消 |
| GET/POST/PUT | `/invite-code` | 招待コード管理 |
| GET | `/workers` | ワーカー一覧 |

**欠員・リマインダー:**

| Method | Path | Description |
|---|---|---|
| GET | `/vacancy/candidates/<entry_id>` | 候補者検索 |
| POST | `/vacancy` | 欠員リクエスト作成 |
| POST | `/vacancy/<id>/notify` | 候補者通知 |
| DELETE | `/vacancy/<id>` | リクエスト取消 |
| GET | `/vacancy` | リクエスト一覧 |
| GET | `/change-log` | 変更履歴 |
| GET/PUT | `/reminder-settings` | リマインダー設定 |
| POST | `/reminders/send/<period_id>` | 手動リマインド |
| GET | `/reminders/stats/<period_id>` | リマインダー統計 |

### 3.3 スタッフ API (api_worker_bp: `/api/worker/*`)

| Method | Path | Description |
|---|---|---|
| GET | `/periods` | 公開中の期間一覧 |
| GET | `/periods/<id>/opening-hours` | 期間別営業時間 |
| GET | `/calendars` | Google Calendar 一覧 |
| GET | `/calendar/events` | Calendar イベント取得 |
| GET | `/periods/<id>/availability` | 自分の提出取得 |
| POST | `/periods/<id>/availability` | 希望提出 |

### 3.4 事業主 API (api_owner_bp: `/api/owner/*`)

| Method | Path | Description |
|---|---|---|
| GET | `/pending-approvals` | 承認待ち一覧 |
| GET | `/schedules/<id>` | スケジュール詳細 |
| POST | `/schedules/<id>/approve` | 承認 |
| POST | `/schedules/<id>/reject` | 差戻し |

### 3.5 システム

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/cron/process-tasks` | CRON_SECRET | 非同期タスク処理 + リマインダー |
| GET | `/api/admin/dashboard/overview` | admin | 概要統計 |
| GET | `/api/admin/dashboard/tasks` | admin | タスク一覧 |
| GET | `/api/admin/dashboard/audit-logs` | admin | 監査ログ |
| GET | `/api/invite/info` | public | 招待情報確認 |
| GET | `/vacancy/respond` | public (token) | 欠員応答 |
| POST | `/api/organizations` | auth | 組織作成 (5/hour) |

---

## 4. サービス層

### 4.1 auth_service.py (366行)

| 関数 | 引数 | 戻り値 | 説明 |
|---|---|---|---|
| `create_oauth_flow()` | — | `Flow` | Google OAuth フロー生成 |
| `extract_user_info(credentials)` | Credentials | dict | id_token → {google_id, email, display_name} |
| `determine_role(email)` | str | str | OrganizationMember → env → 'worker' |
| `upsert_user(google_id, email, name, invitation_token, invite_code_org)` | ... | User | ユーザー作成/更新 + 組織割当 |
| `save_refresh_token(user, token)` | User, str | — | Fernet 暗号化して DB 保存 |
| `get_credentials_for_user(user)` | User | Credentials\|None | refresh_token → access_token 自動更新 |

### 4.2 shift_service.py (239行)

| 関数 | 説明 |
|---|---|
| `get_opening_hours_for_date(org_id, date)` | 例外 > 通常 > None の優先順で営業時間取得 |
| `get_opening_hours_for_period(org_id, start, end)` | 期間内の全日営業時間を一括取得 |
| `create_or_update_submission(period_id, user_id, slots, notes)` | 冪等なシフト希望保存 |
| `save_schedule(period_id, created_by, entries, org_id)` | スケジュール保存 (在籍・日付範囲検証) |
| `get_worker_hours_summary(schedule_id)` | スタッフ別月間合計時間 |

### 4.3 approval_service.py (193行)

状態遷移は `_transition_schedule()` で統一。ApprovalHistory + AuditLog を自動記録。

| 関数 | 遷移 |
|---|---|
| `submit_for_approval(schedule_id, admin)` | draft → pending_approval |
| `approve_schedule(schedule_id, owner, comment)` | pending_approval → approved |
| `reject_schedule(schedule_id, owner, comment)` | pending_approval → rejected |
| `confirm_schedule(schedule_id, admin)` | approved → confirmed |

### 4.4 vacancy_service.py (417行)

| 関数 | 説明 |
|---|---|
| `find_candidates(entry_id, org_id)` | 条件一致 + 週間時間少ない順ソート |
| `create_vacancy_request(entry_id, reason, admin)` | 欠員リクエスト作成 |
| `send_vacancy_notifications(req_id, user_ids, base_url)` | トークン発行 + メール通知 |
| `respond_to_vacancy(token, action)` | accept/decline (レースコンディション防止) |

### 4.5 task_runner.py (187行)

| 関数 | 説明 |
|---|---|
| `@register_handler(task_type)` | ハンドラ登録デコレータ |
| `process_pending_tasks(batch_size=20)` | キュー消化 (指数バックオフ: 30s, 2m, 8m) |
| `enqueue_email(to, subject, body)` | メールタスク登録 |
| `enqueue_calendar_sync(user_id, entry_id, ...)` | Calendar同期タスク登録 |

### 4.6 notification_service.py (169行)

`_enqueue_or_send()` パターン: 非同期キュー優先、DB障害時は同期 SMTP にフォールバック。

| 関数 | トリガー |
|---|---|
| `notify_approval_requested(schedule, admin)` | 承認依頼 |
| `notify_approval_result(schedule, performer, action)` | 承認/差戻し結果 |
| `notify_invitation_created(invitation)` | メール指定招待 |
| `notify_submission_deadline(period, user)` | 提出期限リマインド |
| `notify_preshift(entry, user)` | シフト前日リマインド |
| `notify_vacancy_request(vacancy, candidate, base_url)` | 欠員補充依頼 |
| `notify_vacancy_accepted(vacancy, acceptor)` | 欠員承諾通知 |

---

## 5. ミドルウェア

### auth_middleware.py (64行)

```python
@require_auth
# 1. session['user_id'] の存在確認
# 2. User.query.get(user_id) で is_active 確認
# 3. OrganizationMember.filter_by(user_id, is_active=True).first() で組織所属確認
# 4. g.current_user = user をセット

@require_role('admin', 'owner')
# 1. @require_auth と同じチェック
# 2. user.role in allowed_roles を追加確認
```

---

## 6. フロントエンド

### 6.1 共有モジュール (static/js/modules/)

| モジュール | exports | 説明 |
|---|---|---|
| api-client.js | `api`, `getCurrentUser()`, `getCalendarEvents()`, `getCalendarList()` | fetch ラッパー。401 → 再認証モーダル |
| calendar-grid.js | `renderCalendar()` | 月間カレンダー DOM 生成 |
| shift-calculator.js | `calculateAvailableSlots()`, `calculateDetailedSlots()` | GCal イベントから空き時間計算 |
| notification.js | `showToast()` | トースト通知 |
| ui-dialogs.js | `showConfirmDialog()`, `showPromptDialog()` | モーダルダイアログ |
| btn-loading.js | `setLoading()`, `withLoading()` | ボタンローディング状態 |
| event-utils.js | `isAllDayEvent()`, `getEventsForDate()`, `formatSubmittedAt()` | イベントユーティリティ |
| time-utils.js | `timeToMinutes()`, `minutesToTime()` | HH:MM ↔ 分変換 |
| escape-html.js | `escapeHtml()` | XSS 防止 |
| date-constants.js | `WEEKDAY_NAMES` | 日本語曜日名 |

### 6.2 CSS 設計トークン (common.css)

```css
/* カラーパレット */
--color-primary-{50..900}   /* Blue (#3b82f6) */
--color-success-*            /* Green (#22c55e) */
--color-warning-*            /* Amber (#f59e0b) */
--color-danger-*             /* Red (#ef4444) */
--color-neutral-{50..900}   /* Slate */

/* サイズ */
--radius-{sm,md,lg,xl,2xl}  /* 4px..20px */
--shadow-{sm,md,lg,xl}      /* ボックスシャドウ */
```

---

## 7. セキュリティ

| 機構 | 実装 |
|---|---|
| 認証 | Google OAuth 2.0 (id_token + userinfo fallback) |
| セッション | サーバーサイド SQLAlchemy, 24時間有効, HttpOnly/SameSite/Secure |
| トークン暗号化 | Fernet (SECRET_KEY → SHA-256 → 鍵導出) |
| RBAC | @require_auth + @require_role + OrganizationMember 検証 |
| CORS | 本番: CORS_ALLOWED_ORIGINS 未設定 → same-origin only |
| CSP | default-src 'self'; script-src 'self' unpkg.com; ... |
| HSTS | 本番: max-age=31536000 |
| レート制限 | OAuth 10/min, 組織作成 5/hour, デフォルト 200/hour |
| SMTP 保護 | Subject の CR/LF/NUL 除去 |
| XSS | フロントエンド escapeHtml() + CSP |

---

## 8. デプロイ

### vercel.json

```json
{
  "rewrites": [{ "source": "/(.*)", "destination": "/api/index" }],
  "crons": [{ "path": "/api/cron/process-tasks", "schedule": "0 9 * * *" }]
}
```

### 環境変数

| 変数 | 必須 | 説明 |
|---|---|---|
| `SECRET_KEY` | 本番必須 | セッション + Fernet 暗号化鍵 |
| `DATABASE_URL` | 本番必須 | PostgreSQL 接続文字列 |
| `GOOGLE_CLIENT_ID` | Yes | OAuth クライアント ID |
| `GOOGLE_CLIENT_SECRET` | Yes | OAuth シークレット |
| `GOOGLE_REDIRECT_URI` | Yes | OAuth コールバック URI |
| `CRON_SECRET` | 推奨 | Cron エンドポイント Bearer トークン |
| `ADMIN_EMAIL` | — | ブートストラップ管理者 (カンマ区切り) |
| `OWNER_EMAIL` | — | ブートストラップ事業主 |
| `MASTER_EMAIL` | — | マスター管理者 |
| `SMTP_HOST/PORT/USER/PASS/FROM` | — | メール通知 |
| `CORS_ALLOWED_ORIGINS` | 本番推奨 | 許可オリジン |

### コールドスタート

`api/index.py` で `flask_migrate.upgrade()` を自動実行。失敗してもアプリは起動 (ログのみ)。

---

## 9. テスト

| ファイル | テスト数 | カテゴリ |
|---|---|---|
| test_auth.py | 7 | 認証 + ロール |
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

実行: `python -m pytest tests/`

---

## 10. マイグレーション履歴

| リビジョン | 内容 |
|---|---|
| 25086bfdac9f | 初期スキーマ (13テーブル) |
| dc3fa46ab193 | organization_members + invitation_tokens |
| a1b2c3d4e5f6 | async_tasks テーブル |
| b2c3d4e5f6a7 | audit_logs テーブル |
| c3d4e5f6a7b8 | Organization.invite_code カラム追加 |
| d4e5f6a7b8c9 | reminders, vacancy_requests, vacancy_candidates, shift_change_logs |

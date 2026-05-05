# 02. Worker の月次フロー（希望提出〜確定受領〜カレンダー反映）

Worker（シフトに入る人）が、毎月どのようにシステムを使うかのフロー。

## 登場する人間

- **Worker** — アルバイト・スタッフ。自分の出勤可能時間を提出し、確定したシフトを受け取る
- **Admin** — （このフローでは背景） 期間を公開し、最終的にシフトを確定する

## フローの全体像（3 ステージ）

1. **希望提出** — 公開された期間に対して、出勤可能なスロットを入力して送信
2. **待機 + 確定受領** — 確定通知を受け取り、自分のシフトを確認
3. **カレンダー反映** — Google カレンダーに自動 or 手動で同期

---

## ステージ 1: 希望提出

```mermaid
sequenceDiagram
    autonumber
    actor Worker
    participant App as worker.html / worker-app.js
    participant API as /api/worker/*
    participant DB as DB

    Worker->>App: /worker を開く
    App->>API: GET /api/worker/periods
    API->>DB: ShiftPeriod WHERE status='open' AND org
    DB-->>API: 公開中の期間 + 自分の提出状況
    API-->>App: [{id, name, deadline, submission_status}]

    App-->>Worker: 期間一覧を表示<br/>（「未提出」「提出済み」を色分け）

    Worker->>App: 期間を選択
    App->>API: GET /api/worker/periods/{id}/opening-hours
    API->>DB: OpeningHours + 例外日
    DB-->>API: 日別の営業時間
    API-->>App: 営業時間グリッド

    App->>API: GET /api/worker/periods/{id}/availability
    API->>DB: ShiftSubmission (既存あれば)
    API-->>App: 既存入力（下書きの復元）

    App-->>Worker: カレンダーグリッド表示<br/>（日付×時間のスロット選択 UI）

    Worker->>App: 出勤可能スロットを選択 + メモ入力
    Worker->>App: 「提出する」をクリック

    App->>API: POST /api/worker/periods/{id}/availability<br/>{slots: [...], notes: ...}
    API->>API: Rate limit チェック (20 req/min)
    API->>DB: create_or_update_submission()<br/>ShiftSubmission.status='submitted'<br/>ShiftSubmissionSlot を差し替え
    DB-->>API: submission
    API-->>App: 201 Created + submission JSON
    App-->>Worker: 「提出しました」トースト
```

### 主な分岐

- **期間が `status='open'` でない** → 400 `VALIDATION_ERROR`（締切後やキャンセル済み）
- **別組織の期間 ID を叩いた** → 404 `NOT_FOUND`
- **再提出** — `create_or_update_submission` は既存 submission の slots を差し替える（上書き可能）

---

## ステージ 2: 待機と確定受領

Worker が提出した後、Admin がスケジュールを組んで確定するまでの間、Worker は特にシステムを触りません。確定時は **メール通知** と **Worker アプリで表示** の 2 経路で届きます。

```mermaid
sequenceDiagram
    autonumber
    actor Worker
    participant Admin
    participant Shifree
    participant Queue as AsyncTask キュー
    participant Cron as Vercel Cron
    participant Mail as メール送信
    participant App as worker.html
    participant DB

    Admin->>Shifree: POST /api/admin/periods/{id}/schedule/confirm
    Shifree->>DB: ShiftSchedule.status = 'confirmed'<br/>ShiftScheduleEntry を一括作成
    Shifree->>Queue: notify_schedule_confirmed()<br/>→ AsyncTask (send_email) を enqueue
    Shifree-->>Admin: 確定レスポンス

    Note over Cron,Mail: ここから非同期
    Cron->>Shifree: POST /api/cron/process-tasks<br/>(日次 — Vercel Hobby)
    Shifree->>DB: pending タスクを取得
    Shifree->>Mail: send_email(worker.email, "シフト確定")
    Mail-->>Worker: 確定メール受信

    Note over Worker,App: 次にアプリを開いたとき
    Worker->>App: /worker を開く
    App->>Shifree: GET /api/worker/confirmed-shifts
    Shifree->>DB: ShiftScheduleEntry<br/>JOIN ShiftSchedule WHERE status='confirmed'<br/>WHERE user_id = self
    DB-->>Shifree: 自分の確定シフト一覧
    Shifree-->>App: [{shift_date, start, end, sync_status, ...}]
    App-->>Worker: 確定シフト表示 + 同期状態バッジ
```

### ポイント

- **通知と表示の独立性** — メールが届かなくても、アプリを開けば `/api/worker/confirmed-shifts` で確認できる。「メールを見逃したので出勤を忘れる」を防ぐ多重化。
- **Vercel Cron の制約** — Hobby プランは 1 日 1 回しか cron を回せないため、確定直後にメールが届くとは限らない（最大 24 時間遅延）。同期通知の性質としては「数時間以内に届けばよい」想定。

---

## ステージ 3: カレンダー反映

確定後、Google カレンダーへの同期は **自動（Admin 確定時に一括）** が基本。失敗した分だけ Worker が手動で救済します。

```mermaid
sequenceDiagram
    autonumber
    actor Worker
    participant App as worker-app.js
    participant API as /api/worker/*
    participant Google as Google Calendar
    participant DB

    Note over App,DB: 確定直後の自動同期で成功している分は<br/>sync_status='SYNCED' として既に反映済み

    Worker->>App: 確定シフト一覧を開く
    App->>API: GET /api/worker/confirmed-shifts
    API->>DB: entries + is_synced / can_sync / sync_status
    API-->>App: 同期状態付きシフト一覧

    App-->>Worker: ・「同期済み」(緑チェック)<br/>・「要手動同期」(黄色 + ボタン)<br/>・「Google 連携が必要」(赤 + 再ログイン案内)

    alt 単一シフトを同期
        Worker->>App: 「カレンダーに追加」クリック
        App->>API: POST /api/worker/confirmed-shifts/{id}/sync
        API->>DB: last_sync_attempt_at = now
        API->>Google: get_credentials_for_user()<br/>+ create_event()
        Google-->>API: event_id
        API->>DB: entry.calendar_event_id<br/>+ synced_at = now
        API-->>App: 更新された entry
        App-->>Worker: 「追加しました」
    else 一括同期
        Worker->>App: 「全部同期」クリック
        App->>API: POST /api/worker/confirmed-shifts/sync-all
        API->>API: Rate limit (5 req/min)
        API->>Google: credentials を 1 回取得<br/>→ 未同期 entry を順に create_event
        API-->>App: {synced, failed, results[]}
        App-->>Worker: 件数サマリー
    end
```

### 失敗時の分岐（詳細は 05-calendar-sync-recovery.md）

| エラー | HTTP | 画面表示 | 対応 |
|---|---|---|---|
| `CREDENTIALS_EXPIRED` | 401 | 「再ログインしてください」 | Worker が再ログイン |
| `NO_CREDENTIALS` | 401 | 「Google 連携未設定」 | Worker が再ログイン |
| `CALENDAR_PERMISSION_DENIED` | 500 | 「カレンダー権限が必要」 | スコープ再同意 |
| `CALENDAR_TEMPORARY_FAILURE` | 500 | 「一時的な失敗」 | 時間を置いて再試行 |

---

## ユーザー体験サマリー

| タイミング | Worker が触る場所 | Worker が目にするもの |
|---|---|---|
| 期間公開直後 | アプリ or メール | 提出依頼の通知（今後実装予定） |
| 提出中 | `/worker` の期間タブ | スロット選択 UI、既存入力の復元 |
| 提出後 | — | 提出済みラベル |
| 締切前日 | メール | `notify_submission_deadline` リマインド |
| 確定直後 | メール + `/worker` | 確定通知 + 確定シフト一覧 |
| 前日 21 時 | メール | `notify_preshift` リマインド |

## 参照

- `app/blueprints/api_worker.py:20-175` — 期間取得・提出
- `app/blueprints/api_worker.py:218-402` — 確定シフト取得 + 同期
- `app/services/shift_service.py` — `create_or_update_submission`
- `app/services/calendar_service.py` — `create_event`, `classify_calendar_error`

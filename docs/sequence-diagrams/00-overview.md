# 00. 全体俯瞰

ひと月の運営サイクルを通して、**各ロールがどのタイミングでシステムに関わるか** をひと目で掴むための俯瞰図。細部は個別図 (01-07) を参照。

## 登場する人間と役割

| アクター | 主な役割 | 触る画面 |
|---|---|---|
| **Admin** | シフト作成、メンバー管理、確定操作 | `/admin` |
| **Owner** | シフト承認（承認 ON のときのみ） | `/owner` |
| **Worker** | 希望提出、確定受領、カレンダー同期 | `/worker` |
| **招待される人** | 参加手続き | `/invite` → `/callback-landing` |
| **欠員候補** | メールリンク応答 | `/vacancy/respond`（ログイン不要） |

## サブシステム

| サブシステム | 役割 |
|---|---|
| **Flask アプリ本体** | ブラウザからのリクエストを受け付け、DB と外部 API を橋渡し |
| **PostgreSQL (prod) / SQLite (dev)** | ユーザー、組織、シフト、承認履歴、通知ログ |
| **Google OAuth 2.0** | 認証 + Calendar API のアクセストークン |
| **Google Calendar** | 確定シフトのイベント書き込み |
| **AsyncTask キュー** | 通知メールの非同期配信 |
| **Vercel Cron** | 日次トリガー（通知配信・リマインダー） |
| **SMTP** | メール配信 |

---

## ライフサイクル俯瞰（月次サイクル）

```mermaid
sequenceDiagram
    autonumber
    actor Admin
    actor Worker
    actor Owner
    actor Candidate as 欠員候補
    participant Shifree as シフリー
    participant Google as Google OAuth + Calendar
    participant Cron as Vercel Cron
    participant Mail as SMTP

    rect rgba(230, 240, 255, 0.4)
    Note over Admin,Worker: 【フェーズ1】 参加 (01-onboarding)
    Admin->>Shifree: 招待発行 (POST /api/admin/invitations)
    Shifree->>Mail: 招待メール
    Mail-->>Worker: 招待 URL
    Worker->>Google: OAuth 認可
    Google-->>Shifree: credentials
    Shifree-->>Worker: /worker へ着地
    end

    rect rgba(240, 255, 230, 0.4)
    Note over Admin,Worker: 【フェーズ2】 期間公開と希望提出 (02, 04)
    Admin->>Shifree: 期間作成 (POST /api/admin/periods)
    Worker->>Shifree: 希望提出 (POST /api/worker/.../availability)
    Note over Cron,Mail: 締切前日
    Cron->>Shifree: POST /api/cron/process-tasks
    Shifree->>Mail: 未提出 Worker にリマインド
    Mail-->>Worker: 「提出期限が近い」
    end

    rect rgba(255, 245, 220, 0.4)
    Note over Admin,Owner: 【フェーズ3】 シフト組立と承認 (03, 04)
    Admin->>Shifree: シフト作成 (POST .../schedule)<br/>ステータス=draft
    alt approval_required = ON
        Admin->>Shifree: submit → pending_approval
        Shifree->>Mail: 承認依頼
        Mail-->>Owner: メール通知
        Owner->>Shifree: approve → approved
        Shifree->>Mail: 承認完了
        Mail-->>Admin: メール通知
        Admin->>Shifree: confirm → confirmed
    else approval_required = OFF
        Admin->>Shifree: confirm (直接) → confirmed
    end
    end

    rect rgba(255, 230, 230, 0.4)
    Note over Admin,Worker: 【フェーズ4】 カレンダー反映 (05)
    Shifree->>Google: 各 Worker のカレンダーに create_event
    Google-->>Shifree: event_id（または失敗）
    Shifree-->>Admin: sync_summary
    alt 失敗した Worker の救済
        Worker->>Shifree: POST /api/worker/.../sync(-all)
        Shifree->>Google: create_event
    end
    end

    rect rgba(240, 230, 255, 0.4)
    Note over Admin,Candidate: 【フェーズ5】 欠員発生時 (06)
    Admin->>Shifree: POST /api/admin/vacancy + notify
    Shifree->>Mail: 候補者に一斉送信
    Mail-->>Candidate: 応答リンク
    Candidate->>Shifree: GET /vacancy/respond?token=...&action=accept
    Shifree->>Shifree: entry.user_id を差し替え
    Shifree->>Mail: Admin に受付完了通知
    Mail-->>Admin: 「補充されました」
    end

    rect rgba(220, 255, 240, 0.4)
    Note over Cron,Worker: 【フェーズ6】 前日リマインダー (07)
    Cron->>Shifree: POST /api/cron/process-tasks
    Shifree->>Mail: 明日シフトの Worker に通知
    Mail-->>Worker: 「明日のシフトのご確認」
    end
```

---

## アクセス経路マップ（誰がどのエンドポイントを叩くか）

```mermaid
flowchart TB
    subgraph 人間
        Admin
        Owner
        Worker
        Candidate[欠員候補<br/>ログイン不要]
        Invitee[招待される人]
    end

    subgraph 認証ミドルウェア
        RA["@require_role('admin')"]
        RO["@require_role('owner')"]
        RW["@require_role('worker')"]
        Public[認証不要]
    end

    subgraph APIブループリント
        AA[api_admin_bp<br/>/api/admin/*]
        AO[api_owner_bp<br/>/api/owner/*]
        AW[api_worker_bp<br/>/api/worker/*]
        AC[api_common_bp<br/>/ /invite /vacancy/respond]
        AUTH[auth_bp<br/>/auth/*]
        CRON[api_cron_bp<br/>/api/cron/*]
        AD[api_dashboard_bp<br/>/api/dashboard/*]
    end

    subgraph 共通サービス層
        Shift[shift_service]
        Approval[approval_service]
        Calendar[calendar_service]
        Vacancy[vacancy_service]
        Reminder[reminder_service]
        Notif[notification_service]
        TaskRun[task_runner]
    end

    subgraph 外部
        Google[Google OAuth + Calendar]
        SMTP[SMTP]
        VercelCron[Vercel Cron]
    end

    subgraph ストレージ
        DB[(PostgreSQL / SQLite)]
    end

    Admin --> RA --> AA
    Admin --> RA --> AD
    Owner --> RO --> AO
    Worker --> RW --> AW
    Candidate --> Public --> AC
    Invitee --> Public --> AUTH
    Invitee --> Public --> AC

    AA --> Shift
    AA --> Approval
    AA --> Vacancy
    AA --> Reminder
    AA --> Calendar
    AO --> Approval
    AW --> Shift
    AW --> Calendar
    AUTH --> Google
    AC --> Vacancy

    VercelCron --> CRON
    CRON --> TaskRun
    CRON --> Reminder

    Shift --> DB
    Approval --> DB
    Approval --> Notif
    Calendar --> Google
    Vacancy --> DB
    Vacancy --> Notif
    Reminder --> Notif
    Notif --> DB
    TaskRun --> SMTP
    Reminder --> DB
```

---

## 1 日の中の時間軸

実運用での典型的な 1 日の流れ。

```mermaid
gantt
    title 1 日のシステム内イベント（例: 月末前日）
    dateFormat  HH:mm
    axisFormat  %H:%M

    section 自動
    Vercel Cron 起動 (process-tasks)  :milestone, cron, 09:00, 0m
    締切前リマインダー検査 + 送信       :active, 09:00, 5m
    前日リマインダー検査 + 送信        :active, 09:05, 5m
    AsyncTask (enqueue 済み) 消化    :active, 09:00, 10m

    section Admin
    提出状況チェック                :admin1, 10:00, 15m
    シフト作成                     :admin2, after admin1, 2h
    submit (承認 ON)              :milestone, admin3, after admin2, 0m

    section Owner
    承認メール受信                  :milestone, own1, after admin3, 0m
    承認                          :own2, after own1, 20m

    section Admin 2
    confirm + Calendar 同期       :admin4, after own2, 5m
    sync_summary 確認              :admin5, after admin4, 10m

    section Worker
    確定メール受信                  :milestone, w1, after admin4, 0m
    カレンダー確認 + 必要なら手動同期    :w2, after w1, 30m
```

- Cron の実行時刻（09:00 JST）は `vercel.json` で固定。運用タイミングはこの日次イベントに合わせて組まれる想定。

---

## ロール別の「関わり方」ダイジェスト

### Worker

- 月 1 回: 希望提出（数分）
- 月 1 回: 確定を受領し、カレンダー同期が失敗していたら手動追加（数分）
- 必要時: 欠員メールに応答（1 分）
- 日次: メールを読む

### Owner（承認 ON の場合のみ）

- 月 1 回: シフト案を確認して承認（5-30 分）
- 差し戻しあれば再確認

### Admin

- 月 1 回: 期間作成、シフト組立、確定（数時間）
- 随時: メンバー管理、欠員対応、設定調整
- 日次: 通知配信の成否を軽く確認（ダッシュボード）

### 欠員候補

- 不定期: メールリンクをクリックして応答（ログイン不要）

### 招待される人

- 初回のみ: 招待 URL → Google ログイン → アプリに着地

---

## もっと詳しく知るには

| 知りたいこと | 見るべき図 |
|---|---|
| 認証と参加の仕組み | [01-onboarding.md](01-onboarding.md) |
| Worker の毎月の操作 | [02-worker-monthly-flow.md](02-worker-monthly-flow.md) |
| 承認プロセスの分岐 | [03-owner-approval.md](03-owner-approval.md) |
| Admin の運営実務 | [04-admin-operation-cycle.md](04-admin-operation-cycle.md) |
| カレンダー同期のトラブルシュート | [05-calendar-sync-recovery.md](05-calendar-sync-recovery.md) |
| 欠員募集の race condition | [06-vacancy-request.md](06-vacancy-request.md) |
| 裏で動いている Cron | [07-background-jobs.md](07-background-jobs.md) |

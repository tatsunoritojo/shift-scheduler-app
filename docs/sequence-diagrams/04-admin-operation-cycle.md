# 04. Admin のシフト運営サイクル

Admin がひと月のシフトを回すために行う一連の操作。**期間作成 → メンバー管理 → 希望集約 → シフト作成 → 確定 → 通知** の流れ。

## 登場する人間

- **Admin** — シフト作成の全体責任者
- **Worker** — 希望を提出する側（間接的）
- **Owner** — 承認 ON の場合のみ登場

## 月次サイクルの俯瞰

```mermaid
sequenceDiagram
    autonumber
    actor Admin
    participant Shifree
    participant DB
    participant Queue as AsyncTask
    participant Mail
    actor Worker
    actor Owner

    Note over Admin,DB: Step 1. 期間を作成 + 公開
    Admin->>Shifree: POST /api/admin/periods<br/>{name, start_date, end_date, submission_deadline}
    Shifree->>DB: ShiftPeriod (status='open')
    Shifree-->>Admin: created

    Note over Admin,Worker: Step 2. 希望が集まる（Worker 主体 — 02 参照）
    Worker->>Shifree: POST /api/worker/.../availability (締切まで)
    Worker->>Shifree: ...

    Note over Admin,Queue: Step 3. 締切前リマインド（自動）
    Queue->>Shifree: process-tasks で reminder_service 起動
    Shifree->>Mail: 未提出 Worker に submission_deadline メール
    Mail-->>Worker: 「提出期限が近づいています」

    Note over Admin,DB: Step 4. 提出状況を確認
    Admin->>Shifree: GET /api/admin/periods/{id}/submissions
    Shifree->>DB: ShiftSubmission + slots
    Shifree-->>Admin: 提出一覧（誰が出せる・出せない）

    Note over Admin,DB: Step 5. シフトを組み立てる
    Admin->>Shifree: POST /api/admin/periods/{id}/schedule<br/>{entries: [...], expected_version}
    Shifree->>Shifree: 楽観ロック (expected_version 照合)
    Shifree->>DB: ShiftSchedule + Entry を保存 (draft)

    alt approval_required = true
        Admin->>Shifree: POST .../schedule/submit
        Shifree->>DB: draft → pending_approval
        Shifree-->>Mail: notify_approval_requested
        Mail-->>Owner: 「承認依頼」
        Owner->>Shifree: approve (詳細 03 参照)
        Shifree-->>Mail: notify_approval_result
        Mail-->>Admin: 「承認されました」
        Admin->>Shifree: POST .../schedule/confirm
        Shifree->>DB: approved → confirmed
    else approval_required = false
        Admin->>Shifree: POST .../schedule/confirm
        Shifree->>DB: draft → confirmed (confirm_schedule_direct)
    end

    Note over Shifree,Worker: Step 6. 確定時のカレンダー同期 + 通知
    Shifree->>Shifree: _sync_schedule_to_calendar()<br/>worker ごとに credentials を取得<br/>create_event() で primary カレンダーに挿入
    Shifree->>Queue: notify_schedule_confirmed per worker
    Shifree-->>Admin: sync_summary<br/>{total, synced, needs_worker_action, failed}
    Queue-->>Mail: send_email to each worker
    Mail-->>Worker: 「シフトが確定しました」

    Note over Admin,Worker: Step 7. 前日リマインド（自動）
    Queue->>Shifree: process-tasks
    Shifree->>Mail: preshift リマインド (shift_date - 1日 21:00)
    Mail-->>Worker: 「明日のシフトのご確認を」
```

---

## メンバー管理（月次サイクルと並行して随時）

Worker の追加・ロール変更・退職処理。月次サイクル外でいつでも発生するので、独立したフローとして把握しておく。

```mermaid
sequenceDiagram
    autonumber
    actor Admin
    participant Shifree
    participant DB
    participant Mail
    actor NewMember as 新規メンバー

    rect rgba(200, 230, 255, 0.3)
    Note over Admin,DB: A. 個別招待の発行
    Admin->>Shifree: POST /api/admin/invitations<br/>{email, role}
    Shifree->>DB: InvitationToken<br/>(token = secrets.token_urlsafe(32))<br/>+ OrganizationMember 予約
    Shifree->>Mail: notify_invitation_created()
    Mail-->>NewMember: 「招待されました」+ 招待 URL
    Shifree-->>Admin: invitation JSON
    end

    rect rgba(230, 255, 220, 0.3)
    Note over Admin,DB: B. 招待コード（組織共通）
    Admin->>Shifree: GET /api/admin/invite-code
    Shifree-->>Admin: {code, enabled}
    Admin->>Shifree: PUT /api/admin/invite-code<br/>{enabled: true}
    Shifree->>DB: Organization.invite_code_enabled = true
    Admin->>Shifree: POST /api/admin/invite-code<br/>{regenerate: true}
    Shifree->>DB: 新しい code を生成
    Note over Admin,NewMember: URL または QR コードで共有<br/>(admin-app.js が qrcode-generator で生成)
    end

    rect rgba(255, 230, 230, 0.3)
    Note over Admin,DB: C. ロール変更・削除
    Admin->>Shifree: GET /api/admin/members/{id}/role-change-impact
    Shifree->>Shifree: 最後の owner か?<br/>自分自身か?<br/>pending 承認がないか?
    Shifree-->>Admin: 影響プレビュー

    Admin->>Shifree: PUT /api/admin/members/{id}/role
    Shifree->>Shifree: ガード: LAST_OWNER / SELF_ROLE_CHANGE
    Shifree->>DB: OrganizationMember.role 更新<br/>User.role も同期 (非正規化キャッシュ)
    Shifree-->>Admin: updated

    Admin->>Shifree: DELETE /api/admin/members/{id}
    Shifree->>DB: OrganizationMember.is_active = false
    Note over Shifree,DB: 削除ではなく非アクティブ化<br/>(履歴維持)
    end
```

### LAST_OWNER ガードと承認モードの関係

- 承認 ON のときは Owner が最低 1 人いないと submit できないので、**「最後の Owner を下ろす」操作はブロック**されます。
- 承認 OFF のときは Owner が 0 人でも運用が回るので、このガードは外れます。

---

## 設定の操作

Admin がカスタマイズできる主な設定（Phase A 以降で追加された項目）。

| 設定 | エンドポイント | 影響 |
|---|---|---|
| 営業時間 | `PUT /api/admin/opening-hours` | Worker の希望提出 UI のグリッド |
| 例外日（祝日・臨時休業） | `POST /api/admin/opening-hours/exceptions` | 同上 |
| 承認プロセス | `PUT /api/admin/settings/workflow` | `approval_required` ON/OFF |
| レベル制度 | `PUT /api/admin/settings/levels` | Worker に tier を付けて最低賃金計算等 |
| 重複チェック | `PUT /api/admin/settings/overlap-check` | シフト枠の重複を許すか |
| 最低出勤 | `PUT /api/admin/settings/min-attendance` | Worker ごとの週あたり最低出勤時間 |
| リマインド | `PUT /api/admin/settings/reminder` | 提出締切何日前の何時に送るか |

これらはすべて `Organization.settings_json` に JSON として格納。読み書きは `organization_settings.py` に集約されています。

---

## ダッシュボード（運用監視）

```mermaid
sequenceDiagram
    autonumber
    actor Admin
    participant Shifree
    participant DB

    Admin->>Shifree: GET /api/dashboard/overview
    Shifree->>DB: 期間別シフト状況、提出率、未同期件数
    Shifree-->>Admin: 集計データ

    Admin->>Shifree: GET /api/dashboard/tasks
    Shifree->>DB: AsyncTask (最近の成功/失敗)
    Shifree-->>Admin: 最近のタスク履歴

    Admin->>Shifree: GET /api/dashboard/task-stats
    Shifree->>DB: 集計 (per task_type, status)
    Shifree-->>Admin: 通知・同期の成否サマリー
```

通知配信や同期の失敗を Admin が気付けるよう、ダッシュボードに可視化。ユーザーがサポート問い合わせする前に気づくのが狙い。

---

## ユーザー体験サマリー

### Admin がひと月に触るもの

1. **月初**: 新しい期間を作成・公開（1 分）
2. **締切前**: 提出状況を眺める、リマインドを追加送信（3-5 分）
3. **締切後**: シフトを組む（30 分〜数時間）
4. **承認後 or 直接**: 「確定」をクリック。同期結果を確認し、要手動の Worker に声をかける（5 分）
5. **随時**: メンバーの招待・ロール変更、設定調整

## 参照

- `app/blueprints/api_admin.py` 全体
- `app/services/shift_service.py` — シフト組立ロジック
- `app/services/organization_settings.py` — 各種設定の getter/setter
- `app/blueprints/api_dashboard.py` — 運用ダッシュボード
- `docs/admin-redesign-plan.md` — Admin 画面の再設計計画

# 06. 欠員募集（Vacancy Request）

Worker が急な体調不良などで出勤できなくなったとき、**Admin が代わりの候補者を自動的に見つけてメールで募集し、最初に受けた人がそのシフトに入る** 仕組み。

## 登場する人間

- **Admin** — 欠員枠を決めて募集を開始する
- **元の Worker** — 出勤できなくなった人（オプション：自己申告の窓口は今後実装予定）
- **候補 Worker 複数人** — 希望を提出していて、その日時間が空いている人
- **新しい Worker** — 最初にメールリンクで「引き受ける」を押した人

## フロー全体

```mermaid
sequenceDiagram
    autonumber
    actor Admin
    participant Shifree
    participant DB
    participant Mail
    actor Cand1 as 候補 A
    actor Cand2 as 候補 B
    actor Cand3 as 候補 C

    Note over Admin,DB: Step 1. 候補者を見る
    Admin->>Shifree: GET /api/admin/vacancy/candidates/{entry_id}
    Shifree->>Shifree: find_candidates()<br/>・同日に availability 出してる人<br/>・元の Worker は除外<br/>・既にアサイン済みの人も除外<br/>・週あたり時間の少ない順にソート（公平性）
    Shifree->>DB: ShiftSubmissionSlot JOIN ShiftSubmission
    DB-->>Shifree: 候補リスト + 各人の週時間
    Shifree-->>Admin: [{user, weekly_hours, slot_time}]

    Note over Admin,DB: Step 2. 欠員リクエスト作成
    Admin->>Shifree: POST /api/admin/vacancy<br/>{schedule_entry_id, reason}
    Shifree->>DB: VacancyRequest (status='open')
    Shifree-->>Admin: vacancy JSON

    Note over Admin,Mail: Step 3. 通知送信
    Admin->>Shifree: POST /api/admin/vacancy/{id}/notify<br/>{candidate_user_ids: [A.id, B.id, C.id]}
    Shifree->>DB: 各候補に<br/>VacancyCandidate (status='notified')<br/>response_token = secrets.token_urlsafe(32)
    Shifree->>DB: VacancyRequest.status = 'notified'

    par 候補 A にメール
        Shifree->>Mail: notify_vacancy_request(A.email, accept_url_A, decline_url_A)
        Mail-->>Cand1: 「シフト補充のお願い」<br/>+ 受ける / 断るリンク
    and 候補 B にメール
        Shifree->>Mail: notify_vacancy_request(B.email, ...)
        Mail-->>Cand2: 同上
    and 候補 C にメール
        Shifree->>Mail: notify_vacancy_request(C.email, ...)
        Mail-->>Cand3: 同上
    end
```

---

## Step 4. 候補者が応答する（Race condition guard が活躍）

```mermaid
sequenceDiagram
    autonumber
    actor Cand1 as 候補 A
    actor Cand2 as 候補 B
    participant Browser1 as Browser A
    participant Browser2 as Browser B
    participant Shifree
    participant DB
    participant Mail
    actor Admin

    Note over Cand1,Cand2: メールが届いて、A と B がほぼ同時に「引き受ける」

    Cand1->>Browser1: accept_url_A をクリック
    Browser1->>Shifree: GET /vacancy/respond?token=A&action=accept

    Cand2->>Browser2: accept_url_B をクリック (2 秒遅れ)
    Browser2->>Shifree: GET /vacancy/respond?token=B&action=accept

    rect rgba(255, 240, 200, 0.5)
    Note over Shifree,DB: 先着 A の処理
    Shifree->>DB: VacancyCandidate (token=A) を取得
    DB-->>Shifree: candidate A (status='notified')
    Shifree->>DB: VacancyRequest の状態確認
    DB-->>Shifree: vacancy.status='notified' (まだ誰も引き受けていない)

    Shifree->>DB: candidate_A.status = 'accepted'<br/>vacancy.status = 'accepted'<br/>vacancy.accepted_by = A.id<br/>ShiftScheduleEntry.user_id を A に更新<br/>ShiftChangeLog 記録<br/>他の候補 (B, C) は status='expired' に
    Shifree->>Mail: notify_vacancy_accepted()
    Shifree-->>Browser1: 受付確認ページ「引き受けました」
    Browser1-->>Cand1: 「シフトへの出勤が確定しました」

    Mail-->>Admin: 「A さんが補充を引き受けました」
    end

    rect rgba(255, 220, 220, 0.5)
    Note over Shifree,DB: 後発 B の処理（A より 2 秒遅れ）
    Shifree->>DB: VacancyCandidate (token=B) を取得
    DB-->>Shifree: candidate B<br/>(直前で status='expired' に更新されている)
    Shifree->>Shifree: candidate.status != 'notified'<br/>→ 'already_filled' を返す
    Shifree-->>Browser2: 「すでに補充済みです」ページ
    Browser2-->>Cand2: 「他の方が先に引き受けました」
    end
```

### Race condition guard の仕組み

`respond_to_vacancy()` (`vacancy_service.py:221-`) で以下の 2 重チェック：

1. **Candidate 状態チェック** — `candidate.status in ('accepted', 'declined', 'expired')` → 既応答
2. **Vacancy 状態チェック** — `vacancy.status != 'notified'` → 誰かが先に受けた

さらに accept 処理の内部で `if vacancy.status != 'notified'` を再チェック（トランザクション内で二重 submit を防ぐ）。

**注意**: 厳密には DB ロック (SELECT FOR UPDATE) は使っていないので、本当に同時（ミリ秒レベル）の応答では競合する可能性がゼロではない。実運用では候補を 5-10 人程度に絞って通知するので、現実的には問題にならない規模を想定。

---

## 辞退 (decline)

```mermaid
sequenceDiagram
    autonumber
    actor Cand as 候補 Worker
    participant Shifree
    participant DB

    Cand->>Shifree: GET /vacancy/respond?token=X&action=decline
    Shifree->>DB: candidate.status = 'declined'<br/>+ responded_at

    Shifree->>DB: 他にまだ notified の候補がいるか確認
    alt 他にまだいる
        DB-->>Shifree: 残り > 0
        Shifree-->>Cand: 「辞退しました」ページ
        Note over Shifree: vacancy は open のまま
    else 全員辞退した
        DB-->>Shifree: 残り = 0
        Shifree->>DB: vacancy.status = 'expired'
        Shifree-->>Cand: 「辞退しました」ページ
        Note over Shifree: Admin 側に「誰も引き受け手が見つからず」通知<br/>(実装予定)
    end
```

---

## 候補抽出アルゴリズム: 公平性ソート

`find_candidates()` が返すリストは **週あたりの既アサイン時間が少ない順** に並びます。

```mermaid
flowchart LR
    A[対象シフトの日付と時間帯] --> B[その日に is_available=true で提出している Worker]
    B --> C{元の Worker?}
    C -->|Yes| X1[除外]
    C -->|No| D{既に同じ日にアサイン済?}
    D -->|Yes| X2[除外]
    D -->|No| E{is_active?}
    E -->|No| X3[除外]
    E -->|Yes| F[候補に追加]
    F --> G[_calc_weekly_hours で週時間を計算]
    G --> H[週時間 昇順でソート]
```

「普段あまりシフトに入っていない人」に優先的に声がかかる設計。ただし最終的に誰が受けるかは先着順なので、機会平等の保証というより「声かけの優先順位」として機能します。

---

## ユーザー体験サマリー

| アクター | 何をするか | 何を見るか |
|---|---|---|
| Admin | 候補リストから通知先を選び送信 | 送信件数 + 応答状況ダッシュボード |
| 元 Worker | （現状は外部連絡） | 交代が決まったら通知（実装予定） |
| 候補 Worker（受ける） | メール → リンククリック | 「引き受けました」確認画面 |
| 候補 Worker（辞退） | メール → 辞退リンク | 「辞退しました」確認画面 |
| 候補 Worker（間に合わず） | メール → リンククリック | 「すでに補充済み」案内 |

### 候補者が **ログイン不要** で応答できる

`/vacancy/respond` は公開エンドポイント。`response_token` が 32 バイトの URL-safe ランダムトークンなので、メールが漏れない限り外部から引き受けを偽装される可能性は極低。

- 利点: Worker が「ログイン面倒 → 電話で返事」を回避できる
- 注意: トークンが他人に流出すると、他人が引き受けを偽装可能 — メールセキュリティに依存

---

## 参照

- `app/services/vacancy_service.py` — `find_candidates`, `create_vacancy_request`, `send_vacancy_notifications`, `respond_to_vacancy`
- `app/blueprints/api_admin.py:1078-` — 欠員系エンドポイント
- `app/blueprints/api_common.py:201-269` — 公開 `/vacancy/respond` エンドポイント
- `app/models/vacancy.py` — `VacancyRequest`, `VacancyCandidate`, `ShiftChangeLog`

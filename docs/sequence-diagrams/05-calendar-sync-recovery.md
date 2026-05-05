# 05. カレンダー同期の失敗回復

シフト確定時、確定した各 Worker の Google カレンダーにイベントを自動挿入します。失敗したときにどう復旧するかを、**自動同期 → 自動失敗の検出 → Worker 自力復旧 → Admin 一括再同期** の流れで描きます。

## 登場する人間

- **Admin** — シフト確定を行い、全体の同期結果を監視する
- **Worker** — 自分のカレンダーに同期できていない分を自力で追加する

## 同期の 3 経路

| 経路 | 起点 | 書き込み先 | 使う認証情報 |
|---|---|---|---|
| **自動（確定時）** | Admin の confirm | 各 Worker の primary | 各 Worker の refresh_token |
| **Worker 自力** | Worker 自身のボタン | 自分の primary | 自分の refresh_token |
| **Admin 一括再試行** | Admin の手動操作 | 各 Worker の primary | 各 Worker の refresh_token |

**ポイント**: Admin の認証情報で Worker のカレンダーに書き込むことはしません。必ず Worker 本人の credentials を使う（マルチテナント・権限分離の観点）。

---

## シーケンス図: 自動同期（確定時）

```mermaid
sequenceDiagram
    autonumber
    actor Admin
    participant Shifree
    participant DB
    participant Google as Google Calendar API

    Admin->>Shifree: POST /api/admin/periods/{id}/schedule/confirm
    Shifree->>DB: ShiftSchedule.status = 'confirmed'
    Shifree->>Shifree: _sync_schedule_to_calendar(schedule)

    loop 確定 entry ごと
        Shifree->>DB: entry.last_sync_attempt_at = now

        alt 既に同期済 (calendar_event_id がある)
            Shifree-->>Shifree: skip (冪等性)
        else credentials キャッシュにない
            Shifree->>DB: get_credentials_for_user(worker)
            alt 成功
                DB-->>Shifree: credentials をキャッシュ
                Shifree->>Google: create_event()
                alt 成功
                    Google-->>Shifree: event_id
                    Shifree->>DB: entry.calendar_event_id<br/>+ synced_at<br/>+ sync_error = None
                else 失敗
                    Google-->>Shifree: HTTPError
                    Shifree->>Shifree: classify_calendar_error()
                    Shifree->>DB: entry.sync_error = CODE
                end
            else CredentialsExpiredError
                DB-->>Shifree: 例外
                Shifree->>DB: entry.sync_error = CREDENTIALS_EXPIRED<br/>needs_worker_action = true
            else その他の例外
                DB-->>Shifree: 例外
                Shifree->>DB: entry.sync_error = CREDENTIALS_UNAVAILABLE<br/>needs_worker_action = true
            end
        else credentials キャッシュ済み
            Shifree->>Google: create_event() (キャッシュ利用)
        end
    end

    Shifree-->>Admin: sync_summary<br/>{total, synced, needs_worker_action, failed}
```

### Admin 画面の表示

確定レスポンスに `sync_summary` が含まれるので、Admin アプリでは以下のサマリーカードを表示：

- ✅ 同期済み: N 件
- ⚠️ Worker の対応が必要: M 件（氏名リスト付き）
- ❌ 失敗: K 件（原因コード付き）

`needs_worker_action` のフラグが立った Worker には、Admin から個別に「再ログインしてカレンダーを追加してください」と連絡する運用。

---

## エラー分類 (classify_calendar_error)

`app/services/calendar_service.py` の `classify_calendar_error()` が例外を以下に分類：

| エラーコード | 原因 | HTTP | Worker 側の解決方法 |
|---|---|---|---|
| `CREDENTIALS_EXPIRED` | refresh_token 失効 | 401 | 再ログイン |
| `NO_CREDENTIALS` | そもそも保存されていない | 401 | 再ログイン |
| `CREDENTIALS_UNAVAILABLE` | DB から取得失敗（稀） | 500 | 再ログイン |
| `CALENDAR_PERMISSION_DENIED` | Google 側で Calendar スコープ拒否 | 500 | OAuth 同意をやり直す |
| `CALENDAR_TEMPORARY_FAILURE` | 429 / 500 / 503 | 500 | 時間を置く |
| `CALENDAR_ERROR` | その他 | 500 | サポート問い合わせ |

---

## シーケンス図: Worker 自力復旧

```mermaid
sequenceDiagram
    autonumber
    actor Worker
    participant App as worker-app.js
    participant Shifree
    participant DB
    participant Google

    Worker->>App: /worker を開く
    App->>Shifree: GET /api/worker/confirmed-shifts
    Shifree->>DB: entries WHERE user_id = self<br/>+ is_synced / can_sync / sync_status
    Shifree-->>App: entries with sync metadata

    App-->>Worker: 同期状態のバッジ表示:<br/>・SYNCED (緑)<br/>・NOT_SYNCED (黄「追加」ボタン)<br/>・ERROR_xxx (赤「再ログイン」など)

    alt シフト単位で同期
        Worker->>App: 「カレンダーに追加」クリック
        App->>Shifree: POST /api/worker/confirmed-shifts/{id}/sync
        Shifree->>DB: entry.last_sync_attempt_at = now

        alt 既に同期済み
            Shifree-->>App: {skipped: true}
        else credentials 取得成功
            Shifree->>Google: create_event('primary', ...)
            alt 成功
                Google-->>Shifree: event_id
                Shifree->>DB: entry.calendar_event_id + synced_at<br/>+ sync_error = None
                Shifree-->>App: 200 + updated entry
                App-->>Worker: 「追加しました」
            else 失敗
                Google-->>Shifree: HTTPError
                Shifree->>Shifree: classify_calendar_error()
                Shifree->>DB: entry.sync_error = CODE
                Shifree-->>App: 401 or 500 + error code
                App-->>Worker: エラーメッセージ<br/>(再ログイン案内 or 時間をおいて再試行)
            end
        else CREDENTIALS_EXPIRED
            Shifree->>DB: entry.sync_error = CREDENTIALS_EXPIRED
            Shifree-->>App: 401 CREDENTIALS_EXPIRED
            App-->>Worker: 「再ログインしてください」ボタン表示
            Worker->>Shifree: GET /auth/google/login
            Note over Worker: 再ログインして戻ってくる
            Worker->>App: もう一度「追加」をクリック
        end
    else 一括同期
        Worker->>App: 「未同期をすべて追加」
        App->>Shifree: POST /api/worker/confirmed-shifts/sync-all
        Shifree->>Shifree: Rate limit (5 req/min)
        Shifree->>DB: 未同期 entry を一括取得<br/>(calendar_event_id IS NULL)
        Shifree->>Google: credentials を 1 回取得<br/>→ 各 entry で create_event
        Shifree->>DB: 各 entry に結果を反映
        Shifree-->>App: {synced, failed, skipped, results[]}
        App-->>Worker: 件数サマリー + 失敗理由
    end
```

### Worker から見える同期状態（`get_sync_status()` の返り値）

`ShiftScheduleEntry` モデルに実装された派生プロパティ：

- `SYNCED` — `calendar_event_id` あり、エラーなし
- `NOT_SYNCED` — `calendar_event_id` なし、エラーなし（未試行）
- `ERROR_CREDENTIALS_EXPIRED` / `ERROR_NO_CREDENTIALS` — 再ログイン必要
- `ERROR_TEMPORARY` — 一時的失敗（リトライ）
- `ERROR_OTHER` — その他

UI は状態ごとに色とアクションを分けて表示（02-worker-monthly-flow.md の Stage 3 参照）。

---

## シーケンス図: Admin 一括再同期

Admin が「失敗している分を再試行したい」ときのエンドポイントは実装上は **shift-schedule の confirm の再呼び出し** で代替できます（冪等性ガードで成功済は skip される）。

```mermaid
sequenceDiagram
    autonumber
    actor Admin
    participant Shifree
    participant DB
    participant Google

    Admin->>Shifree: GET /api/admin/periods/{id}/schedule
    Shifree->>DB: schedule + entries (with sync_status)
    Shifree-->>Admin: sync_summary カード表示

    Note over Admin: 失敗数を見て再試行を判断

    Admin->>Shifree: POST /api/admin/periods/{id}/schedule/confirm
    Shifree->>Shifree: 既に confirmed だが再度 _sync_schedule_to_calendar<br/>(calendar_event_id がある entry は skip される)
    Shifree->>Google: 失敗していた分だけ create_event
    Shifree-->>Admin: 更新された sync_summary

    alt それでも失敗
        Note over Admin: Worker 側の対応が必要<br/>→ 該当 Worker にメッセージを送る
    end
```

**現状の実装の注意点**: 失敗分のみを再同期する専用エンドポイントはなく、confirm を再呼び出しで代替しています。冪等性は `calendar_event_id` の存在でガードされるので安全ですが、UX 上「同期だけ再試行」ボタンを別途切り出すのが改善余地です（未実装）。

---

## LinkedCalendarAccount（読み取り専用の別アカウント連携）

Worker が **別の Google アカウントのカレンダーを参照用に追加** できる機能。書き込みは primary アカウントのみで、連携アカウントは読み取りのみ。

```mermaid
sequenceDiagram
    autonumber
    actor Worker
    participant App as worker.html
    participant Shifree
    participant Google

    Worker->>App: 「参照用カレンダーを追加」
    App->>Shifree: GET /auth/google/link-calendar
    Shifree->>Google: OAuth (readonly スコープ)<br/>redirect_uri = /auth/google/callback-link
    Google-->>Shifree: callback + credentials

    Shifree->>Shifree: 同じアカウントでないこと確認<br/>(google_id != user.google_id)
    Shifree->>Shifree: refresh_token 必須
    Shifree->>DB: save_linked_calendar_token()<br/>LinkedCalendarAccount 作成
    Shifree-->>Worker: /worker?link_success=1

    Note over Worker: 以降、希望提出 UI で<br/>「本業のカレンダーの予定」を<br/>参考表示できる
```

## 参照

- `app/services/calendar_service.py` — `create_event`, `classify_calendar_error`
- `app/blueprints/api_worker.py:218-402` — `/confirmed-shifts`, `/sync`, `/sync-all`
- `app/blueprints/api_admin.py:647-` — `_sync_schedule_to_calendar`
- `app/models/shift.py` — `ShiftScheduleEntry.is_synced`, `can_sync`, `get_sync_status`
- `app/blueprints/auth.py:369-453` — `link_calendar`, `callback_link`
- `app/models/user.py` — `LinkedCalendarAccount`

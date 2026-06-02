# OAuth Verification Submission 準備書

作成日: 2026-06-02
ステータス: 調査・設計完了 / 提出前

---

## 1. 公式情報から見た Verification 要件

出典:
- [Sensitive scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification)
- [Verification requirements](https://support.google.com/cloud/answer/13464321)
- [Demo Video requirements](https://support.google.com/cloud/answer/13804565)
- [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy)
- [Choose Google Calendar API scopes](https://developers.google.com/workspace/calendar/api/auth)

### Sensitive scope verification の必須提出物

| 項目 | 要件 |
|---|---|
| **Homepage** | 公開アクセス可能、アプリ説明、Privacy Policy リンク、検証済みドメイン上 |
| **Privacy Policy** | Homepage と同一ドメイン、consent screen にもリンク設定、Google ユーザーデータの扱いを明記 |
| **Terms of Service** | 推奨（必須ではない） |
| **Logo** | JPEG/PNG/BMP、1MB以下、ブランド一意識別 |
| **Demo Video** | YouTube Unlisted、英語 consent screen、各 scope の使用デモ |
| **Scope Justification** | 各 sensitive scope について「なぜ必要か」「より狭い scope では不十分な理由」 |
| **Domain Verification** | Google Search Console で所有権検証済み |
| **Contact Email** | Google からの通知を受信可能 |

### 審査プロセス

- Sensitive scope: **3-5 営業日**（restricted は数週間 + CASA セキュリティ評価）
- Calendar scopes はすべて **sensitive**（restricted ではない） → CASA 不要、年次再検証不要
- Unverified（In production だが verification 未完了）: **100 ユーザー上限**
- 審査通過後: 未確認アプリ警告が消える

### Limited Use 要件（全 sensitive scope に適用）

1. データは「ユーザー向け機能の提供/改善」にのみ使用
2. 広告・データブローカー・信用判定への転送禁止
3. 人によるデータ閲覧は明示同意/セキュリティ/法令のみ
4. 第三者転送は明示同意がある場合のみ

---

## 2. 現在の Shifree 設定の充足状況

| 項目 | 状態 | 補足 |
|---|---|---|
| Publishing status | In production | 2026-06-02 変更済み |
| Homepage | `/lp` が公開 | Privacy Policy リンクあり（`landing.html:884`） |
| Privacy Policy | `/privacy` が公開 | Google User Data Policy 準拠を明記（Section 4） |
| Terms of Service | `/terms` が公開 | Google Calendar 連携記載あり（Section 6） |
| Logo | `static/icons/icon-192.png`, `icon-512.png` 存在 | consent screen に設定済みか要確認 |
| Demo Video | **未作成** | |
| Scope Justification | **未作成** | |
| Domain Verification | **要確認** | `shifree.com` が Search Console で検証済みか |
| Contact Email | `tatsunoritojo@gmail.com` | |
| Authorized Domains | `shifree.com` + `shifree.vercel.app` + `www.googleapis.com` | `www.googleapis.com` が残存 |
| Redirect URIs | `shifree.com/auth/google/callback` + `shifree.com/auth/google/callback-link` + `shifree.vercel.app` 版 | 旧ドメイン残存 |
| Client Secrets | 2本存在 | 整理の要否を後述 |

---

## 3. Scope Inventory

### 3.1 Sensitive Scopes（verification 対象）

#### `calendar.events` (sensitive)

| 項目 | 内容 |
|---|---|
| **分類** | Sensitive |
| **consent 表示** | "View and edit events on all your calendars" |
| **コード上の使用箇所** | |
| - `events().insert()` | `calendar_service.py:73` / `api_worker.py:300,378` / `api_admin.py:918` / `opening_hours_sync_service.py:73` / `task_runner.py:68` / `vacancy_service.py:370` |
| - `events().update()` | `calendar_service.py:89` / `opening_hours_sync_service.py:85` |
| - `events().delete()` | `calendar_service.py:98` / `opening_hours_sync_service.py:99` / `shift_service.py:350` / `vacancy_service.py:360` |
| **対応するユーザー機能** | (1) Worker: 確定シフトを個人 Calendar に同期 (2) Admin: 営業時間を Calendar に書き出し (3) System: 欠員補充時の Calendar 更新 (4) System: 非同期タスクによる Calendar 書き込み |
| **なぜ必要か** | 確定シフト・営業時間を Google Calendar に書き込む機能はアプリのコア価値。Calendar 上でシフトを直接確認できることが、紙や別ツールを不要にする |
| **より狭い scope で代替できるか** | 不可。`calendar.events.readonly` では書き込み不可 |
| **verification 時の説明方針** | 「確定シフトと営業時間を Calendar に create/update/delete する。ユーザーの明示的操作（sync ボタン押下）でのみ実行」 |
| **デモで見せるべき操作** | Worker が確定シフトを sync → Calendar にイベント出現 / Admin が営業時間を Calendar に書き出し |

#### `calendar.events.readonly` (sensitive) — 削除対象

> **ステータス: 削除対象。** Shifree が現在使用している読み取り系 API メソッドにおいて、`calendar.events.readonly` が必要な箇所はなく、`calendar.readonly` で代替可能である。`app/config.py` から削除済み。GCC Data Access からの除去はデプロイ・E2E 確認後に実施する。

| 項目 | 内容 |
|---|---|
| **分類** | Sensitive |
| **consent 表示** | "View events on all your calendars" |
| **コード上の使用箇所** | |
| - `events().list()` | `calendar_service.py:24` / `api_calendar.py:57` / `api_worker.py:130` / `opening_hours_sync_service.py:134` |
| **対応するユーザー機能** | (1) Worker: シフト希望入力時に既存予定を表示（空き時間可視化） (2) Admin: シフト構築画面で Calendar イベントを参照 (3) System: 営業時間の Calendar → アプリ同期 |
| **なぜ必要か** | 上記機能は `calendar.readonly` でも認可される。`calendar.events.readonly` は冗長 |
| **より狭い scope で代替できるか** | `calendar.readonly` で代替可能（`events().list()` は両 scope で認可される） |
| **verification 時の説明方針** | 削除するため不要 |
| **デモで見せるべき操作** | 削除するため不要 |

#### `calendar.readonly` (sensitive)

| 項目 | 内容 |
|---|---|
| **分類** | Sensitive |
| **consent 表示** | "See and download any calendar you can access using Google Calendar" |
| **コード上の使用箇所** | |
| - `calendarList().list()` | `calendar_service.py:46` / `api_worker.py:68,86` / `api_admin.py:1463` |
| **対応するユーザー機能** | (1) Worker: カレンダー一覧表示（primary + linked）でどのカレンダーの予定を見るか選択 (2) Admin: シフト構築画面でカレンダー選択 (3) Linked Calendar: 参照用の別アカウントカレンダー一覧取得 |
| **なぜ必要か** | `calendarList().list()` API は `calendar.events.readonly` では呼べない。ユーザーが複数カレンダーを持つ場合、どのカレンダーを参照するか選ぶ必要がある |
| **より狭い scope で代替できるか** | **可能性あり**: `calendar.calendarlist.readonly` でカレンダー一覧だけ取得可能。ただしこれは非 sensitive scope かどうか要確認 |
| **verification 時の説明方針** | 「ユーザーのカレンダー一覧を取得し、どのカレンダーを参照するか選択肢を提示する」 |
| **デモで見せるべき操作** | Worker の Calendar 連携画面でカレンダー一覧が表示される様子 |

### 3.2 Non-sensitive Scopes（参考）

| Scope | 用途 | 使用箇所 |
|---|---|---|
| `openid` | OAuth 認証基盤 | `config.py:23,30` |
| `userinfo.email` | メールアドレス取得 | `config.py:24,31` / `auth_service.py:69-72` |
| `userinfo.profile` | 表示名取得 | `config.py:25,32` / `auth_service.py:69-72` |

### 3.3 Scope 冗長性分析

**`calendar.readonly` と `calendar.events.readonly` の関係:**

Google Calendar API の scope 階層:
- `calendar.readonly` は `calendarList().list()` + `events().list()` + `freebusy.query()` を認可
- `calendar.events.readonly` は `events().list()` のみ認可
- Shifree が現在使用している読み取り系 API メソッド（`events().list()` + `calendarList().list()`）において、`calendar.events.readonly` が必要な箇所はなく、`calendar.readonly` で代替可能
- なお `freebusy.query()` は Shifree では現在未使用（Worker の空き時間計算はフロントエンドの `shift-calculator.js:calculateAvailableSlots` で `events().list()` の結果から算出）

**結論**: Shifree が使用中の読み取り系 API に限れば、`calendar.events.readonly` は冗長。`calendar.readonly` だけで `events().list()` も `calendarList().list()` もカバーできる。

**推奨 scope 構成（削減後）:**

```python
GOOGLE_SCOPES_READONLY = [
    'openid',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/calendar.readonly',
    # calendar.events.readonly を削除（calendar.readonly で包含）
]
GOOGLE_SCOPES_WRITE = [
    'openid',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/calendar.readonly',
    # calendar.events.readonly を削除（calendar.readonly で包含）
    'https://www.googleapis.com/auth/calendar.events',
]
```

**利点:**
- sensitive scope が 3 → 2 に減少（審査通過率向上）
- 各 scope の必要性説明が明確になる（冗長 scope の正当化が不要）
- consent screen の scope 表示が減り、ユーザーの心理的抵抗が下がる

**リスク:**
- 既存ユーザーの token に `calendar.events.readonly` が付与済み → 削除しても既存 token は引き続き動作（scope は token 発行時に固定）
- Google Auth Platform の Data Access から scope を除去する操作が必要

---

## 4. Scope Justification 下書き（英語）

### For `calendar.readonly`

> **Scope:** `https://www.googleapis.com/auth/calendar.readonly`
>
> **Why this scope is needed:**
> Shifree is a shift scheduling app that integrates with Google Calendar. This scope is required for two core features:
>
> 1. **Calendar list retrieval** (`calendarList.list`): When workers view their shift submission form, the app displays a list of their Google Calendars so they can select which calendar's events to overlay on the scheduling grid. This helps workers identify time conflicts between their existing commitments and available shift slots. Admin users also use this to select which calendar contains business hours.
>
> 2. **Event reading** (`events.list`): The app reads calendar events within a specific date range to display them alongside shift slots. Workers see their personal appointments overlaid on the shift grid, enabling informed shift preference submissions. The app also reads business-hours events from the admin's calendar to auto-populate operating schedules.
>
> **Why a narrower scope is insufficient:**
> `calendar.events.readonly` only grants access to `events.list` but not `calendarList.list`. Without `calendarList.list`, users cannot select which of their multiple calendars to reference, making the overlay feature non-functional for users with more than one calendar.
>
> **Note on FreeBusy API:**
> While `calendar.readonly` also authorizes the `freebusy.query` API, Shifree does not currently use this endpoint. Worker availability is calculated client-side from `events.list` results. This scope is requested solely for `calendarList.list` and `events.list`.
>
> **Data handling:**
> - Calendar events are read in real-time and displayed in the browser. Event data is NOT stored in our database.
> - Only event metadata (title, start/end time) is used for display. Event descriptions, attendees, and attachments are not processed.
> - No calendar data is shared with third parties, used for advertising, or used for AI/ML training.
> - Users can revoke access at any time via Google Account permissions (myaccount.google.com/permissions).

### For `calendar.events`

> **Scope:** `https://www.googleapis.com/auth/calendar.events`
>
> **Why this scope is needed:**
> This scope enables the core value proposition of Shifree: confirmed shift schedules appear directly in workers' Google Calendars, eliminating the need for separate schedule-checking tools.
>
> Three specific write operations require this scope:
>
> 1. **Confirmed shift sync** (`events.insert`): When a shift schedule is finalized, workers can sync their confirmed shifts to their primary Google Calendar with a single tap. Each shift creates a calendar event with the shift date, start/end time, and a "Created by Shifree" description.
>
> 2. **Business hours export** (`events.insert`, `events.update`, `events.delete`): Admins can export business operating hours to Google Calendar. When hours change, existing events are updated; when a day is closed, the corresponding event is deleted.
>
> 3. **Vacancy replacement** (`events.delete`, `events.insert`): When a shift is reassigned due to a vacancy, the original worker's calendar event is removed and a new event is created for the replacement worker.
>
> **Why a narrower scope is insufficient:**
> `calendar.events.readonly` does not permit create, update, or delete operations. There is no scope that allows only insert without update/delete — `calendar.events` is the minimum write scope available for the Calendar Events API.
>
> **Data handling:**
> - Calendar events are created ONLY when the user explicitly triggers sync (button press). No background or automatic calendar writes occur without user action.
> - Events contain only: shift summary, date/time, and "Created by Shifree" description. No sensitive business data is written to calendars.
> - Users can delete synced events directly from Google Calendar at any time.
> - All calendar writes use the user's own credentials — Shifree never writes to calendars using another user's credentials.

---

## 5. Demo Video Scenario

### 概要

- 所要時間: 3-5 分
- 言語: 英語字幕 + 英語ナレーション
- 撮影環境: Chrome ブラウザ、`https://shifree.com` 本番環境
- consent screen 言語: **English に切替**（審査要件）

### シーン構成

**Scene 1: Introduction (0:00-0:20)**
> Narration: "This is Shifree, a shift scheduling app for small businesses. Shifree integrates with Google Calendar to help teams manage shift schedules. Let me walk you through how we use each requested Google Calendar scope."

- 画面: `https://shifree.com/lp` を表示
- LP のフッターにある Privacy Policy リンクを指し示す

**Scene 2: OAuth Login + Consent Screen (0:20-0:50)**

> 注: 以下は scope 削減後（sensitive scope 2件: `calendar.readonly` + `calendar.events`）を前提としたシナリオ。撮影は scope 削減デプロイ + GCC Data Access 更新後に行う。

> Narration: "When a user signs in, they authenticate with Google OAuth. Here's the consent screen showing the two Calendar scopes we request: calendar.readonly for viewing calendars and events, and calendar.events for writing confirmed shifts to the calendar."

- `https://shifree.com/login` → "Google でログイン" をクリック
- Google consent screen が表示される（**英語表示**）
- ブラウザのアドレスバーに OAuth client ID が見えることを確認
- 要求される scope を1つずつハイライト（sensitive scope 2件のみであることを見せる）
- "Allow" をクリック

**Scene 3: Calendar List — `calendar.readonly` (0:50-1:30)**
> Narration: "The calendar.readonly scope enables us to list the user's calendars. Here, a worker sees their available calendars and can select which one to overlay on the shift grid. This requires the calendarList.list API, which needs calendar.readonly."

- Worker 画面でカレンダー選択ドロップダウンを表示
- 複数カレンダーが一覧されている様子
- Linked Calendar（別アカウント）の追加操作も見せる

**Scene 4: Event Reading — `calendar.readonly` (1:30-2:10)**
> Narration: "The same scope also allows reading calendar events. When a worker fills in their shift preferences, existing Google Calendar events are displayed on the scheduling grid. This overlay helps workers avoid double-booking by seeing their personal commitments alongside available shift slots."

- Worker のシフト希望入力画面を表示
- Calendar イベントがグリッド上にオーバーレイされている様子
- 「この時間は既存予定があるので別の時間を選ぶ」操作を実演

**Scene 5: Confirmed Shift Sync — `calendar.events` (2:10-3:00)**
> Narration: "The calendar.events scope is used to write confirmed shifts to the worker's Google Calendar. After the admin finalizes the schedule, the worker taps 'Sync to Calendar' and their shifts appear as calendar events. This is the core feature that eliminates the need for workers to manually copy their schedule."

- Worker の確定シフト一覧画面を表示
- "カレンダーに同期" ボタンをクリック
- 同期成功メッセージ
- Google Calendar を別タブで開き、シフトイベントが作成されたことを確認

**Scene 6: Business Hours Export — `calendar.events` (3:00-3:30)**
> Narration: "Admins can also export business operating hours to Google Calendar. When hours change, events are updated; when a day is closed, the event is removed. This keeps the business calendar in sync with the scheduling system."

- Admin の営業時間設定画面
- Calendar への書き出し操作
- Calendar 上にイベントが反映される様子

**Scene 7: Privacy & Account Management (3:30-4:00)**
> Narration: "Our Privacy Policy, accessible from the homepage, describes how we handle Google user data in compliance with Google's API Services User Data Policy including Limited Use requirements. Users can revoke access at any time through Google Account permissions."

- `/lp` フッターの Privacy Policy リンクをクリック
- Privacy Policy ページの Section 4 "Google ユーザーデータの取り扱い" をスクロール表示
- `/terms` リンクも見せる

**Scene 8: Closing (4:00-4:15)**
> Narration: "Shifree requests only the minimum scopes needed: calendar.readonly for reading calendars and events, and calendar.events for writing confirmed shifts. No data is shared with third parties or used for advertising."

### 撮影前の準備事項

1. **consent screen 言語を English に切替** — GCC > OAuth consent screen > App information
2. テスト用の Worker アカウントにカレンダー予定を数件入れておく
3. 確定シフトが存在する期間を用意しておく（sync デモ用）
4. 営業時間が設定済みの組織を用意（export デモ用）
5. Chrome の言語設定を English に（アドレスバー等の表示統一）

---

## 6. Verification Submission Checklist

### 必須項目

- [ ] **App Name**: `shifree` — consent screen と LP で一致
- [ ] **Logo**: consent screen に設定済みか確認。`static/icons/icon-512.png` を使用可能（PNG、1MB 以下）
- [ ] **Homepage URL**: `https://shifree.com/lp` — 公開アクセス可能、アプリ説明あり、Privacy Policy リンクあり
- [ ] **Privacy Policy URL**: `https://shifree.com/privacy` — Section 4 で Google User Data 取り扱い明記、Limited Use 準拠を宣言
- [ ] **Terms of Service URL**: `https://shifree.com/terms` — Section 6 で Google Calendar 連携記載
- [ ] **Authorized Domains**: `shifree.com` が含まれている
- [ ] **Domain Verification**: `shifree.com` が Google Search Console で所有権検証済み
- [ ] **Data Access Scopes**: 提出する scope と実際にコードでリクエストする scope が一致
- [ ] **Demo Video**: YouTube Unlisted でアップロード済み、アクセス可能
- [ ] **Scope Justification**: 各 sensitive scope について記入
- [ ] **Contact Email**: `tatsunoritojo@gmail.com` — Cloud Console IAM に設定済み
- [ ] **OAuth Client ID**: Redirect URI が `https://shifree.com/auth/google/callback` + `/callback-link`
- [ ] **Publishing Status**: In production
- [ ] **Restricted Scopes**: なし（Calendar scopes はすべて sensitive）

### 事前整理項目

- [ ] **`calendar.events.readonly` を scope から削除** — 冗長（`calendar.readonly` で包含）
- [ ] **`www.googleapis.com` を Authorized Domains から除去** — 由来不明、審査で指摘される可能性
- [ ] **Client Secret 2 本の整理** — 使用中の1本を特定し、未使用を削除
- [ ] **`shifree.vercel.app` の Redirect URI / Authorized Domains の扱いを決定**
- [ ] **consent screen の Logo 設定を確認** — 未設定なら icon-512.png を登録
- [ ] **consent screen 言語を English に切替可能か確認**（デモ動画撮影用）
- [ ] **Google Search Console でドメイン所有権を確認**（未検証なら Cloudflare DNS で TXT レコード追加）
- [ ] **Google Auth Platform の Data Access から `calendar.events.readonly` を除去**

### 提出後の確認

- [ ] 審査ステータスの監視（3-5 営業日）
- [ ] 却下時の修正対応準備
- [ ] 承認後: 未確認アプリ警告が消えたことを確認
- [ ] 承認後: OAuth user cap 100 の制限が解除されたことを確認

---

## 7. 不足・リスク・修正候補

### 7.1 `www.googleapis.com` が Authorized Domains に残っている件

**推奨: 提出前に除去**

- 由来不明（おそらく GCC 初期設定時の自動追加または誤操作）
- Shifree のドメインではないため、審査官に「なぜ Google のドメインが含まれるのか」と疑問を持たれる可能性
- OAuth redirect や homepage には無関係
- 除去しても機能に影響なし

### 7.2 `shifree.vercel.app` を残したまま verification に出してよいか

**推奨: 残したまま提出可能。ただし justification で触れない**

- Redirect URI に `shifree.vercel.app` 版が残っているのは、Preview/Development 環境用
- 本番は `shifree.com` に統一済み（domain redirect で強制）
- 審査官は consent screen の設定と提出内容の一致を見る。`shifree.vercel.app` が Authorized Domains に残っていても、homepage/privacy が `shifree.com` であれば問題にならない
- ただし、verification 完了後に整理することを推奨

### 7.3 Client Secret が 2 本ある件

**推奨: 提出前に使用中の 1 本を特定し、未使用を削除**

- 2 本の Client Secret は審査に直接影響しないが、セキュリティ衛生上整理すべき
- Vercel env に設定されている `GOOGLE_CLIENT_SECRET` と一致する方が使用中
- 未使用の Secret を削除しても、使用中の Secret には影響なし
- **注意**: 削除前に Vercel env の値と照合すること（誤って使用中を消すと本番障害）

### 7.4 `calendar.readonly` と `calendar.events.readonly` の両方が必要か

**結論: `calendar.events.readonly` は不要（削除済み）**

Shifree が現在使用している読み取り系 API メソッドにおいて、`calendar.events.readonly` が必要な箇所はなく、`calendar.readonly` で代替可能である。

分析（Section 3.3 参照）:
- `calendar.readonly` は `calendarList().list()` + `events().list()` を認可
- `calendar.events.readonly` は `events().list()` のみ認可
- Shifree が使う読み取り API（`calendarList().list()` + `events().list()`）はすべて `calendar.readonly` でカバー可能
- 冗長な scope を残すと、審査官に「なぜ両方必要か」の説明が求められ、却下リスクが上がる
- `app/config.py` からは削除済み。GCC Data Access からの除去はデプロイ・E2E 確認後に実施する

### 7.5 `calendar.events` は最小権限として妥当か

**妥当**

- `calendar.events` は Calendar Events API の書き込み（insert/update/delete）に必要な最小 scope
- insert のみ（update/delete 不要）の scope は Google Calendar API に存在しない
- Shifree は実際に insert/update/delete すべてを使用している（確定シフト sync、営業時間 export、欠員補充）
- これ以上狭い scope は存在しない

### 7.6 Privacy Policy の十分性

**概ね十分だが、以下の補強を推奨:**

現在の記載（`privacy.html` Section 4）:
- Google API Services User Data Policy 準拠 + Limited Use 準拠を明記 ... OK
- 広告不使用、第三者販売なし、AI/ML 不使用 ... OK
- データ暗号化、refresh token 暗号化保管 ... OK
- データ削除手段（組織脱退、アカウント削除要求、Google 権限取消） ... OK

**不足している可能性がある点（優先度順）:**
1. **[高] 英語版がない** — 審査官が日本語を読めない場合に不利。少なくとも Section 4（Google ユーザーデータの取り扱い）の英語版を併設すべき。審査通過に最も直結する
2. **[中] 具体的な scope の列挙がない** — 「カレンダーの予定の読み取り」「書き込み」とあるが、具体的な scope 名（`calendar.readonly`, `calendar.events`）を明記したほうが審査官にわかりやすい
3. **[中] データ保持期間の明記がない** — Calendar イベントデータはリアルタイム表示のみで保存しない旨を明記すべき
4. **[低] Linked Calendar（別アカウント連携）への言及がない** — Section 1.2 で触れていない。ただし linked calendar は同じ scope（`calendar.readonly`）を使うため、審査上のリスクは低い

### 7.7 Terms of Service の十分性

**十分**（Terms は推奨であり必須ではない。Section 6 で Calendar 連携に言及済み）

### 7.8 LP が reviewer にアプリ用途を説明できるか

**日本語のみのため、審査官が理解できない可能性**

- LP (`landing.html`) は全文日本語
- 審査官はアプリの目的を理解する必要がある
- 対策案:
  - LP に英語セクションを追加（推奨）
  - または Demo Video のナレーションで十分に説明する（最低ライン）

### 7.9 テストアカウントの要否

**Sensitive scope では不要**（審査はデモ動画のみで実施）

- テストアカウント提供は Restricted scope の CASA 評価で必要
- Calendar scopes は sensitive → テストアカウント不要
- ただし、デモ動画で実際の操作を見せる必要がある

---

## 8. 今すぐ提出してよいか

**いいえ。以下を先に実施すべき。**

必須:
1. `calendar.events.readonly` の scope 削除（コード変更 + GCC Data Access 更新）
2. Demo Video の撮影・アップロード
3. Scope Justification の最終版作成
4. Google Search Console での `shifree.com` ドメイン所有権検証（未確認の場合）

推奨:
5. `www.googleapis.com` を Authorized Domains から除去
6. Client Secret の整理（未使用の 1 本を削除）
7. Privacy Policy に scope 名の明記 + データ保持期間 + Linked Calendar 言及 + 英語サマリー追加
8. consent screen に Logo を設定（未設定の場合）

---

## 9. 提出前に実施すべき次アクション（優先順）

### Phase 1: scope 削減（コード変更 + 検証） — 実施済み

1. ~~`app/config.py` から `calendar.events.readonly` を削除~~ — 完了
2. ~~`app_v1_legacy.py` からも同 scope を削除~~ — 完了
3. ~~`pytest` で回帰テスト~~ — 403 テスト全 pass
4. 本番デプロイ後、既存ユーザーの Calendar 機能が動作することを確認（E2E）
5. Google Auth Platform の Data Access から `calendar.events.readonly` を除去（E2E 確認後）

### Phase 2: 提出物準備

6. **Domain Verification**: Google Search Console で `shifree.com` のドメイン所有権を確認。未検証なら Cloudflare DNS で TXT レコード追加。verification submission の必須条件
7. consent screen に Logo を設定（未設定の場合）
8. Privacy Policy 補強（優先度順: 英語サマリー > scope 名明記 > データ保持期間 > Linked Calendar 言及）
9. Demo Video 撮影・YouTube Unlisted アップロード（scope 削減デプロイ + GCC Data Access 更新後に撮影）
10. Scope Justification 最終版を用意

### Phase 3: GCC 整理

10. `www.googleapis.com` を Authorized Domains から除去
11. Client Secret の整理（Vercel env と照合して未使用を削除）

### Phase 4: 提出

12. Cloud Console Verification Center から Submit
13. 審査ステータス監視（3-5 営業日）

### 並行: 経過観察

- 2026-06-09: refresh token 失効チェック（user_id=5）
- Phase 1 の scope 削減デプロイ後にも Calendar sync 動作確認

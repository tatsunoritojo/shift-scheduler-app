# 01. オンボーディング（新規メンバーの参加）

新規ユーザーが組織に参加するまでのフロー。招待方法は **4 経路** あり、どれを通るかでロールと所属が決まります。

## 登場する人間

- **招待者（Admin）** — 招待 URL/コードを発行する人
- **新規ユーザー** — これから参加する Worker / Owner / Admin
- **Bootstrap 管理者** — 環境変数 (`ADMIN_EMAIL` / `OWNER_EMAIL`) で設定される初期管理者（初期セットアップ時のみ）

## 4 つの参加経路

| 経路 | 発行方法 | 想定ロール | URL |
|---|---|---|---|
| **A. 個別招待トークン** | Admin が `POST /api/admin/invitations` で発行 | worker/owner/admin 任意 | `/invite?token=...` |
| **B. 組織招待コード** | 組織に固定の共有コード | worker 固定 | `/invite?code=...` |
| **C. 環境変数 Bootstrap** | デプロイ時に `ADMIN_EMAIL` / `OWNER_EMAIL` を設定 | admin / owner | ログイン時に自動判定 |
| **D. 未所属ログイン** | どの招待経路にも該当しない | 所属なし | `/no-organization` へ |

---

## シーケンス図（経路 A + B）: 招待リンク経由

```mermaid
sequenceDiagram
    autonumber
    actor Inviter as 招待者 (Admin)
    actor NewUser as 新規ユーザー
    participant Browser as ブラウザ
    participant Shifree as シフリー (Flask)
    participant Google as Google OAuth
    participant DB as DB

    Note over Inviter,Shifree: 【事前】招待を発行
    Inviter->>Shifree: POST /api/admin/invitations<br/>(email, role) または invite_code
    Shifree->>DB: InvitationToken / Organization.invite_code 保存
    Shifree-->>Inviter: 招待 URL を表示

    Inviter-->>NewUser: 招待 URL をメール/チャットで共有

    NewUser->>Browser: 招待 URL をクリック
    Browser->>Shifree: GET /invite?token=... or ?code=...
    Shifree-->>Browser: invite.html (組織名・ロール表示)
    Browser->>Shifree: GET /api/invite/info?token=...
    Shifree->>DB: InvitationToken / Organization を検索
    Shifree-->>Browser: {organization_name, role, login_url}

    NewUser->>Browser: 「Google でログイン」をクリック
    Browser->>Shifree: GET /auth/invite/<token><br/>(or /auth/invite/code/<code>)
    Shifree->>Shifree: トークン/コードを署名 Cookie に保存<br/>(itsdangerous, HttpOnly, 10min)
    Shifree-->>Browser: 302 → /auth/google/login?invite_token=...

    Browser->>Shifree: GET /auth/google/login
    Shifree->>Shifree: session['state'] + session['invitation_token'] 保存
    Shifree-->>Browser: 302 → Google 認可画面

    Browser->>Google: 認可要求
    NewUser->>Google: アカウント選択 + 許可
    Google-->>Browser: 302 → /auth/google/callback?code=...&state=...

    Browser->>Shifree: GET /auth/google/callback
    Shifree->>Shifree: state 照合 (hmac.compare_digest)
    Shifree->>Google: トークン交換 (fetch_token)
    Google-->>Shifree: access_token + refresh_token + id_token

    Shifree->>Shifree: _resolve_invitation() / _resolve_invite_code()<br/>Cookie → session フォールバックで検証
    Shifree->>DB: upsert_user() — User 作成/更新<br/>OrganizationMember 発行<br/>role を招待情報から決定
    Shifree->>DB: save_refresh_token()
    Shifree-->>Browser: 302 → /callback-landing?dest=/worker&joined=1

    Browser->>Shifree: GET /callback-landing
    Shifree-->>Browser: 参加完了ページ
    Browser->>Shifree: GET /worker | /owner | /admin
    Shifree-->>NewUser: ロール別 SPA 表示
```

### この経路の特徴

- **Cookie 優先 + Session フォールバック** — モバイルブラウザでは OAuth リダイレクト中に Cookie が消えることがあるので、`session['invitation_token']` にも保存しています (`auth.py:125-131`)。
- **メール一致チェック** — 個別招待 (経路 A) では `invite.email` と Google アカウントのメールを大文字小文字無視で比較し、一致しないとトークンを無効化します (`auth.py:266-271`)。
- **完了ランディング** — 招待経由で参加したユーザーには `/callback-landing?joined=1` を挟み、次回以降は直接ロール別ページへ飛ばします (`auth.py:245-250`)。

---

## シーケンス図（経路 C）: 環境変数 Bootstrap

招待リンクを経由しない「初期管理者」の登録。`ADMIN_EMAIL` / `OWNER_EMAIL` に設定されたメールで直接ログインすると、自動的にロールが割り当てられます。

```mermaid
sequenceDiagram
    autonumber
    actor Bootstrap as Bootstrap 管理者
    participant Browser as ブラウザ
    participant Shifree as シフリー
    participant Google as Google OAuth
    participant DB as DB

    Bootstrap->>Browser: /login を開く
    Browser->>Shifree: GET /login
    Shifree-->>Browser: login.html

    Bootstrap->>Browser: 「Google でログイン」
    Browser->>Shifree: GET /auth/google/login<br/>(招待情報なし)
    Shifree-->>Google: 認可要求
    Google-->>Shifree: callback (email = ADMIN_EMAIL)

    Shifree->>DB: upsert_user() — 招待情報なし
    Shifree->>Shifree: determine_role()<br/>1. OrganizationMember 照会<br/>2. なければ ADMIN_EMAIL / OWNER_EMAIL と照合<br/>3. マッチすれば role='admin' or 'owner' を付与
    Shifree->>DB: OrganizationMember を作成（あれば組織に紐付け）

    alt 組織 ID が確定
        Shifree-->>Browser: 302 → /admin or /owner
    else 組織未設定（初回セットアップ）
        Shifree-->>Browser: 302 → /no-organization
        Note over Browser,Shifree: 「組織を作成する」導線から<br/>POST /api/organizations を実行
    end
```

---

## シーケンス図（経路 D）: 未所属ログイン

招待経路に該当しないユーザーは、組織に所属できず業務 API にアクセスできません。

```mermaid
sequenceDiagram
    autonumber
    actor Stranger as 招待されていないユーザー
    participant Browser as ブラウザ
    participant Shifree as シフリー
    participant Google as Google

    Stranger->>Browser: /login を開く
    Browser->>Google: OAuth 認可
    Google-->>Shifree: callback (email)

    Shifree->>Shifree: upsert_user()<br/>招待トークンなし + invite_code なし<br/>+ Bootstrap email マッチなし
    Shifree->>Shifree: 新規 User 作成のみ<br/>（OrganizationMember は作成しない）

    Shifree-->>Browser: 302 → /no-organization
    Browser->>Shifree: GET /no-organization
    Shifree-->>Stranger: no-organization.html<br/>「招待リンクが必要です」
```

### 業務上の意味

この経路で止められるユーザーは、**悪意なく身内のメールアドレスでログインしてしまった第三者**などを想定しています。未所属ユーザーは `require_role` ミドルウェアで業務 API からも弾かれるので、データ漏洩にはつながりません。

---

## ユーザー体験サマリー

| ロール | 参加直後に見える画面 | 受け取るメール |
|---|---|---|
| Worker（個別招待） | `/callback-landing?joined=1` → `/worker` | 招待メール（`notify_invitation_created`） |
| Worker（招待コード） | `/callback-landing?joined=1` → `/worker` | なし（コード共有は Admin が自由に行う） |
| Owner | `/callback-landing?joined=1` → `/owner` | 招待メール |
| Admin | `/callback-landing?joined=1` → `/admin` | 招待メール |
| Bootstrap | `/admin` または `/owner` 直行 | なし |
| 未所属 | `/no-organization` | なし |

## 参照

- `app/blueprints/auth.py:58-252` — OAuth フローと招待解決
- `app/services/auth_service.py` — `upsert_user()`, `determine_role()`, `save_refresh_token()`
- `app/blueprints/api_common.py:145-198` — `/invite` ランディング、`/api/invite/info`
- `app/models/membership.py` — `InvitationToken`, `OrganizationMember`

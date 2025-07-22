# シフト計算アプリ バックエンド要件定義書

## 1. 目的
本ドキュメントは、汎用シフト可能日計算アプリにおけるGoogle Calendar APIとの安全な連携を実現するためのバックエンドシステムの要件を定義する。これにより、認証情報の安全な管理、APIクォータの効率的な利用、および将来的な機能拡張（例: シフトの書き込み）の基盤を確立する。

## 2. アーキテクチャ
*   **フロントエンド**: 既存のHTML/JavaScriptアプリケーション。ユーザーインターフェースを提供し、バックエンドAPIを呼び出す。
*   **バックエンド**: 新規開発。Google Calendar APIとの直接連携、認証情報の管理、およびビジネスロジックの一部を担当する。

```
[ユーザー] <--- HTTP/HTTPS ---> [フロントエンド (HTML/JS)] <--- HTTP/HTTPS ---> [バックエンドサーバー] <--- HTTPS ---> [Google Calendar API]
                                                                                               ^
                                                                                               |
                                                                                             [データストア (refresh_token)]
```

## 3. 主要機能

### 3.1. Googleアカウント認証 (OAuth 2.0)
*   **認可コードフローの実装**: ユーザーの初回認証時に、GoogleのOAuth 2.0認可コードフローを用いて認証を行う。
*   **トークンの取得と保存**:
    *   Googleから発行される`access_token`（短期間有効）と`refresh_token`（長期間有効）を取得する。
    *   `refresh_token`は、ユーザーと紐付けてバックエンドのデータストアに安全に保存する。
*   **トークンの自動更新**: `access_token`が期限切れになった場合、保存された`refresh_token`を用いて自動的に新しい`access_token`を取得する。ユーザーの再認証は不要とする。

### 3.2. Google Calendar API連携
*   **カレンダーイベントの取得**:
    *   指定された期間（フロントエンドから渡される）内のGoogleカレンダーイベントを、認証済みのユーザーのカレンダーから取得する。
    *   取得するカレンダーは、ユーザーが選択したカレンダーID（またはデフォルトの`primary`）とする。
    *   取得するイベントのスコープは、読み取り専用（`https://www.googleapis.com/auth/calendar.events.readonly`）を基本とする。
*   **（将来的な拡張）シフトの書き込み**:
    *   計算されたシフト可能日をGoogleカレンダーにイベントとして書き込む機能を追加できるよう考慮する。この場合、書き込み権限（`https://www.googleapis.com/auth/calendar.events`）が必要となる。

### 3.3. APIエンドポイント
バックエンドは以下の主要なAPIエンドポイントを提供する。

*   **`/auth/google/login` (GET)**:
    *   目的: Google認証プロセスを開始する。
    *   動作: ユーザーをGoogleの認証URLにリダイレクトする。
*   **`/auth/google/callback` (GET)**:
    *   目的: Google認証後のコールバックを受け取り、トークンを処理する。
    *   動作: Googleから渡される認可コードを受け取り、それを用いて`access_token`と`refresh_token`を取得する。`refresh_token`をデータストアに保存し、ユーザーをフロントエンドの適切なページにリダイレクトする。
*   **`/api/calendar/events` (GET)**:
    *   目的: 指定期間内のカレンダーイベントを取得する。
    *   パラメータ: `startDate`, `endDate`, `calendarId` など。
    *   動作: 保存された`refresh_token`を用いてGoogle Calendar APIを呼び出し、イベントデータを取得してフロントエンドに返す。

## 4. セキュリティ考慮事項
*   **`CLIENT_SECRET`の隠蔽**: Google Cloud Platformで発行される`CLIENT_SECRET`は、バックエンドサーバー上でのみ管理し、クライアントサイドに露出させない。
*   **`refresh_token`の安全な保存**: `refresh_token`は、データベースなどの安全なデータストアに暗号化して保存することを検討する。
*   **HTTPSの利用**: 本番環境では、フロントエンドとバックエンド間の通信、およびバックエンドとGoogle API間の通信にHTTPSを必須とする。
*   **スコープの最小権限の原則**: 必要な最小限のGoogle APIスコープのみを要求する。

## 5. 技術スタック (提案)
*   **言語**: Python
*   **Webフレームワーク**: Flask (軽量でOAuthフローの実装に適しているため)
*   **Google APIクライアントライブラリ**: `google-auth-oauthlib`, `google-api-python-client` (Google公式のPythonライブラリ)
*   **HTTPクライアント**: `requests` (API呼び出し用)
*   **データストア**: SQLite (開発・テスト用。`refresh_token`の保存に利用。本番環境ではPostgreSQL, MySQLなどを検討)

## 6. 今後のステップ
1.  Google Cloud Platformでのプロジェクト設定（OAuth同意画面、OAuthクライアントIDの作成）。
2.  バックエンドサーバーのセットアップ（Python, Flask環境構築）。
3.  OAuth認証フローの実装（`/auth/google/login`, `/auth/google/callback`）。
4.  Google Calendar API呼び出しの実装（`/api/calendar/events`）。
5.  フロントエンドからバックエンドAPIへの切り替え。
6.  テストとデプロイ。

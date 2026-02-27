# シフト可能日計算アプリ

Google Calendarと連携し、個人の予定に基づいてシフト可能日を自動計算するWebアプリケーション。

## このアプリケーションで解決する課題

出勤者の予定調整は経営者にとって非常に大きな負担となります。また、出勤者にとっても、特に学生などは手書きでのシフト提出が多く、デジタル化が進んでいません。

そこで、Googleカレンダーの予定を読み込み、自動で営業時間や最低労働時間、移動時間などの条件をもとに、自動でシフト提出用の表を作成するようにしました。これにより、予定管理をGoogleカレンダーで一元化できるだけでなく、どこからいつでも見やすいシフト希望表を提出することができます。

## 機能一覧

- Google Calendar OAuth連携によるリアルタイム予定取得
- 営業時間・最低勤務時間・移動時間を考慮したシフト可能日計算
- 時間指定予定と終日予定の自動区別
- 複数月対応のカレンダー表生成
- 除外曜日・祝日の自動除外
- 印刷用シフト表・CSVエクスポート
- 設定のブラウザ保存・復元

## 技術構成

| カテゴリ | 技術 |
|---|---|
| バックエンド | Flask / SQLAlchemy |
| フロントエンド | HTML5 + CSS3 + JavaScript (単一ファイル) |
| 認証 | Google OAuth 2.0 |
| API | Google Calendar API v3 |
| DB | SQLite (ローカル) / PostgreSQL (本番) |
| デプロイ | Vercel (@vercel/python) |

## ローカル開発

### 前提条件

- Python 3.9以上
- Google Cloud Projectで Calendar API を有効化済み

### セットアップ

```bash
# 依存関係をインストール
pip install -r requirements.txt

# 環境変数を設定
cp .env.example .env  # または手動で .env を作成
```

`.env` に以下を設定:

```env
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REDIRECT_URI=http://localhost:5000/auth/google/callback
SECRET_KEY=your_secret_key
SESSION_COOKIE_SECURE=0
```

> Google Cloud Console > APIとサービス > 認証情報 で OAuth 2.0 クライアントIDを作成し、
> リダイレクトURIに `http://localhost:5000/auth/google/callback` を追加してください。

### 起動

```bash
python app.py
```

`http://localhost:5000/app` にアクセス。

## Vercelデプロイ

### 1. Vercel CLIまたはダッシュボードでプロジェクトをインポート

```bash
vercel
```

### 2. 環境変数を設定

Vercelダッシュボード > Settings > Environment Variables に以下を追加:

| 変数名 | 値 |
|---|---|
| `GOOGLE_CLIENT_ID` | OAuth クライアントID |
| `GOOGLE_CLIENT_SECRET` | OAuth クライアントシークレット |
| `GOOGLE_REDIRECT_URI` | `https://your-domain.vercel.app/auth/google/callback` |
| `SECRET_KEY` | ランダムな秘密鍵 |
| `DATABASE_URL` | PostgreSQL接続文字列 (Vercel Postgres等) |

### 3. デプロイ

```bash
vercel --prod
```

> Google Cloud ConsoleのリダイレクトURIにVercelのURLを追加するのを忘れずに。

## 使い方

1. 「Googleアカウント認証」でカレンダーアクセスを許可
2. 営業時間・最低勤務時間・移動時間を設定
3. 期間を指定して「シフト可能日を計算」
4. 結果を確認し、出勤希望日をチェック
5. 「シフト表を生成」または「CSV出力」で結果を出力

## ファイル構成

```
シフト計算アプリ/
├── app.py                          # Flaskメインアプリケーション
├── api/
│   └── index.py                    # Vercelエントリポイント
├── static/
│   └── shift_scheduler_app.html    # フロントエンドHTML (単一ファイル)
├── vercel.json                     # Vercelルーティング設定
├── requirements.txt                # Python依存関係
├── .env                            # 環境変数 (git管理外)
└── .gitignore
```

## トラブルシューティング

- **認証エラー**: Google Cloud ConsoleのリダイレクトURIが正しいか確認
- **OAuthコールバックがHTTPになる**: `ProxyFix`ミドルウェアが有効か確認 (Vercel環境)
- **ローカルでCookieが保存されない**: `.env`に`SESSION_COOKIE_SECURE=0`を設定

## ライセンス

MIT

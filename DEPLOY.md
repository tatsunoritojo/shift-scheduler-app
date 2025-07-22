# デプロイガイド

このガイドでは、シフト計算アプリを本番環境にデプロイする手順を説明します。

## 🚨 重要な注意事項

**GitHub Pages は使用できません**
- このアプリはFlaskサーバーが必要な動的Webアプリケーションです
- GitHub Pagesは静的サイトのみ対応のため使用不可

## 🌟 推奨デプロイ先

### 1. Heroku（最も簡単）

#### 前提条件
- Heroku CLIのインストール
- Gitリポジトリの初期化

#### デプロイ手順

```bash
# 1. Herokuアプリを作成
heroku create your-shift-app-name

# 2. 環境変数を設定
heroku config:set GOOGLE_CLIENT_ID="your_client_id_here"
heroku config:set GOOGLE_CLIENT_SECRET="your_client_secret_here"
heroku config:set GOOGLE_REDIRECT_URI="https://your-shift-app-name.herokuapp.com/auth/google/callback"
heroku config:set SECRET_KEY="your_secret_key_here"

# 3. デプロイ
git add .
git commit -m "Initial commit"
git push heroku main
```

#### Google Cloud Console設定
1. Google Cloud Consoleで認証情報を編集
2. 「承認済みのリダイレクトURI」に以下を追加：
   ```
   https://your-shift-app-name.herokuapp.com/auth/google/callback
   ```

### 2. Railway（モダンな選択肢）

```bash
# 1. Railway CLIをインストール
npm install -g @railway/cli

# 2. ログインしてプロジェクト作成
railway login
railway init

# 3. 環境変数を設定
railway variables:set GOOGLE_CLIENT_ID="your_client_id_here"
railway variables:set GOOGLE_CLIENT_SECRET="your_client_secret_here"
railway variables:set GOOGLE_REDIRECT_URI="https://your-domain.railway.app/auth/google/callback"
railway variables:set SECRET_KEY="your_secret_key_here"

# 4. デプロイ
railway up
```

### 3. Render（セキュリティ重視）

1. [Render.com](https://render.com/)でアカウント作成
2. GitHubリポジトリを接続
3. Web Serviceとして作成
4. 環境変数を設定：
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - `GOOGLE_REDIRECT_URI`
   - `SECRET_KEY`

## 🔐 セキュリティ設定

### 必須の環境変数

```env
# Google OAuth認証情報
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=https://your-domain.com/auth/google/callback

# セッション暗号化キー（32文字のランダム文字列）
SECRET_KEY=your_32_character_random_string

# データベースURL（PostgreSQL使用の場合）
DATABASE_URL=postgresql://user:pass@host:port/db
```

### SECRET_KEYの生成

```python
# Python で安全なキーを生成
import secrets
print(secrets.token_hex(32))
```

## 🗂️ ファイル構成（デプロイ用）

```
シフト計算アプリ/
├── app_production.py     # 本番環境用アプリケーション
├── Procfile             # Heroku起動設定
├── runtime.txt          # Python バージョン指定
├── requirements.txt     # 依存関係
├── static/
│   └── shift_scheduler_app.html
└── README.md
```

## 🚀 デプロイ前チェックリスト

### セキュリティ
- [ ] `.env`ファイルが`.gitignore`に含まれている
- [ ] 認証情報がコードにハードコードされていない
- [ ] `OAUTHLIB_INSECURE_TRANSPORT=1`が削除されている
- [ ] `SECRET_KEY`が環境変数で設定されている

### 機能
- [ ] Google Cloud ConsoleでHTTPSリダイレクトURIが設定されている
- [ ] 環境変数がすべて設定されている
- [ ] データベースの接続設定が正しい

### テスト
- [ ] ローカル環境で動作確認済み
- [ ] OAuth認証フローが正常動作
- [ ] カレンダーデータの取得が成功

## ⚡ 高速デプロイ（Heroku）

```bash
# 1行でデプロイ準備
git init && git add . && git commit -m "Ready for deploy"

# Herokuアプリ作成〜デプロイ
heroku create your-app-name && \
heroku config:set GOOGLE_CLIENT_ID="YOUR_ID" && \
heroku config:set GOOGLE_CLIENT_SECRET="YOUR_SECRET" && \
heroku config:set GOOGLE_REDIRECT_URI="https://your-app-name.herokuapp.com/auth/google/callback" && \
heroku config:set SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')" && \
git push heroku main
```

## 🔧 トラブルシューティング

### デプロイエラー

**エラー**: `Application error`
**解決**: Heroku logsを確認
```bash
heroku logs --tail
```

**エラー**: `redirect_uri_mismatch`
**解決**: Google Cloud ConsoleのリダイレクトURIを確認

**エラー**: `ModuleNotFoundError`
**解決**: `requirements.txt`の依存関係を確認

### 認証エラー

**エラー**: OAuth認証が失敗する
**解決**: 
1. HTTPSが有効になっているか確認
2. Google Cloud Consoleの設定確認
3. 環境変数の値が正しいか確認

## 📊 本番環境での監視

### ログ監視
```bash
# Heroku
heroku logs --tail

# Railway
railway logs

# Render
# ダッシュボードでログ確認
```

### パフォーマンス監視
- アプリケーションの応答時間
- データベース接続数
- メモリ使用量

---

**⚠️ 注意**: 本番環境では定期的なセキュリティ更新とモニタリングを行ってください。
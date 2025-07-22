# 🎯 Renderデプロイ完全ガイド

このガイドに従って、Renderにシフト計算アプリをデプロイします。

## ステップ1: 必要な準備

### SECRET_KEYの生成
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
📋 生成された値をメモしてください。

## ステップ2: GitHubリポジトリの作成

### 2.1 ローカルでGitリポジトリ初期化
```bash
cd "C:\Users\tatsu\Github\シフト計算アプリ"
git init
git add .
git commit -m "Initial commit: Shift Scheduler App v1.0"
```

### 2.2 GitHubにリポジトリ作成
1. [GitHub](https://github.com)でNew repositoryを作成
2. リポジトリ名: `shift-scheduler-app`（推奨）
3. Private/Publicはお好みで選択
4. READMEの初期化は「しない」を選択

### 2.3 リモートリポジトリに接続
```bash
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/shift-scheduler-app.git
git push -u origin main
```

## ステップ3: Google Cloud Console設定更新

### 3.1 認証情報の編集
1. [Google Cloud Console](https://console.cloud.google.com/)
2. APIとサービス → 認証情報
3. 作成したOAuth 2.0クライアントIDを選択
4. 「承認済みのリダイレクトURI」に以下を**追加**:
   ```
   https://YOUR_APP_NAME.onrender.com/auth/google/callback
   ```
   ⚠️ `YOUR_APP_NAME`は次のステップで決める名前に置き換えてください

## ステップ4: Renderでのデプロイ

### 4.1 Renderアカウント作成
1. [Render.com](https://render.com/)にアクセス
2. 「Get Started for Free」をクリック
3. GitHubアカウントでサインアップ（推奨）

### 4.2 New Web Service作成
1. Renderダッシュボードで「New +」→「Web Service」を選択
2. 「Connect a repository」でGitHubを選択
3. 作成したリポジトリ `shift-scheduler-app` を選択
4. 「Connect」をクリック

### 4.3 サービス設定
以下の設定を入力してください：

| 項目 | 設定値 |
|------|--------|
| **Name** | `shift-scheduler-app`（任意の名前） |
| **Region** | `Oregon (US West)` |
| **Branch** | `main` |
| **Root Directory** | (空白) |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `python app_production.py` |
| **Plan** | `Free` |

### 4.4 環境変数の設定
「Environment Variables」セクションで以下を追加：

| Key | Value | 説明 |
|-----|-------|------|
| `GOOGLE_CLIENT_ID` | `あなたのクライアントID` | Google Cloud Consoleから取得 |
| `GOOGLE_CLIENT_SECRET` | `あなたのクライアントシークレット` | Google Cloud Consoleから取得 |
| `GOOGLE_REDIRECT_URI` | `https://YOUR_APP_NAME.onrender.com/auth/google/callback` | YOUR_APP_NAMEを実際の名前に置き換え |
| `SECRET_KEY` | `ステップ1で生成した32文字の文字列` | セッション暗号化キー |

⚠️ **重要**: 環境変数の値は「""」で囲まない、そのまま入力してください。

### 4.5 デプロイ実行
「Create Web Service」をクリックしてデプロイを開始します。

## ステップ5: Google Cloud Console最終設定

デプロイが完了したら、実際のRender URLを確認し、Google Cloud Consoleの設定を更新してください。

### 5.1 RenderでURLを確認
1. Renderダッシュボードでサービスを選択
2. 上部に表示される `https://your-app-name.onrender.com` をコピー

### 5.2 Google Cloud Consoleで最終更新
1. 先ほど追加したリダイレクトURIを正確なURLに更新
2. 保存をクリック

## ステップ6: 動作テスト

### 6.1 基本動作確認
1. `https://your-app-name.onrender.com` にアクセス
2. アプリケーションが正常に表示されることを確認

### 6.2 認証テスト
1. 「Googleアカウント認証」ボタンをクリック
2. Googleログイン画面が表示されることを確認
3. 認証後、アプリに戻ることを確認

### 6.3 機能テスト
1. 期間を設定してシフト計算を実行
2. カレンダーデータが取得されることを確認
3. シフト表生成が動作することを確認

## 🔧 トラブルシューティング

### デプロイエラー
- **Build Failed**: `requirements.txt`の内容を確認
- **Start Failed**: `app_production.py`のパスを確認

### 認証エラー
- **redirect_uri_mismatch**: Google Cloud ConsoleのURLが正確か確認
- **403 access_denied**: OAuth同意画面の設定を確認

### 接続エラー
- **500 Internal Server Error**: Renderのログを確認
  1. サービス詳細画面で「Logs」タブを選択
  2. エラーメッセージを確認

## ✅ 成功チェックリスト

- [ ] GitHubリポジトリが作成された
- [ ] Renderでサービスがデプロイされた
- [ ] 環境変数がすべて設定された
- [ ] Google Cloud ConsoleでHTTPS URLが設定された
- [ ] アプリケーションにアクセスできる
- [ ] Google認証が正常動作する
- [ ] シフト計算機能が動作する

## 🎉 デプロイ完了後の設定

### セキュリティ設定
- Renderダッシュボードで「Settings」→「Environment Variables」で値が適切にマスクされていることを確認

### 自動デプロイ
- GitHubにpushするたびにRenderが自動的に再デプロイします
- 「Auto-Deploy」がYESになっていることを確認

### モニタリング
- Renderダッシュボードでアプリのパフォーマンスを監視できます
- 異常があればメール通知を受け取れます

---

**🎯 完了予定時間**: 15-20分
**💰 費用**: 完全無料（Free プラン使用）
**🔒 セキュリティ**: Render標準のHTTPS/暗号化適用済み
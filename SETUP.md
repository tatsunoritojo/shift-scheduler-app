# セットアップガイド

このガイドでは、シフト計算アプリを初回設定する手順を詳しく説明します。

## 前提条件

- Python 3.8以上がインストールされていること
- インターネット接続があること
- Googleアカウントを持っていること

## ステップ1: Google Cloud Consoleでの設定

### 1.1 プロジェクトの作成
1. [Google Cloud Console](https://console.cloud.google.com/)にアクセス
2. 「プロジェクトを作成」をクリック
3. プロジェクト名を入力（例：「shift-scheduler-app」）
4. 「作成」をクリック

### 1.2 Google Calendar APIの有効化
1. 左側メニューから「APIとサービス」→「ライブラリ」を選択
2. 検索欄に「Google Calendar API」と入力
3. 「Google Calendar API」を選択
4. 「有効にする」をクリック

### 1.3 OAuth 2.0認証情報の作成
1. 左側メニューから「APIとサービス」→「認証情報」を選択
2. 「認証情報を作成」→「OAuth クライアント ID」をクリック
3. 「同意画面を構成」が表示された場合：
   - User Type: 「外部」を選択
   - 「作成」をクリック
   - アプリ名、ユーザーサポートメール、デベロッパーの連絡先情報を入力
   - 「保存して次へ」を繰り返してスコープとテストユーザーをスキップ
4. アプリケーションの種類で「ウェブ アプリケーション」を選択
5. 名前を入力（例：「Shift Scheduler Web Client」）
6. 「承認済みのリダイレクト URI」に以下を追加：
   ```
   http://localhost:5000/auth/google/callback
   ```
7. 「作成」をクリック

### 1.4 認証情報のダウンロード
1. 作成されたOAuth 2.0クライアントの右側にある「ダウンロード」アイコンをクリック
2. JSONファイルがダウンロードされます
3. ファイルをプロジェクトフォルダにコピーし、名前を確認してください

## ステップ2: アプリケーションの設定

### 2.1 依存関係のインストール
```bash
cd "C:\Users\tatsu\Github\シフト計算アプリ"
pip install -r requirements.txt
```

### 2.2 環境変数の設定
1. ダウンロードしたJSONファイルを開く
2. `.env`ファイルを編集し、以下の値を設定：

```env
GOOGLE_CLIENT_ID=【JSONファイルのclient_id】
GOOGLE_CLIENT_SECRET=【JSONファイルのclient_secret】
GOOGLE_REDIRECT_URI=http://localhost:5000/auth/google/callback
```

### 2.3 アプリケーションの起動テスト
```bash
python app.py
```

ブラウザで http://localhost:5000/app にアクセスして動作を確認してください。

## トラブルシューティング

### エラー1: "403 access_denied"
**原因**: OAuth同意画面の設定が不完全
**解決策**: Google Cloud Consoleでアプリを「本番環境」に公開するか、テストユーザーに自分のGoogleアカウントを追加

### エラー2: "redirect_uri_mismatch"
**原因**: リダイレクトURIの設定が一致しない
**解決策**: Google Cloud Consoleで設定したURIと`.env`ファイルのURIが完全に一致するか確認

### エラー3: "ImportError: No module named..."
**原因**: 必要なPythonパッケージがインストールされていない
**解決策**: `pip install -r requirements.txt`を再実行

### エラー4: カレンダーデータが取得できない
**原因**: Google Calendar APIが有効化されていない
**解決策**: Google Cloud ConsoleでGoogle Calendar APIが有効になっているか確認

## セキュリティに関する注意点

1. **認証情報の管理**
   - `.env`ファイルはGitリポジトリにコミットしないでください
   - `client_secret*.json`ファイルも同様に除外してください

2. **本番環境での使用**
   - 本番環境では適切なHTTPS設定を行ってください
   - `OAUTHLIB_INSECURE_TRANSPORT=1`の設定は開発環境のみで使用してください

3. **アクセス権限**
   - このアプリはカレンダーの読み取り専用権限を使用します
   - 必要以上の権限を与えないよう注意してください

## 次のステップ

セットアップが完了したら、README.mdの「使用方法」セクションを参照して実際にアプリケーションを使用してみてください。
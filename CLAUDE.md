# shift-scheduler-app

マルチテナント対応シフト管理システム（Flask + Vanilla JS）
デプロイ先: Vercel (サーバーレス)

## アクティブな対応事項（次セッション着手用）

**最終更新: 2026-04-25**

優先順位:
1. **タブ順入替** — admin画面の初期表示をシフト作成画面に。設定タブを後ろへ（小・即対応可）
2. **重複チェック挙動の検証** — Phase A の `overlap_check` が「コア×自習室は許可、自習室同士は禁止」を再現できるか確認
3. **シフト期間フィルタ/アーカイブ** — 蓄積で見えづらくなる問題への対処（要スコープ整理）
4. **営業日マスタ機能** — Googleカレンダー依存を減らし、アプリ内から営業日一括投入（要スコープ整理）
5. **キロクル連携API** — `attendance-saas` との連携用。最小構成想定で1〜2週間（仕様確定後）

セッション開始時はこのリストとメモファイルを必ず確認すること。タスク完了時はこのセクションも更新する。

## 技術スタック

- Backend: Python 3.9+ / Flask 3.1 / SQLAlchemy + Alembic
- Frontend: Vanilla JS + HTML（ロール別SPA）
- DB: SQLite (dev) / PostgreSQL (prod)
- 認証: Google OAuth 2.0
- デプロイ: Vercel (サーバーレス + Cron)
- テスト: pytest (153件)

## 最初に確認するファイル

バックエンド修正時:
1. `app/__init__.py` — アプリケーションファクトリ
2. `app/config.py` — 環境別設定
3. `app/blueprints/` 配下の該当ブループリント
4. `app/models/` 配下の該当モデル
5. `app/services/` 配下の該当サービス

フロントエンド修正時:
1. `static/pages/` — ロール別HTMLテンプレート (admin, worker, owner)
2. `static/js/` — ロール別JSアプリ (admin-app.js が最大)
3. `static/css/` — ロール別スタイル

認証・権限の修正時:
1. `app/middleware/auth_middleware.py` — @require_auth, @require_role
2. `app/blueprints/auth.py` — OAuth + 招待トークン
3. `app/services/auth_service.py`

## 標準コマンド

```bash
pip install -r requirements.txt   # 依存インストール
python wsgi.py                    # 開発サーバー (localhost:5000)
pytest                            # テスト実行 (153件)
flask db migrate -m "message"     # マイグレーション生成
flask db upgrade                  # マイグレーション適用
```

## ブループリント構成

| ブループリント | 役割 |
|---|---|
| auth_bp | Google OAuth + 招待 |
| api_admin_bp | 管理者操作 (営業時間, シフト期間, メンバー) |
| api_worker_bp | ワーカーのシフト希望提出 |
| api_owner_bp | オーナー承認ワークフロー |
| api_calendar_bp | Google Calendar 同期 |
| api_cron_bp | 非同期タスク処理 |
| api_dashboard_bp | 運用ダッシュボード |

## 検証ルール

- モデル変更後: `flask db migrate` → `flask db upgrade` → `pytest`
- サービスロジック変更後: `pytest` で回帰テスト
- ブループリント変更後: 該当テストファイルを確認してから `pytest`
- フロントエンド変更後: `python wsgi.py` で手動確認

## 注意点

- Vercel デプロイ時、`api/index.py` がエントリポイント（コールドスタートでマイグレーション自動実行）
- 環境変数: `.env.local` 参照（本番は Vercel ダッシュボードで管理）
- PWA対応: `static/manifest.json` + `static/sw.js`
- RBAC: admin / owner / worker の3ロール（DB駆動）

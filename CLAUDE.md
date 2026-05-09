# shift-scheduler-app

マルチテナント対応シフト管理システム（Flask + Vanilla JS）
デプロイ先: Vercel (サーバーレス)

## LP Phase 2a 実装乖離対応

**最終更新: 2026-05-05** — 全項目クローズ、Phase 2a-3 修正依頼の準備完了

LP Phase 2a の Scene 1-6 で発見した実装乖離を埋める作業群。詳細は `docs/lp-redesign-v2/phase-2a-fix-request.md`、判定の根拠は `docs/sequence-diagrams/`。

- ~~**B: 期間公開メール通知 + 募集文面**~~ — PR #24 マージ済（c5a0e41 backend / 4bca151 frontend）
- ~~**A: Worker 提出 UI の Google Cal Free/Busy 連動**~~ — **既存実装で成立** (`worker-app.js` + `shift-calculator.js` の `calculateAvailableSlots`)。発見後シーケンス図を更新 (PR #25)
- ~~**D: 必要人数管理 (StaffingRequirement)**~~ — branch `feature/staffing-requirements`（258fb8d backend / 18126b1 frontend）
- ~~**C: PNG/PDF 期間カレンダー書き出し**~~ — 既存実装で成立 (`openShareModal` + html2canvas/jsPDF)

次フェーズ: ClaudeDesign に Phase 2a-3 修正依頼を投げる。Scene 1 + Scene 2 + Scene 4 のコピーを「実装と整合する形」に微調整するのみ（核となる動作は全て実装側で支えられている）。

**次セッション着手用ポインタ:**
- ✉️ 投げる依頼書: `docs/lp-redesign-v2/phase-2a-3-fix-request.md` — 「プロンプト本文（ここから下をコピペ）」セクションをそのまま ClaudeDesign に渡せばよい状態
- 📜 前セッション履歴: `docs/lp-redesign-v2/phase-2a-fix-request.md` — Phase 2a-2 修正依頼の履歴（既反映済）
- 🧭 fact 判定根拠: `docs/sequence-diagrams/02-worker-monthly-flow.md`（Worker UI Free/Busy 連動の正確な経路を追記済、PR #25）
- ⚠️ 既存問題（無関係）: `tests/test_reminder.py::TestSubmissionReminders::test_auto_submission_reminders` は日付固定（2026-04-30）で常時失敗。LP 対応とは無関係なので別 PR で修正する → **2026-05-09 解消** (PR #38、真因は時刻依存 flake)

## Schema Governance

### 現在地
- Schema Governance 着手完了。
- 本番障害は復旧済み。
- production DB head は `d4310c2b47c0`。
- `/health/schema` は本番で `match=true` を返却中。
- ADR 0001 / 0002 は Accepted。
- ADR 0002 Step 1 は実装・deploy 済み。
  - 起動時 revision cache
  - `/health/schema`
  - 503 遮断はまだ未有効化（Step 2 待ち）

### 次アクション
1. ADR 0001 Phase 1
   - GitHub Actions で migration workflow 実装
   - migration 成功後のみ deploy
   - `_run_auto_migration` を runtime から削除
2. Vercel Cron
   - `/health/schema` を 5 分おきに polling
   - mismatch / check_failed を監視対象化
3. ADR 0002 Step 2
   - `/api/admin/*` への 503 遮断を有効化
   - ただし Step 1 の観測ログを一定期間見てから
4. P1 タスク
   - `User.role` / `User.organization_id` の認可キャッシュ見直し
   - CHECK 制約
   - CI の Postgres 化
   - index 確度高 3 本

### 参照ファイル
- `docs/decisions/0001-replace-cold-start-auto-migration-with-cicd.md`
- `docs/decisions/0002-schema-mismatch-fail-fast-middleware.md`
- `app/middleware/schema_guard.py`
- `app/blueprints/api_common.py`
- `app/__init__.py`

### 未解決
- ADR 0001 Phase 1 は未実装
- ADR 0002 Step 2 の 503 遮断は未有効化
- `/health/schema` の監視は手動確認止まり
- P1 の DB 負債整理は未着手

### 最終更新
- 2026-05-09

## アクティブな対応事項（次セッション着手用）

**最終更新: 2026-04-26**

優先順位:
1. ~~**タブ順入替**~~ — 2026-04-25 完了（PR #15 main マージ済み）
2. ~~**シフト期間アーカイブ・完全削除**~~ — 2026-04-26 完了（PR #16、ブランチ `feature/period-archive-delete`）
3. **シフト構築画面の提出状況改善** — 提出済みだけでなく未提出者も一覧表示し、未提出者の各行にリマインドボタンを配置する（クライアント要望、2026-04-26）
4. **重複チェック挙動の検証** — Phase A の `overlap_check` が「コア×自習室は許可、自習室同士は禁止」を再現できるか確認
5. **営業日マスタ機能** — Googleカレンダー依存を減らし、アプリ内から営業日一括投入（要スコープ整理）
6. **キロクル連携API** — `attendance-saas` との連携用。最小構成想定で1〜2週間（仕様確定後）
7. **ライフサイクル監査の残課題** — `docs/lifecycle-audit-2026-04-26.md` 参照。OrganizationMember 復活 API、VacancyRequest cancel UI、ShiftSchedule 確定後取消などが個別 PR 候補

タブUI再設計の持ち越しタスク（別PR候補）:
- Major 2: 主要操作後のバッジ古さ対策（mutation 後の reload 漏れチェック）
- Minor 7: ARIA タブパターン対応、separator 折り返し対策、二重ロード解消、aria-label 追加など

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

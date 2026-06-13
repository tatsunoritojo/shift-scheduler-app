# Shifree（旧 shift-scheduler-app）

マルチテナント対応シフト管理システム（Flask + Vanilla JS）。本番ドメイン: `shifree.com`
デプロイ先: Vercel (サーバーレス)

## ドキュメント整備履歴

経過日数を即時把握できるように、実施日のみを記録する（内容詳細は PR / git log 参照）。

| 種別 | 実施日 | 参照 |
|---|---|---|
| README ポートフォリオ向け全面リライト | 2026-05-10 | PR #41 |

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

## OAuth Verification 本番公開対応

**最終更新: 2026-06-02** — OAuth consent screen を **In production** へ変更完了。refresh token 7日失効問題は解消見込み（経過観察: 2026-06-09）。次は OAuth verification submission

テストモードの OAuth consent screen では calendar スコープ使用時 refresh token が **7日で失効** する公式仕様（https://developers.google.com/identity/protocols/oauth2 — Refresh token expiration）。これが種さん等の `CREDENTIALS_EXPIRED` の真因。根本解決として OAuth consent screen を Production 化し、sensitive scope の verification 申請へ進む。

### 現在地
- 本番ドメイン: **`https://shifree.com`**（production 稼働中）
- OAuth ログイン: `shifree.com` 起点で **E2E 成功**（callback / state エラーなし、`redirect_uri` に改行 `%0A` 混入なしを確認）
- PR #43: main に squash merge 済み（squash commit `e3b778f`）— Phase 1 バッチ1 + Phase 2 コード（`BASE_URL` env 配線、公開URL を `shifree.com` 化）
- PR #44: main に squash merge 済み（commit `c049477`）— Phase 2 + env 切替の handoff 反映
- **PR #45: main に squash merge 済み（squash commit `5c76f82c4037810371025a2b4ce6947b6a1035d3`）— domain redirect**
  - `vercel.json` に `shifree.vercel.app`→`shifree.com` の host 条件付き redirect を追加
  - `source: /:path((?!api/).*)` で **`/api/` は redirect 対象外**（cron / 同一オリジン API を保護）
  - `permanent: false` ＝ **307 redirect**
  - 本番 deploy: id `dpl_h7SqZLMPQRJxZdLUzJGSuCzDqu1i` / target production / state READY
  - **curl 実測パス**（2026-06-01）:
    - `shifree.vercel.app/` `/lp` `/worker` → 307 → `shifree.com/...`（path 保持）
    - `/auth/invite/dummy-token?foo=bar` / `/vacancy/respond?token=dummy-token&action=accept` → 307 で **query 保持**
    - `/api/index` → 404（307 でない）＝ `/api/` 除外が機能
    - `shifree.com/` → 302 `/login`（相対）/ `/lp` → 200 ＝ **redirect loop なし**
    - Preview URL（`shifree-<hash>.vercel.app` / `shifree-git-main-…`）→ 401（保護）で **redirect されない**＝host 条件は完全一致のみ
- これにより解消したリスク:
  - 旧 `shifree.vercel.app` 起点アクセスが入口で `shifree.com` に寄る
  - admin が旧ブックマークから入った場合の `request.host_url` 由来リンク（招待・欠員・手動リマインド）が vercel.app を指すリスクが低下
  - OAuth state 不一致リスクが入口側で軽減
- Vercel env（最終状態、`vercel env ls` 確認済み）:
  - `GOOGLE_REDIRECT_URI`: Production=`https://shifree.com/auth/google/callback` / Preview・Development=`https://shifree.vercel.app/auth/google/callback`
  - `CORS_ALLOWED_ORIGINS`: Production=`https://shifree.com` / Preview・Development=`https://shifree.vercel.app`
  - `BASE_URL`: Production=`https://shifree.com`（Preview/Dev には元から無し）
- reminder リンク調査（2026-06-01）: 自動リマインダー（cron、`reminder_service.py:120-121`）は `BASE_URL` 由来で **shifree.com 確定**。admin 起点リンク3経路（`api_admin.py:506` 手動リマインド / `:1160` 招待 / `:1338` 欠員）は `request.host_url` 由来＝admin のアクセスドメイン依存だが、domain redirect で入口が寄るため実質 shifree.com に揃う。旧ドメインのハードコードはコード・メールテンプレートに無し
- **OAuth consent screen: In production**（2026-06-02 に Testing → In production へ変更完了）
  - GCC 実施前確認: App name `shifree` / User type External / sensitive scopes 3件（`calendar.events` / `calendar.events.readonly` / `calendar.readonly`）/ restricted なし / OAuth user cap 15/100
  - Publish App 後 E2E: `shifree.com` 起点ログイン成功（`tatsunoritojo@gmail.com`）/ refresh token 保存確認（user_id=5, updated 2026-06-02 02:40 UTC）/ domain redirect 継続動作
  - 未確認アプリ警告: **表示あり**（sensitive scope の verification 未完了のため。verification 完了後に自動消去）
- OAuth verification submission: 未実施（In production 化の次ステップ）
- `shifree.vercel.app` は段階移行用に残置（Vercel domain / GCP Redirect URI / Authorized domains いずれも残置。ただし入口は 307 で shifree.com へ寄る）

### 注意・教訓（今回の失敗から）
- **Vercel env を CLI 投入するときは `printf '%s'` を使う**。`echo` は末尾改行を値に混入させ、`GOOGLE_REDIRECT_URI` に `%0A` が入って `redirect_uri_mismatch` を起こす（今回是正済み）
- `vercel env rm NAME production` は、全環境同値で束ねられた変数を削除すると **Preview / Development も巻き込んで消す**。production だけ変えたつもりでも他環境が脱落する
- Preview env は CLI 非対話実行で Git branch 指定（`git_branch_required`）に詰まる。**Preview の復元は Dashboard 手動が確実**（今回そうした）
- production 切替後、旧 `shifree.vercel.app` 起点ログインはクロスドメイン state 不一致で**失敗する想定**（`SESSION_COOKIE_DOMAIN` 未設定でホスト別スコープのため）。旧ドメイン入口は domain redirect で `shifree.com` へ寄せて解消する

### legacy scope 救済（OAUTHLIB_RELAX_TOKEN_SCOPE）

**2026-06-02 追加。理由: PR #48 後の legacy scope 付与アカウント救済のため。**

- 障害: PR #48（`3424cec`）で `calendar.events.readonly` を要求 scope から削除したが、テスト期にログイン済みのアカウントは Google 側に旧 scope 付与が残存。`login()` の `include_granted_scopes='true'`（`auth.py:120`）により、token 応答 scope が要求 scope（5）より多くなり、oauthlib が `flow.fetch_token` で scope mismatch を**例外**にして `LOGIN_FAILED: Token fetch failed`（500）→ ユーザーには「認証に失敗しました」表示。
- 確証: `onedrop202507@gmail.com` を `myaccount.google.com/permissions` で revoke → 再ログイン成功、の対照実験で機序確定（原因分類 F）。
- 恒久対策: **Vercel Production env に `OAUTHLIB_RELAX_TOKEN_SCOPE=1` を追加**（Production のみ。Preview/Dev には入れない）。oauthlib が scope mismatch を raise せず warning に降格 → fetch_token 成功。これで legacy アカウント全員が revoke なしでログイン可能。
- 副作用（許容済み）: legacy ユーザーは `user_tokens.scopes` に `calendar.events.readonly` が残り得る。API 呼び出しの Credentials は `config.GOOGLE_SCOPES_WRITE`（5 scope、`auth_service.py:343`）から再構築されるため**機能影響なし**。要求 scope は 5 のまま（verification 整合 OK）。再 consent で自然に 5 へ収束。
- 適用: env 追加後、現 Production deployment を Redeploy（`dpl_5ogTaiYJMycUdoHT3ZxKZEt9S1mP` → `dpl_GUxyPYNPerAW9tKpU5o4rUVxt6Q2`、shifree.com alias 済み、READY）。
- rollback: `vercel env rm OAUTHLIB_RELAX_TOKEN_SCOPE production` → Redeploy。可逆（外すと legacy が再び 500 に戻るのみ）。
- 将来のクリーンアップ候補: `login()` から `include_granted_scopes='true'` を外す案（superset を合算させない根本対策。ただし挙動変更のため別 PR で評価）。
- **E2E 実証済み（2026-06-02）**: 影響アカウントは **14件**（Onedrop パイロットスタッフ `onedrop.*` + `tatsunoritojo` id=5。全員が legacy 6-scope grant を保有）。うち **id=5 / id=6 が revoke せず RELAX 有効 deployment（`dpl_GUxyPYNPerAW9tKpU5o4rUVxt6Q2`）でログイン成功**（`LOGIN_SUCCESS` 12:20 / 12:24 UTC）。同 deployment で `LOGIN_FAILED: Token fetch failed` の新規発生ゼロ。OAuth 要求 scope は 5 のまま（curl 実測）。→ **残り12名も RELAX で自動救済、revoke 依頼不要**。
- 補足: `onedrop202507`（id=4）は revoke 済みのため保存 scope が 5 に再保存され、影響リストから外れている（仮説の裏取り）。
- **未確認**: Calendar 一覧取得 / Calendar sync（イベント書き込み）の機能テスト（OAuth 残タスク 2 と同一）。`user_tokens.scopes` は legacy ユーザーで 6 のまま残る想定（機能影響なし）。
- **GCC Data Access からの `calendar.events.readonly` 削除は未実施**。ログインは実証済みなので技術的には削除可（RELAX が mismatch を吸収）。推奨順序は「Calendar 機能テスト → GCC 削除 → verification submission」。

### 残タスク
1. **経過観察: 2026-06-09 頃に refresh token が失効しないことを確認**（In production 化で 7日失効は解消されたはずだが、実測で裏取りする）
2. Worker の Calendar Free/Busy 取得確認 / Admin の Calendar sync（イベント書き込み）確認
3. **OAuth verification submission**（scope justification / デモ動画シナリオ / sensitive scope 審査。目安 10営業日）
4. 未確認アプリ警告の解消（verification 完了後に自動消去）
5. `api_admin.py` の `request.host_url` → `BASE_URL` 統一（防御的修正候補。domain redirect で実害は低下済み）
6. `www.googleapis.com` が Authorized domains に残っている件の整理（由来不明、verification 申請時に指摘される可能性）
7. 旧 `shifree.vercel.app` の最終整理（Vercel domain / GCP Redirect URI / Authorized domains。verification 安定後）
8. Preview / Development を将来 `shifree.com` に寄せるか判断（現状 `shifree.vercel.app` のまま保留）
9. cron `/api/cron/process-tasks` の継続正常実行を観測

### 次セッション着手用ポインタ
- 詳細 handoff: `docs/notes/260531_oauth-verification-phase1-handoff.md`（Phase 1〜2 + env 切替 + domain redirect + In production + 失敗教訓の累積記録）
- 次回開始順: ①`git status` → ②本 OAuth セクション（特に「legacy scope 救済」サブセクション）→ ③**Calendar 機能テストの結果確認**（最優先・下記）→ ④判定6項目クリアなら GCC Data Access から `calendar.events.readonly` 削除手順を設計 → ⑤OAuth verification submission の準備
- **最優先の次アクション（2026-06-02 時点）**: Calendar 一覧取得 / Calendar sync の手動 E2E。東城さんが `shifree.com` で操作 → 操作 UTC 時刻を控える → Vercel ログ（deployment `dpl_GUxyPYNPerAW9tKpU5o4rUVxt6Q2`）で照合。照合する文字列は `Google Calendar API error:` / `Calendar event fetch error:` / `Credential error for user` / `CREDENTIALS_EXPIRED` / `CALENDAR_PERMISSION_DENIED` / `CALENDAR_API_ERROR` / `LOGIN_FAILED`（いずれも「出ない」+ Calendar 系が 2xx なら合格。成功時の専用ログは無いので絶対の不在で判定）。根拠: `app/services/calendar_service.py:24,46,73,89,101-110` / `app/blueprints/api_calendar.py:61,70,37`
- 判定基準6項目（全クリアで GCC 削除可）: legacy ログイン復旧済✓ / `LOGIN_FAILED` 新規ゼロ✓ / 要求 scope 5✓ / Calendar 一覧取得正常（未） / Calendar sync・イベント作成正常（未） / コードが events.readonly 非要求✓。残るは Calendar 機能2項目のみ。
- 最終 handoff 未固定: Calendar テスト + GCC 削除まで終わったら CLAUDE.md と `docs/notes/260602_oauth-verification-preparation.md` をまとめて更新し PR 化する方針（ユーザー指示）。
- 経過観察の基準日: **2026-06-09**（In production 化から 7日後）。user_id=5 の token が失効せず Calendar sync が動作するかを確認
- 作業ツリーの無関係差分（OAuth 作業に混ぜない）: `docs/incident-2026-04-26-handoff.md` / `docs/archive-from-shift-keisan-app/` / `docs/business/`

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

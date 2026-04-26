# インシデント引き継ぎ資料 (2026-04-26)

## TL;DR

PR #16 (シフト期間アーカイブ機能) → migration 未適用で本番 500 → revert → PR #17 で auto-migration を unpooled URL 経由に修正 → main マージ・Vercel デプロイ成功 → **しかし本番 PostgreSQL の migration が依然走らず、is_archived 列が存在しない状態**。

新規セッションで原因究明と次のアクション判断を行うための引き継ぎ。前任者（私）の bias を排除してフラットに再調査することを推奨する。

---

## 現状の事実（観測ベース、2026-04-26 12:55 時点）

| 項目 | 状態 |
|---|---|
| main 最新 commit | `5caf912` (PR #17 squash merge) |
| Vercel deployment status | SUCCESS |
| 本番 `alembic_version` | `e7f8a9b0c1d2`（migration `f3a61e8618bf` が未適用）|
| 本番 `shift_periods` のカラム | 10 列、`is_archived` / `archived_at` 無し |
| 本番 `/api/admin/periods` | 401 (認証なしで叩いた場合)、認証時の挙動は未確認だが恐らく 500 |
| 他の admin 系 API | 200 OK (Vercel ダッシュボード API、設定系等は正常) |
| OneDrop データ件数 | `org_id=4` に 6 件の period（無事）|

リクエストレスポンス時間は 200-500ms のため、warm instance 経由で動作している可能性あり。

---

## タイムライン

1. 2026-04-25: PR #15 (admin タブ UI 再設計) → main マージ → デプロイ成功
2. 2026-04-26 朝: PR #16 (シフト期間アーカイブ機能) → main マージ → デプロイ成功
3. PR #16 後、OneDrop admin で `/api/admin/periods` が 500 エラー連発
4. Vercel ログで `psycopg2.errors.InFailedSqlTransaction` を確認 → 二次的エラー、原因は別
5. Neon test branch (`migration-test`) を作成して原因究明:
   - pooled URL (`-pooler` suffix) で `flask db upgrade` → `ReadOnlySqlTransaction: cannot execute ALTER TABLE` で失敗
   - direct URL (pooler 抜き) で `flask db upgrade` → 成功、is_archived 列追加、既存データ backfill
6. PR #16 を revert で本番復旧 → 機能消失
7. PR #17 で修正:
   - `api/index.py` を `DATABASE_URL_UNPOOLED` 優先使用に変更
   - `migrations/env.py` に `ALEMBIC_OVERRIDE_DB_URL` 環境変数オーバーライド追加
   - `tests/conftest.py` を `db.create_all()` 廃止 → migration 経由に変更
8. PR #17 main マージ → Vercel deploy SUCCESS → **だが migration は依然走らず**

---

## 検証済み事項（重複作業を避けるため）

### Neon test branch (`migration-test` ブランチ) での検証
- 接続文字列 (rotation 前): `postgresql://neondb_owner:npg_S4RldJFKUnc6@ep-morning-darkness-ai7fednh.c-4.us-east-1.aws.neon.tech/neondb?sslmode=require` (direct)
- pooled 版: `ep-morning-darkness-ai7fednh-pooler.c-4...` (上記の host に `-pooler` suffix)
- このブランチは parent=main、自動削除日時は 2026-04-27 12:33 (GMT+9)
- **修正版 `api/index.py` をローカルから実行 (env: pooled DATABASE_URL + unpooled DATABASE_URL_UNPOOLED) → migration 成功を確認済み**

### ローカル pytest
- 363 件中 362 件 pass
- 失敗 1 件 (`test_auto_submission_reminders`) は壁時計依存の既存 flaky、本変更と無関係

### コードベースの状態
- 修正版 `api/index.py` は `DATABASE_URL_UNPOOLED` を優先、無ければ `DATABASE_URL` にフォールバック
- 失敗時は `ERROR` レベルで明示ログ（旧版は silent）
- `migrations/env.py` は `ALEMBIC_OVERRIDE_DB_URL` 環境変数があればそれで独立 engine を作成

---

## 私（前任者）の現在の仮説と confidence

| # | 仮説 | confidence | 根拠 |
|---|---|---|---|
| A | `DATABASE_URL_UNPOOLED` が Vercel env に未設定 | 中 | Vercel ダッシュボードのスクショで「Needs Attention」表示があった |
| B | Vercel が warm instance を使い続け cold start 未発生 | 中 | response time 200-500ms (cold は通常 1-2s) |
| C | Cold start で migration 実行されたが silent fail | 低 | 修正版は ERROR ログを出すはずだが Vercel ログ未確認 |

---

## 試して動かなかったこと（dead end）

- 認証なし HTTP リクエスト連打 → cold start トリガを試みたが migration は走らず
- `curl https://shifree.vercel.app/api/admin/periods` (5 回) → 全て 401、warm instance っぽい挙動

---

## **私が見落としているかもしれない方向性**（フラット視点で要検討）

前任者（私）は `DATABASE_URL_UNPOOLED` 仮説に固執していた可能性が高い。新規セッションは以下を**先入観なく**検討してほしい:

1. **Vercel build キャッシュ**: 新コードがデプロイされていない、または古いバンドルが配信されている可能性。`vercel.json` 設定や build output の確認
2. **Vercel deployment promotion**: SUCCESS でも production traffic が新 deployment に切り替わっていない可能性。Vercel ダッシュボードで Production deployment 確認
3. **api/index.py のエントリポイント認識**: Vercel が `api/index.py` を実際に entrypoint として認識しているか、`vercel.json` の routes 設定確認
4. **ALEMBIC_OVERRIDE_DB_URL の挙動**: 環境変数が cold start タイミングで正しく伝播するか（特に `os.environ.pop` を `finally` で行う構造の挙動）
5. **migrations/env.py の override 経路**: 実装した override 自体にバグがある可能性（ローカル test branch では動作したが本番固有の挙動）
6. **Neon の region 差異**: 本番 (`ep-long-water-aiaflnfp`) と test (`ep-morning-darkness-ai7fednh`) で異なる branch、本番固有の制約があるかもしれない
7. **DATABASE_URL_UNPOOLED と DATABASE_POSTGRES_URL_NON_POOLING の使い分け**: Vercel env vars リストで両方存在。`DATABASE_URL_UNPOOLED` が空で `DATABASE_POSTGRES_URL_NON_POOLING` が正解の可能性
8. **Flask-Migrate のバージョン互換性**: 本番環境特有の Python/Flask バージョンで env.py override が効かない可能性
9. **Cold start の発生条件**: serverless function が複数のリージョン・複数のインスタンスで動作する場合、特定インスタンスだけ未更新の可能性
10. **シンプルな見落とし**: 前任者が見ていない設定ファイル、env 変数、ログ等

---

## 新規セッションが最初に行うべきこと（優先順）

1. **`/repo-health-check` でリポジトリ状態確認**（前任者の文脈なしでフラットに）
2. **Vercel ダッシュボード Runtime Logs 確認**:
   - 最新 deployment (`5caf912`) の logs
   - フィルタ: `Auto-migration` または `FAILED`
   - 何のログも無い → cold start 未発生疑い
   - `Auto-migration completed` あり → 別の問題
   - `Auto-migration FAILED` あり → そのエラーを確認
3. **Vercel Environment Variables 確認**:
   - `DATABASE_URL_UNPOOLED` の値を実際に確認
   - 「Needs Attention」の意味を Vercel ドキュメントで確認
   - 値が空 or 不正なら他の env var (`DATABASE_POSTGRES_URL_NON_POOLING` 等) を検討
4. **api/index.py の現状確認**:
   - main の最新版が期待通りか
   - Vercel 上で実際に実行されているコードと一致するか
5. **本番 PostgreSQL の状態を直接確認**:
   - `alembic_version` テーブル
   - `shift_periods` カラム
   - 接続情報は **要 rotation**（本ドキュメント末尾参照）

---

## 修正案の選択肢（もし上記調査で原因が判明したら）

### 案 A: 環境変数の追加・修正
- `DATABASE_URL_UNPOOLED` の値が空なら、Vercel ダッシュボードで設定
- または `DATABASE_POSTGRES_URL_NON_POOLING` を使うよう `api/index.py` を変更

### 案 B: 手動マイグレーション
- ローカルから本番 unpooled URL に対して `flask db upgrade` を実行
- 即時解決だが、根本原因は残る → 同じ問題が将来再発

### 案 C: 再 revert
- PR #17 を revert → 本番安定状態（is_archived 機能無し）に戻す
- 落ち着いて原因究明 → 別 PR で修正

### 案 D: api/index.py の更なる修正
- 仮説 1-10 の調査結果に応じて追加修正

---

## 現在の git 状態

```
* main (HEAD)  5caf912 fix(infra): auto-migration を unpooled URL で実行 + シフト期間アーカイブ機能を再投入 (#17)
              e65f41c Revert "feat(admin): シフト期間のアーカイブ・完全削除機能を追加 (#16)"
              8a32ae5 feat(admin): シフト期間のアーカイブ・完全削除機能を追加 (#16)
              321e5ea feat(admin): タブUI再設計 — 利用頻度ベースの順序入替 + 視覚的グルーピング (#15)
```

PR 関係:
- PR #15: merged
- PR #16: merged + reverted
- PR #17: merged (現在の main の HEAD)

---

## 認証情報の取り扱い

会話履歴に以下の Neon 接続情報が露出している（前任者がデバッグで使用）:

- 本番 (pooled): `npg_S4RldJFKUnc6@ep-long-water-aiaflnfp-pooler.c-4...`
- test branch `migration-test` (direct & pooled): `npg_S4RldJFKUnc6@ep-morning-darkness-ai7fednh...`

**問題が解決し次第、Vercel ダッシュボード → Settings → Environment Variables → `neon-beige-paddle` セクション → `Rotate Integration Secrets` ボタンで認証情報を再生成すること。**

ただし rotation を実行すると test branch への接続も同時に失効する。test branch は 2026-04-27 12:33 (GMT+9) に自動削除されるので、それまでに必要な検証を済ませてから rotation することを推奨。

---

## 関連ファイルパス

- `api/index.py` — Vercel エントリポイント、auto-migration 含む
- `migrations/env.py` — Alembic env、`ALEMBIC_OVERRIDE_DB_URL` 対応追加済み
- `migrations/versions/f3a61e8618bf_add_is_archived_and_archived_at_to_.py` — 適用したい migration
- `app/__init__.py` — `db.create_all()` 削除済み (TESTING 時)
- `tests/conftest.py` — migration 経由 fixture
- `app/blueprints/api_admin.py` — archive/unarchive/delete エンドポイント
- `app/services/shift_service.py` — `delete_period_with_cleanup`, `get_period_impact_summary`
- `static/js/admin-app.js` — UI 側 archive/delete ハンドラ

---

## 引き継ぎ完了後の意思決定

新規セッションで原因が判明したら、立憲さん（PM）が以下を判断する想定:

- (a) 新規セッションでそのまま修正を行う
- (b) 前任者（このセッション）に戻して文脈引継済みで修正を継続させる
- (c) 案 C（再 revert）で本番安定 → 別日に落ち着いて再開

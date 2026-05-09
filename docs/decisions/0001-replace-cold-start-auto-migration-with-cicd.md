# 0001. Cold start auto-migration を廃止し CI/CD で migration を実行する

## Status

Accepted (2026-05-09)

## Context

2026-05-09 に Onedrop 本番環境で `/api/admin/periods` 等が全件 500 化する障害が発生した。原因は PR #24 (`announcement_text` 列追加) と PR #26 (`staffing_requirements` テーブル追加) の 2 つの migration が production DB に**未適用**のまま、新コードが旧スキーマに対して SELECT を発行したことによる psycopg `UndefinedColumn` / `UndefinedTable`。

既存設計では `api/index.py` の `_run_auto_migration()` が Vercel Lambda の cold start 時に migration を実行する想定だったが、以下の構造的問題があった:

1. **アプリ起動とスキーマ変更が同責務** — migration 失敗時の影響範囲が広く、原因特定が困難
2. **失敗時の握り潰し** — 失敗を `logger.error` で記録するだけで起動継続。結果として「壊れたまま外部公開」する状態を生む
3. **観測性の脆弱性** — 過去に `disable_existing_loggers` の問題で migration ログが完全消失した経緯があり (PR #19 で対処)、再発リスクを抱えたまま運用していた
4. **環境変数依存の複雑性** — Neon の pooled / unpooled URL の使い分け、複数命名規則 (`DATABASE_URL_UNPOOLED` / `POSTGRES_URL_NON_POOLING` etc.) の優先順位を起動時ロジックで吸収しており前提条件が多い

今回の障害は migration 漏れそのものよりも、「**漏れても止まらない・気づけない構造**」が根本にある。

## Decision

Cold start auto-migration を**廃止**し、migration を **GitHub Actions の deploy 工程で明示実行**する方式に切り替える。

### Phase 1（最小実装、即時着手）

**やること:**
- `.github/workflows/db-migrate.yml`: `main` push 時に `flask db upgrade` を **unpooled URL** で実行
- migration 成功時のみ Vercel deploy hook を叩く
- migration 失敗時は Slack 通知 + deploy 阻止
- `api/index.py` から `_run_auto_migration()` を**廃止** (cold start で migration を走らせない)

**やらないこと（Non-goals for Phase 1）:**
- ❌ `flask db check` (alembic check) による model ↔ migration drift 検出
- ❌ migration 自動生成品質のチェック・テスト整備
- ❌ rollback 自動化 / restore point の CI 自動化
- ❌ deploy hook 後の実 deploy 完了待機・ヘルスチェック
- ❌ migration 実行を別 lambda / 別 service で分離

これらは Phase 2 以降の課題とする。Phase 1 は「runtime から migration 責務を完全に外す」だけにスコープを絞る。

### Phase 2（中期、Phase 1 が安定運用 1 ヶ月後）

- PR ステージで `flask db check` による drift 検出 (PR required check)
- migration 前の Neon restore point 自動取得
- より高度な監視 (workflow 失敗の Slack / PagerDuty 連携)
- model 変更があるのに migration が無いケースの検出

### Runtime 側の扱い（厳格な責務分離）

ADR 0002 とも関連するが、**runtime では一切 schema を変更しない**ことを明記する:

| 項目 | runtime での扱い |
|---|---|
| migration 実行 | ❌ 行わない（CI/CD のみ） |
| schema 変更 (ALTER / CREATE / DROP) | ❌ 一切行わない |
| 起動時の schema 整合性チェック | ✅ ADR 0002 で扱う (read-only) |
| schema mismatch 時の挙動 | ✅ ADR 0002 で扱う (admin API を 503) |

「保険として cold start migration を残す」という選択は**取らない**。runtime に残すと「いざという時の逃げ道」として依存され、再び CI/CD migration が形骸化する。明示的に削除する。

### Forward-only Migration 原則

本番運用では **forward-only migration** を原則とする:

- DDL を間違えた場合は新しい forward migration で訂正する（列削除 + 正しい列追加の新 revision）
- 本番復旧手段として `downgrade()` を使わない

ただし開発・検証用途として `downgrade()` 自体は残してよい:

- ローカル開発で migration の試行錯誤に使う
- staging / Neon branch でのリハーサルに使う

この区別をコードコメント or `migrations/README.md` に明記する。

### 移行リスクの吸収

- Phase 1 リリース時は新旧両方の migration 経路が一時併存しうる（Vercel deploy のタイミングと CI workflow merge のタイミングがずれた場合）。これは alembic が revision を見て skip するため冪等で安全
- 完全切替後は `_run_auto_migration` 呼出コード自体を削除して退路を断つ

## Consequences

### Positive
- migration 失敗が deploy 工程で完結 → 本番アプリは常に**整合したスキーマ前提で起動**
- 失敗時のロールバック判断が明示的 (= deploy しない)
- 観測性が GitHub Actions の workflow 結果ページで担保される
- 環境変数依存の複雑性が CI secret 管理に集約され、ランタイムから消える

### Negative
- migration 実行が GitHub Actions の availability に依存
- Vercel deploy hook の呼出順序が非自明（deploy hook が即時返すため、実 deploy 完了との timing 制御は別途必要、ただし Phase 1 では扱わない）

### Neutral / 留意事項
- 破壊的 migration (列削除 / NOT NULL 化 / 型変更) は CI 自動実行ではなく手動実行 + Neon branch でのリハーサル必須（Phase 2 で workflow 化検討）

## Related
- ADR 0002: Schema mismatch fail-fast middleware
- 障害記録: `docs/incident-2026-05-09-schema-drift.md` (起票予定)

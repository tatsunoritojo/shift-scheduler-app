# 0002. Schema mismatch 時に admin API を fail-fast する middleware を導入する

## Status

Accepted (2026-05-09)

## Context

ADR-0001 で migration を CI/CD に移し、deploy 前にスキーマを揃える方針を取る。しかしそれでも以下の状況は起こりうる:

1. CI/CD migration が失敗したが deploy が走ってしまった (workflow 設定ミス)
2. Vercel の rollback 機能で deploy だけ古いバージョンに戻され、DB は新スキーマのまま
3. 別の admin が手動で DB を変更した (revision drift)

これらの場合、**新コードが旧スキーマに当たる、または旧コードが新スキーマに当たる**状態でアプリが起動し、SELECT/INSERT が unpredictable に失敗する。2026-05-09 の障害は前者で、`/api/admin/periods` が `UndefinedColumn` を出し続けた。

現在の挙動は「アプリは起動するが endpoint で 500 を返し続ける」=「壊れた状態を外部公開する」になっている。

## Decision

スキーマ整合性チェックを起動時に行い、不整合時は管理 API (`/api/admin/*`) を **503 maintenance に強制切替**する middleware を導入する。

### 設計制約（前提として固定）

これらは実装詳細ではなく ADR レベルで決め切る:

1. **revision は起動時に 1 回だけ取得し、process-local cache に保持する**
2. **middleware は cache のみを見る** — リクエスト処理中の DB 参照は禁止
3. **`/health/schema` も cache 値を返す** — 都度 DB 参照しない
4. **revision 取得失敗時の挙動**: admin 系のみ 503 (`SCHEMA_CHECK_UNAVAILABLE`)、非 admin 系は通常通り処理
5. **緊急時 bypass**: env var `SCHEMA_GUARD_ENABLED=false` で guard を一時無効化できる。通常運用では有効化を前提とする

### Phase 1（最小実装、即時着手）

**Phase 1 の適用範囲は `/api/admin/*` のみ**に限定する:

- `worker` / `public` / `auth` 系には適用しない
- 今回の障害も管理系 API で顕在化したため、Phase 1 で守るべき重点はそこ
- 範囲を絞ることで、guard 自体の不具合があった場合の影響範囲も限定

**Phase 1 で実装するもの:**

```python
# app/__init__.py
EXPECTED_REVISION = 'd4310c2b47c0'  # 暫定。Phase 2 で env 注入、Phase 3 で alembic 自動取得

# app/middleware/schema_guard.py (新規)
def init_schema_guard(app):
    """app create 時に 1 回実行。process-local cache に保存。"""
    if os.environ.get('SCHEMA_GUARD_ENABLED', 'true').lower() == 'false':
        app.config['SCHEMA_GUARD_ENABLED'] = False
        return
    app.config['SCHEMA_GUARD_ENABLED'] = True
    try:
        actual = _read_alembic_version()  # SELECT version_num FROM alembic_version
        app.config['SCHEMA_ACTUAL_REVISION'] = actual
        app.config['SCHEMA_CHECK_FAILED'] = False
    except Exception as e:
        app.config['SCHEMA_ACTUAL_REVISION'] = None
        app.config['SCHEMA_CHECK_FAILED'] = True
        app.config['SCHEMA_CHECK_ERROR'] = str(e)
    app.config['SCHEMA_CHECKED_AT'] = datetime.utcnow()
    app.config['SCHEMA_MATCH'] = (
        not app.config['SCHEMA_CHECK_FAILED']
        and app.config['SCHEMA_ACTUAL_REVISION'] == EXPECTED_REVISION
    )

# /api/admin/* に対する before_request
@api_admin_bp.before_request
def reject_admin_if_mismatch():
    if not current_app.config.get('SCHEMA_GUARD_ENABLED', True):
        return  # bypass
    if current_app.config.get('SCHEMA_CHECK_FAILED'):
        return error_response(
            'スキーマ確認に失敗しました。一時的にメンテナンス中です。',
            503, code='SCHEMA_CHECK_UNAVAILABLE',
        )
    if not current_app.config.get('SCHEMA_MATCH'):
        return error_response(
            'メンテナンス中です（スキーマ整合性確認失敗）',
            503, code='SCHEMA_MISMATCH',
        )
```

**Phase 1 でやらないこと:**

- ❌ worker / owner / public 系 API への schema guard 適用
- ❌ revision を定期再読込する仕組み (起動時 1 回のみ)
- ❌ frontend 側のメンテナンス画面表示 (503 を返すだけ)
- ❌ Phase 2/3 の env 注入や alembic 自動取得

### `/health/schema` 返却項目（固定）

返却項目は以下に固定する:

```json
{
  "expected_revision": "d4310c2b47c0",
  "actual_revision_cached": "d4310c2b47c0",
  "match": true,
  "checked_at": "2026-05-09T03:00:00Z",
  "cache_age_seconds": 142
}
```

3 つの状況を区別できる:
- `actual_revision_cached: null` → **未取得** (起動時の DB アクセス失敗)
- `cache_age_seconds > 600` → **古い** (cache 更新メカニズム異常、Phase 1 では起動時 1 回なので 600 秒以上は通常)
- `match: false` → **不一致** (revision drift)

`/health/schema` 自体は schema guard の対象外（health check が guard で 503 になっては意味が無い）。

### Rollout 手順（2 段階）

**Step 1: 可視化のみ** (1 週間程度)
- `init_schema_guard` 実装 + `/health/schema` endpoint 実装
- `before_request` の 503 返却は**コメントアウト**したまま deploy
- `/health/schema` を Vercel Cron で 5 分おきに叩いて挙動観察
- log で "would have rejected" 相当の情報を出す

**Step 2: 遮断有効化**
- Step 1 の log で「不整合を観測したか」「false positive が無いか」を確認
- 問題なければ `before_request` の 503 返却を有効化
- `SCHEMA_GUARD_ENABLED=true` を本番 env に設定

「先に可視化してから遮断」の順序を守る。最初から一括導入すると、guard 自体の不具合で誤遮断するリスクがある。

### Phase 2（中期）: env 注入

- `EXPECTED_REVISION` 定数を CI/CD で env var に置き換え
- リリース時の更新漏れリスクを排除

### Phase 3（恒久）: alembic head の自動取得

```python
from alembic.script import ScriptDirectory
EXPECTED_REVISION = ScriptDirectory.from_config(alembic_cfg).get_current_head()
```

migration ファイル群から head を自動算出 → 人手介在ゼロ。

### 監視

- `/health/schema` を Vercel Cron で 5 分おきに叩き、`match=false` で即時通知
- `actual_revision_cached: null` で warning (起動時 DB アクセス失敗の検知)
- `cache_age_seconds > 600` は Phase 1 では正常範囲なのでアラート対象外

## Consequences

### Positive
- 「壊れた状態を外部公開」を構造的に防ぐ
- 障害時の影響範囲が明示的（503 + メンテナンス文言）になり、ユーザの混乱を抑える
- 観測装置として `/health/schema` が runtime とは独立に機能
- `SCHEMA_GUARD_ENABLED=false` で緊急避難路を確保

### Negative
- **Phase 1 の暫定定数は更新漏れ source**: head が進んだのに定数を更新し忘れると、正しい DB に対して不要な 503 を返す。Phase 2 の env 注入で解消するまでは運用注意必要
- 起動時に 1 回 DB 接続が増える（alembic_version 読取）。Lambda cold start に微小な遅延

### Neutral / 留意事項
- middleware は `/auth/*` を除外するので、ログインだけはできる → 「ログインしたが画面が動かない」状態。UX として明示的なメンテナンス画面表示が望ましいが Phase 1 では扱わない (frontend で SCHEMA_MISMATCH コード検知 → 全画面メンテナンス通知は別 issue)
- worker / owner 系は Phase 1 では schema guard 対象外。これらは新スキーマに依存していない経路で動くケースもあり得るため、Phase 2 で対象拡大を検討

## Related
- ADR 0001: Cold start auto-migration の廃止

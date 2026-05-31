# scripts/

シフリーの運用観測・トラブルシューティング用スクリプト群。

> 本 README は `scripts/db_monitor.py` の説明を主対象とします。`scripts/create_pilot_spreadsheet.py` など他のスクリプトは本 README の対象外で、それぞれ個別に保守されます。

## db_monitor.py

シフリー本番 PostgreSQL を **read-only** で観測するための CLI。Claude Code と管理者（東城立憲）の両方がトラブル時に同じツールで同じ観測ができるようにするのが狙い。

### 安全性（書き込み防止の多層防御）

1. **アプリ層**: 全クエリを `_assert_select_only` で検証。`SELECT` / `WITH` 以外は実行前に拒否
2. **DB 層**: 接続時に `default_transaction_read_only=on` を渡し、Postgres 側でも書き込みを拒否
3. **接続情報の非露出**: `DATABASE_URL` の値は標準出力にもエラー出力にも一切書き出さない。`.env.production.local` を `dotenv` 経由で環境変数に展開するのみ
4. **bind parameter**: 引数は SQL 文字列に直接埋めず、`text(sql), {...}` の bind parameter で渡す

### 前提

- `.env.production.local` がカレントディレクトリにあること
- 同ファイル内に `DATABASE_URL=postgresql://...` が定義されていること
- 本番 PostgreSQL に外部からネットワーク到達できる環境であること
- `sqlalchemy` と（推奨）`python-dotenv` が install 済み

### 使い方

```bash
# 組織メンバー一覧
python scripts/db_monitor.py members

# 個人情報をマスクして表示（会話履歴に残したくないとき）
python scripts/db_monitor.py --mask members

# 特定 schedule の Google カレンダー同期状況
python scripts/db_monitor.py sync 11

# シフト期間一覧と各期間の最新 schedule 状態
python scripts/db_monitor.py periods
```

### サブコマンドと観測項目の意味

#### `sync <schedule_id>`

指定 `shift_schedules.id` について、Google カレンダー同期状況の内訳を出力。

| 列 | 意味 |
|---|---|
| `total` | 総エントリ数 |
| `synced` | `calendar_event_id` がセットされている（同期成功） |
| `untouched` | `calendar_event_id IS NULL` かつ `sync_error IS NULL` かつ `last_sync_attempt_at IS NULL` — **まだ一度も同期試行されていない**。確定時の一括同期がタイムアウト等で完走しなかった、または確定後に追加されたエントリの可能性 |
| `attempted_no_error` | 試行したが `calendar_event_id` 未設定で `sync_error` もない過渡的状態。通常は瞬間的にしか観測されない |
| `errored` | `sync_error` がセットされている明確な失敗。`CREDENTIALS_EXPIRED` などが代表的 |

加えて未同期エントリの詳細（`shift_date`, `start_time`, `display_name`, `sync_error`, `last_sync_attempt_at`, `synced_at`）を出力。

#### `members`

全組織のメンバー一覧（`user × role`）。テスター名簿との照合や、想定外アカウントの混入チェックに使う。

#### `periods`

`shift_periods` の一覧と、各期間に紐づく最新 `shift_schedules` の `status` / `confirmed_at`。同名期間の重複や、確定済み期間の取りこぼし検知に使う。

### マスクモード

`--mask` を付けると `display_name` と `email` を伏字にする。

- `display_name`: 「久保田彩未」→「久*****」（先頭1文字 + 残りを `*` に）
- `email`: 「onedrop.kubota.ami@gmail.com」→「o****************i@gmail.com」（local part の最初と最後を残す）

通常は素のデータを見るが、画面共有やログ共有のときはマスクモードを使う。

### 注意事項

- 本スクリプトは本番 DB に接続する。実行は管理者（東城立憲）のみ
- `.env.production.local` は `.gitignore` 対象。値を共有しない
- スクリプト本体は `scripts/db_monitor.py` を `git` 管理する。実行時のログ出力は `.gitignore` に追加するなど別途管理する
- **出力には `display_name` / `email` など個人情報が平文で含まれる**。画面共有・ログ共有・別 AI レビュー等に渡す場合は原則 `--mask` を使うこと

### 拡張

新しい観測項目を増やすときは:

1. `cmd_xxx(con, args)` を追加（必ず `_assert_select_only(sql)` を呼ぶ）
2. `main()` の `sub.add_parser("xxx", ...)` でサブコマンド登録
3. この README に観測項目の意味を追記

"""シフリー本番DB read-only 監視ツール.

サブコマンド:
  sync <schedule_id>   - schedule の Google カレンダー同期状況
  members              - 組織メンバーと役割
  periods              - シフト期間一覧と最新 schedule の状態

オプション:
  --mask    個人情報（display_name / email）をマスクして表示

接続:
  カレントディレクトリの .env.production.local から DATABASE_URL を読み込む。
  接続文字列は標準出力にもエラー出力にも一切出力しない。

セーフガード（多層防御）:
  - 全クエリは SELECT もしくは WITH のみ。実行前に _assert_select_only で検証
  - Postgres 接続は default_transaction_read_only=on で開く（DB 側で書き込み拒否）
  - 引数はすべて bind parameter で渡し、SQL 文字列に値を直接埋め込まない

使用例:
  python scripts/db_monitor.py members
  python scripts/db_monitor.py --mask members
  python scripts/db_monitor.py sync 11
  python scripts/db_monitor.py periods
"""
import argparse
import os
import sys


def _load_database_url():
    """.env.production.local から DATABASE_URL を環境変数経由で読み込む。値は返り値以外で露出しない."""
    try:
        from dotenv import load_dotenv
        load_dotenv(".env.production.local")
    except ImportError:
        if os.path.exists(".env.production.local"):
            with open(".env.production.local", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def _assert_select_only(sql):
    """SELECT / WITH 以外のクエリを弾く。書き込み防止の第1層."""
    stripped = sql.strip().upper().lstrip("(")
    if not (stripped.startswith("SELECT") or stripped.startswith("WITH")):
        raise RuntimeError(f"書き込みクエリは禁止: {sql[:80]!r}")


def _mask_email(email, mask):
    if not mask or not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        return local[0] + "***@" + domain
    return local[0] + "*" * (len(local) - 2) + local[-1] + "@" + domain


def _mask_name(name, mask):
    if not mask or not name:
        return name
    if len(name) <= 1:
        return name + "*"
    return name[0] + "*" * (len(name) - 1)


def cmd_sync(con, args):
    """schedule の同期状況サマリ + 未同期エントリの詳細表示."""
    from sqlalchemy import text
    sid = args.schedule_id

    summary_sql = """
        SELECT
          COUNT(*) AS total,
          COUNT(calendar_event_id) AS synced,
          COUNT(*) FILTER (WHERE calendar_event_id IS NULL AND sync_error IS NULL AND last_sync_attempt_at IS NULL) AS untouched,
          COUNT(*) FILTER (WHERE calendar_event_id IS NULL AND sync_error IS NULL AND last_sync_attempt_at IS NOT NULL) AS attempted_no_error,
          COUNT(*) FILTER (WHERE sync_error IS NOT NULL) AS errored
        FROM shift_schedule_entries WHERE schedule_id = :sid
    """
    _assert_select_only(summary_sql)
    summ = con.execute(text(summary_sql), {"sid": sid}).mappings().first()
    print(f"\n=== schedule {sid} 同期状態の内訳 ===")
    if summ is None:
        print("(該当 schedule_id のエントリなし)")
        return
    print(dict(summ))

    unsynced_sql = """
        SELECT e.shift_date, e.start_time, e.end_time,
               u.display_name, u.email,
               e.sync_error, e.last_sync_attempt_at, e.synced_at
        FROM shift_schedule_entries e
        JOIN users u ON u.id = e.user_id
        WHERE e.schedule_id = :sid AND e.calendar_event_id IS NULL
        ORDER BY e.shift_date, e.start_time
    """
    _assert_select_only(unsynced_sql)
    rows = con.execute(text(unsynced_sql), {"sid": sid}).mappings().all()
    print(f"\n=== schedule {sid} 未同期エントリ ({len(rows)}件) ===")
    for r in rows:
        d = dict(r)
        d["display_name"] = _mask_name(d.get("display_name"), args.mask)
        d["email"] = _mask_email(d.get("email"), args.mask)
        print(d)


def cmd_members(con, args):
    """全組織のメンバー一覧 (user × role) を表示."""
    from sqlalchemy import text
    sql = """
        SELECT om.organization_id, o.name AS org_name,
               u.id AS user_id, u.display_name, u.email, om.role
        FROM organization_members om
        JOIN users u ON u.id = om.user_id
        JOIN organizations o ON o.id = om.organization_id
        ORDER BY om.organization_id, om.role, u.id
    """
    _assert_select_only(sql)
    rows = con.execute(text(sql)).mappings().all()
    print(f"\n=== organization_members ({len(rows)}件) ===")
    for r in rows:
        d = dict(r)
        d["display_name"] = _mask_name(d.get("display_name"), args.mask)
        d["email"] = _mask_email(d.get("email"), args.mask)
        print(d)


def cmd_periods(con, args):
    """シフト期間一覧と、各期間に紐づく最新 schedule の状態."""
    from sqlalchemy import text
    sql = """
        SELECT p.id, p.organization_id, p.name,
               p.start_date, p.end_date, p.status, p.is_archived,
               (SELECT s.status FROM shift_schedules s
                  WHERE s.shift_period_id = p.id
                  ORDER BY s.created_at DESC LIMIT 1) AS latest_schedule_status,
               (SELECT s.confirmed_at FROM shift_schedules s
                  WHERE s.shift_period_id = p.id
                  ORDER BY s.created_at DESC LIMIT 1) AS latest_confirmed_at
        FROM shift_periods p
        ORDER BY p.start_date
    """
    _assert_select_only(sql)
    rows = con.execute(text(sql)).mappings().all()
    print(f"\n=== shift_periods ({len(rows)}件) ===")
    for r in rows:
        print(dict(r))


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mask", action="store_true",
        help="display_name / email をマスクして表示（会話履歴に個人情報を残したくないとき）",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_sync = sub.add_parser("sync", help="schedule の Google カレンダー同期状況")
    p_sync.add_argument("schedule_id", type=int, help="shift_schedules.id")
    p_sync.set_defaults(func=cmd_sync)

    p_members = sub.add_parser("members", help="組織メンバーと役割の一覧")
    p_members.set_defaults(func=cmd_members)

    p_periods = sub.add_parser("periods", help="シフト期間一覧と最新 schedule の状態")
    p_periods.set_defaults(func=cmd_periods)

    args = parser.parse_args()

    url = _load_database_url()
    if not url:
        print("DATABASE_URL が読み込めませんでした (.env.production.local を確認)", file=sys.stderr)
        sys.exit(1)

    # DB 側にも read-only を強制（書き込み防止の第2層）
    from sqlalchemy import create_engine
    engine = create_engine(
        url,
        connect_args={"options": "-c default_transaction_read_only=on"},
    )
    with engine.connect() as con:
        args.func(con, args)


if __name__ == "__main__":
    main()

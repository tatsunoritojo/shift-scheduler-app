"""Schema integrity guard (ADR-0002).

起動時に DB の alembic revision を 1 回だけ取得し、process-local cache に保持する。
リクエスト中の DB 参照は禁止 (cache 値だけを見る)。

Step 1 (現状): 可視化のみ。/health/schema endpoint と起動ログ出力まで。
              before_request の 503 遮断はまだ有効化していない。
Step 2 (後続): /api/admin/* に対する 503 遮断を有効化する。

ADR-0002 §"設計制約" の 5 項目:
  1. revision は起動時に 1 回だけ取得し、process-local cache に保持
  2. middleware は cache のみを見る (per-request DB 参照禁止)
  3. /health/schema も cache 値を返す
  4. revision 取得失敗時の挙動: admin のみ 503 (SCHEMA_CHECK_UNAVAILABLE)
  5. 緊急時 bypass: SCHEMA_GUARD_ENABLED=false で無効化可能
"""

import logging
import os
from datetime import datetime

from sqlalchemy import text

from app.extensions import db

logger = logging.getLogger(__name__)


# Phase 1 (暫定): ハードコード定数。Phase 2 で env 注入、Phase 3 で alembic 自動取得。
# 更新責任: migration の head が進んだら必ずこの値も更新する。
# 値の確認: `flask db current` の出力末尾。
EXPECTED_REVISION = 'd4310c2b47c0'


def _read_alembic_version():
    """DB の alembic_version テーブルから現在の revision を読む。

    起動時に 1 回だけ呼ぶ。失敗は呼出側が拾う。
    """
    result = db.session.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).first()
    if result is None:
        return None
    return result[0]


def init_schema_guard(app):
    """app create 時に 1 回呼ぶ。app.config に schema 整合性情報を保存する。

    保存される config keys:
      SCHEMA_GUARD_ENABLED:    bool  guard を有効にするか (env: SCHEMA_GUARD_ENABLED)
      SCHEMA_EXPECTED:         str   期待 revision (= EXPECTED_REVISION)
      SCHEMA_ACTUAL_CACHED:    str   起動時に観測した DB の revision
      SCHEMA_MATCH:            bool  expected == actual_cached
      SCHEMA_CHECK_FAILED:     bool  DB から revision を読めなかった (接続エラー等)
      SCHEMA_CHECK_ERROR:      str   失敗時のエラーメッセージ
      SCHEMA_CHECKED_AT:       datetime  cache 取得時刻
      SCHEMA_STARTUP_TIME:     datetime  プロセス起動時刻 (= ほぼ checked_at と同じ)
    """
    enabled = os.environ.get('SCHEMA_GUARD_ENABLED', 'true').lower() != 'false'
    app.config['SCHEMA_GUARD_ENABLED'] = enabled
    app.config['SCHEMA_EXPECTED'] = EXPECTED_REVISION
    app.config['SCHEMA_STARTUP_TIME'] = datetime.utcnow()

    if not enabled:
        # 緊急避難路として guard を無効化された場合、最小限の状態だけ埋めて終了
        app.config['SCHEMA_ACTUAL_CACHED'] = None
        app.config['SCHEMA_MATCH'] = None
        app.config['SCHEMA_CHECK_FAILED'] = False
        app.config['SCHEMA_CHECK_ERROR'] = None
        app.config['SCHEMA_CHECKED_AT'] = datetime.utcnow()
        logger.warning("Schema guard disabled via SCHEMA_GUARD_ENABLED=false")
        return

    # Tests skip the live DB read entirely. SQLite test DB does not have
    # alembic_version (schema is created via metadata.create_all in tests).
    if app.config.get('TESTING'):
        app.config['SCHEMA_ACTUAL_CACHED'] = EXPECTED_REVISION
        app.config['SCHEMA_MATCH'] = True
        app.config['SCHEMA_CHECK_FAILED'] = False
        app.config['SCHEMA_CHECK_ERROR'] = None
        app.config['SCHEMA_CHECKED_AT'] = datetime.utcnow()
        return

    try:
        with app.app_context():
            actual = _read_alembic_version()
        app.config['SCHEMA_ACTUAL_CACHED'] = actual
        app.config['SCHEMA_MATCH'] = (actual == EXPECTED_REVISION)
        app.config['SCHEMA_CHECK_FAILED'] = False
        app.config['SCHEMA_CHECK_ERROR'] = None
    except Exception as e:
        app.config['SCHEMA_ACTUAL_CACHED'] = None
        app.config['SCHEMA_MATCH'] = False
        app.config['SCHEMA_CHECK_FAILED'] = True
        app.config['SCHEMA_CHECK_ERROR'] = str(e)
    app.config['SCHEMA_CHECKED_AT'] = datetime.utcnow()

    # Step 1: 可視化のみ。before_request での 503 遮断は Step 2 で有効化する。
    # ここでは「もし遮断していたら admin API は止まっていた」を確認できるように
    # ログを出す。
    if app.config['SCHEMA_CHECK_FAILED']:
        logger.error(
            "[schema-guard] Step 1 mode: would have returned 503 SCHEMA_CHECK_UNAVAILABLE "
            "for /api/admin/* (failed to read alembic_version: %s)",
            app.config['SCHEMA_CHECK_ERROR'],
        )
    elif not app.config['SCHEMA_MATCH']:
        logger.error(
            "[schema-guard] Step 1 mode: would have returned 503 SCHEMA_MISMATCH "
            "for /api/admin/* (expected=%s, actual=%s)",
            app.config['SCHEMA_EXPECTED'],
            app.config['SCHEMA_ACTUAL_CACHED'],
        )
    else:
        logger.info(
            "[schema-guard] Step 1 mode: schema match confirmed (revision=%s)",
            app.config['SCHEMA_EXPECTED'],
        )


def get_schema_status(app):
    """`/health/schema` の返却用 dict を組み立てる。

    cache 値だけを見る (per-request DB 参照禁止 — ADR-0002 §設計制約 #2/#3)。
    """
    checked_at = app.config.get('SCHEMA_CHECKED_AT')
    age_seconds = None
    if checked_at:
        age_seconds = int((datetime.utcnow() - checked_at).total_seconds())
    return {
        'expected_revision': app.config.get('SCHEMA_EXPECTED'),
        'actual_revision_cached': app.config.get('SCHEMA_ACTUAL_CACHED'),
        'match': app.config.get('SCHEMA_MATCH'),
        'check_failed': app.config.get('SCHEMA_CHECK_FAILED', False),
        'check_error': app.config.get('SCHEMA_CHECK_ERROR'),
        'checked_at': checked_at.isoformat() + 'Z' if checked_at else None,
        'cache_age_seconds': age_seconds,
        'guard_enabled': app.config.get('SCHEMA_GUARD_ENABLED'),
    }

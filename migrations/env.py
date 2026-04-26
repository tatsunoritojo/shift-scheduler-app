import logging
import os
from logging.config import fileConfig

from flask import current_app

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# disable_existing_loggers=False:
#   デフォルト True のままだと、本ファイル経由で Alembic が起動した瞬間に
#   既存の logger（特に api/index.py の `api.index` logger）が disabled に
#   される。結果として `_run_auto_migration()` の logger.info("Auto-migration
#   completed") も logger.error("Auto-migration FAILED") も本番ログから
#   完全に消え、migration が成功したのか失敗したのか観測する手段が
#   無くなる。Vercel での auto-migration 不発が長期に温存されたのは
#   この観測性欠落が直接の原因。
# encoding='utf-8':
#   alembic.ini に日本語コメントを書いた際、Windows の cp932 で読み込み
#   失敗するため明示。Vercel Linux のデフォルトは UTF-8 なので本番は
#   無くても動くが、開発環境差を吸収するために統一する。
fileConfig(config.config_file_name, disable_existing_loggers=False, encoding='utf-8')
logger = logging.getLogger('alembic.env')


def get_engine():
    # Allow auto-migration to use a different DB URL than the running app.
    # On Vercel + Neon, app runtime uses the pooled URL (DATABASE_URL) for
    # performance, but DDL must run on the unpooled URL because pooled
    # connections reject ALTER TABLE in transactions.
    override_url = os.environ.get('ALEMBIC_OVERRIDE_DB_URL')
    if override_url:
        from sqlalchemy import create_engine
        if override_url.startswith('postgres://'):
            override_url = override_url.replace('postgres://', 'postgresql://', 1)
        return create_engine(override_url)
    try:
        # this works with Flask-SQLAlchemy<3 and Alchemical
        return current_app.extensions['migrate'].db.get_engine()
    except (TypeError, AttributeError):
        # this works with Flask-SQLAlchemy>=3
        return current_app.extensions['migrate'].db.engine


def get_engine_url():
    try:
        return get_engine().url.render_as_string(hide_password=False).replace(
            '%', '%%')
    except AttributeError:
        return str(get_engine().url).replace('%', '%%')


# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
config.set_main_option('sqlalchemy.url', get_engine_url())
target_db = current_app.extensions['migrate'].db

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_metadata():
    if hasattr(target_db, 'metadatas'):
        return target_db.metadatas[None]
    return target_db.metadata


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url, target_metadata=get_metadata(), literal_binds=True
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    # this callback is used to prevent an auto-migration from being generated
    # when there are no changes to the schema
    # reference: http://alembic.zzzcomputing.com/en/latest/cookbook.html
    def process_revision_directives(context, revision, directives):
        if getattr(config.cmd_opts, 'autogenerate', False):
            script = directives[0]
            if script.upgrade_ops.is_empty():
                directives[:] = []
                logger.info('No changes in schema detected.')

    conf_args = current_app.extensions['migrate'].configure_args
    if conf_args.get("process_revision_directives") is None:
        conf_args["process_revision_directives"] = process_revision_directives

    connectable = get_engine()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=get_metadata(),
            **conf_args
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

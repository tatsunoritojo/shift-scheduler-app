# Gunicorn設定ファイル
import os

# Renderが提供するPORTを使用
bind = f"0.0.0.0:{os.environ.get('PORT', 10000)}"

# ワーカー設定
workers = 1
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2
max_requests = 1000
max_requests_jitter = 50

# ログ設定
accesslog = "-"
errorlog = "-"
loglevel = "info"

# プロセス設定
preload_app = True
daemon = False

# セキュリティ
limit_request_line = 4094
limit_request_fields = 100
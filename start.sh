#!/bin/bash

# Render起動スクリプト
echo "Starting Gunicorn server..."
echo "PORT: $PORT"
echo "Python version: $(python --version)"
echo "Gunicorn version: $(python -m gunicorn --version)"

# Gunicornでアプリケーションを起動
exec python -m gunicorn app_production:app \
    --bind 0.0.0.0:$PORT \
    --workers 1 \
    --timeout 30 \
    --keep-alive 2 \
    --max-requests 1000 \
    --preload
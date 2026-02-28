#!/usr/bin/env sh
# 本番起動: マイグレーション実行後に uvicorn を起動
# Railway / Render の Start Command に指定する場合: sh scripts/start.sh
set -e
cd "$(dirname "$0")/.."
uv run alembic upgrade head
exec uv run uvicorn src.ma_tool.main:app --host 0.0.0.0 --port "${PORT:-8000}"

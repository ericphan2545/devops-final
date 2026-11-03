#!/usr/bin/env bash
# In số việc và một mã kiểm tra (md5) của toàn bộ dữ liệu trong bảng todos.
# Chạy trước khi backup và sau khi restore: hai kết quả giống hệt nhau là restore đúng dữ liệu.
set -euo pipefail
cd "$(dirname "$0")/.."

set -a
source .env
set +a

docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tA -F ' | ' -c \
  "SELECT 'so viec: ' || count(*), 'ma kiem tra: ' || coalesce(md5(string_agg(id || ':' || title, ',' ORDER BY id)), 'trong') FROM todos"
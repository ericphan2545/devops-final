#!/usr/bin/env bash
# Khôi phục DB từ một file backup. GHI ĐÈ dữ liệu hiện tại.
# Cách dùng: bash scripts/restore.sh backups/todo-20261020-101500.sql.gz
set -euo pipefail
FILE=$(realpath "${1:?Cần đường dẫn file backup, ví dụ: bash scripts/restore.sh backups/todo-....sql.gz}")
cd "$(dirname "$0")/.."

set -a
source .env
set +a

echo "Sẽ GHI ĐÈ dữ liệu hiện tại bằng: $FILE"
read -r -p "Gõ yes để tiếp tục: " ANSWER
if [ "$ANSWER" != "yes" ]; then
  echo "Đã huỷ."
  exit 1
fi

gunzip -c "$FILE" | docker compose exec -T db psql -q -o /dev/null -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"
echo "Đã restore xong từ $FILE"
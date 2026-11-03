#!/usr/bin/env bash
# Sao lưu DB ra file nén trong thư mục backups/, giữ 7 bản mới nhất.
# Cách dùng (trên server, ở thư mục repo): bash scripts/backup.sh
set -euo pipefail
cd "$(dirname "$0")/.."

# Lấy POSTGRES_USER và POSTGRES_DB từ file .env
set -a
source .env
set +a

mkdir -p backups
FILE="backups/todo-$(date +%Y%m%d-%H%M%S).sql.gz"
TMP="$FILE.tmp"
trap 'rm -f "$TMP"' EXIT

# Ghi ra file tạm trước, xong hết mới đổi tên: lỗi giữa chừng thì không để lại file hỏng
docker compose exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists | gzip > "$TMP"
mv "$TMP" "$FILE"
echo "Đã backup: $FILE ($(du -h "$FILE" | cut -f1))"

# Chỉ giữ 7 bản mới nhất
ls -1t backups/todo-*.sql.gz | tail -n +8 | xargs -r rm --
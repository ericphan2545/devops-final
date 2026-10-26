#!/usr/bin/env bash
# Chạy trên server mỗi lần deploy (GitHub Actions gọi qua SSH, hoặc chạy tay).
# Việc: build + chạy bản mới, cho Nginx nhận container mới, rồi kiểm tra /health.
set -euo pipefail
cd "$(dirname "$0")/.."

# Gắn mã commit để trang web hiện đúng bản đang chạy
APP_VERSION=$(git rev-parse --short HEAD)
export APP_VERSION

docker compose up -d --build

# Nginx nhớ địa chỉ cũ của container app, nạp lại để nhận container mới
docker compose exec -T nginx nginx -s reload

# Chờ app trả lời /health (tối đa khoảng 60 giây)
for _ in $(seq 1 20); do
  if curl -fs http://localhost/health > /dev/null; then
    echo "Deploy OK: phiên bản $APP_VERSION"
    exit 0
  fi
  sleep 3
done

echo "Deploy LỖI: app không trả lời /health"
docker compose logs app --tail 30
exit 1
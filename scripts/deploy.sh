#!/usr/bin/env bash
# Chạy trên server mỗi lần deploy (GitHub Actions gọi qua SSH, hoặc chạy tay).
# Quy trình tuần 3:
#   1. Kiểm tra Compose, Prometheus/Alertmanager config và file webhook.
#   2. Build image app mới và chờ PostgreSQL sẵn sàng.
#   3. Chạy container migration một lần bằng tài khoản quản trị (không chạy Gunicorn).
#   4. Tạo/cấp lại quyền tối thiểu cho tài khoản ứng dụng (todo_app).
#   5. Khởi động 7 service, kiểm tra nginx -t rồi nạp lại Nginx.
#   6. Kiểm tra /health, /api/tasks, chặn /metrics (403) và /grafana/api/health.
set -euo pipefail
set +x
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "Deploy LỖI: chưa có file .env trên server." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
. ./.env
set +a

for required_var in POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB APP_DB_USER APP_DB_PASSWORD GRAFANA_ADMIN_PASSWORD GRAFANA_ROOT_URL; do
  if [ -z "${!required_var:-}" ]; then
    echo "Deploy LỖI: thiếu biến bắt buộc $required_var trong .env (hãy hoàn tất Bước 1 trước)." >&2
    exit 1
  fi
done

# Gắn mã commit để trang web hiện đúng bản đang chạy
APP_VERSION=$(git rev-parse --short HEAD)
export APP_VERSION

echo "[1/6] Kiểm tra cấu hình Docker Compose, Prometheus và Alertmanager..."
docker compose config --quiet
docker compose run --rm --no-deps --entrypoint /bin/promtool prometheus \
  check config /etc/prometheus/prometheus.yml
docker compose run --rm --no-deps --entrypoint /bin/amtool alertmanager \
  check-config /etc/alertmanager/alertmanager.yml
docker compose run --rm --no-deps --entrypoint /bin/sh alertmanager \
  -c 'test -f /etc/alertmanager/secrets/discord_webhook_url && test -r /etc/alertmanager/secrets/discord_webhook_url && test -s /etc/alertmanager/secrets/discord_webhook_url'

echo "[2/6] Build image app và bảo đảm PostgreSQL sẵn sàng..."
docker compose build app
docker compose up -d db

db_ready=0
for _ in $(seq 1 20); do
  if docker compose exec -T db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" > /dev/null 2>&1; then
    db_ready=1
    break
  fi
  sleep 2
done
if [ "$db_ready" -ne 1 ]; then
  echo "Deploy LỖI: PostgreSQL không sẵn sàng kịp thời." >&2
  docker compose logs db --tail 30
  exit 1
fi

echo "[3/6] Chạy migration một lần bằng tài khoản quản trị..."
DB_USER="$POSTGRES_USER" DB_PASSWORD="$POSTGRES_PASSWORD" \
  docker compose run --rm --no-deps -e DB_USER -e DB_PASSWORD app python migrate.py

echo "[4/6] Cấp quyền tối thiểu cho tài khoản ứng dụng ($APP_DB_USER)..."
docker compose exec -T -e APP_DB_USER -e APP_DB_PASSWORD db \
  sh /docker-entrypoint-initdb.d/20-app-user.sh

echo "[5/6] Khởi động 7 service và nạp lại cấu hình..."
docker compose up -d app alertmanager node-exporter prometheus grafana nginx
docker compose kill -s HUP prometheus alertmanager
docker compose exec -T nginx nginx -t
docker compose exec -T nginx nginx -s reload

echo "[6/6] Kiểm tra /health, API, chặn /metrics và Grafana..."
app_ready=0
for _ in $(seq 1 20); do
  if curl -fsS http://localhost/health > /dev/null && curl -fsS http://localhost/api/tasks > /dev/null; then
    app_ready=1
    break
  fi
  sleep 3
done

if [ "$app_ready" -ne 1 ]; then
  echo "Deploy LỖI: app không trả lời /health hoặc /api/tasks" >&2
  docker compose logs app --tail 30
  exit 1
fi

metrics_code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost/metrics)
if [ "$metrics_code" != "403" ]; then
  echo "Deploy LỖI: /metrics qua Nginx trả HTTP $metrics_code (mong đợi 403)" >&2
  exit 1
fi

grafana_ready=0
for _ in $(seq 1 20); do
  if curl -fsS http://localhost/grafana/api/health > /dev/null; then
    grafana_ready=1
    break
  fi
  sleep 3
done

if [ "$grafana_ready" -ne 1 ]; then
  echo "Deploy LỖI: Grafana không trả lời qua /grafana/api/health" >&2
  docker compose logs grafana --tail 30
  exit 1
fi

echo "Deploy OK: phiên bản $APP_VERSION"

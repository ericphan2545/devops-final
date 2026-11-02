#!/usr/bin/env bash
# Chạy trên server mỗi lần deploy (GitHub Actions gọi qua SSH, hoặc chạy tay).
# Thứ tự triển khai chuẩn Tuần 3 (a -> g):
#   a. Kiểm tra biến bắt buộc và cấu hình (Compose, promtool, amtool, file webhook).
#   b. Build image app mới và bảo đảm PostgreSQL sẵn sàng.
#   c. Chạy migration một lần bằng tài khoản quản trị (không chạy Gunicorn).
#   d. Cấp quyền tối thiểu cho tài khoản ứng dụng (todo_app).
#   e. Khởi động/cập nhật 7 service.
#   f. Kiểm tra cấu hình Nginx (nginx -t) rồi reload.
#   g. Chờ health/API và xác nhận các thành phần giám sát sẵn sàng & đã nạp cấu hình mới.
set -euo pipefail
set +x
cd "$(dirname "$0")/.."

non_blank() {
  [ -n "$(printf '%s' "${1:-}" | tr -d '[:space:]')" ]
}

fail_stage() {
  local stage="$1"
  local message="$2"
  echo "Deploy LỖI ở giai đoạn ${stage}: ${message}" >&2
  exit 1
}

echo "[a/g] Kiểm tra biến môi trường bắt buộc và cấu hình hệ thống..."
if [ ! -f .env ]; then
  fail_stage "[a/g]" "Chưa có file .env trên server (hãy hoàn tất Bước 1 trước)."
fi

if [ "$(wc -c < .env)" != "$(tr -d '\r' < .env | wc -c)" ]; then
  fail_stage "[a/g]" "File .env chứa ký tự xuống dòng Windows (CRLF). Hãy chuẩn hoá bằng: sed -i 's/\r$//' .env"
fi

set -a
# shellcheck disable=SC1091
. ./.env
set +a

for required_var in POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB APP_DB_USER APP_DB_PASSWORD GRAFANA_ADMIN_PASSWORD GRAFANA_ROOT_URL; do
  if ! non_blank "${!required_var:-}"; then
    fail_stage "[a/g]" "Biến bắt buộc $required_var bị thiếu hoặc đang để rỗng trong .env (hãy hoàn tất Bước 1 trước)."
  fi
done

if [ "$APP_DB_USER" = "$POSTGRES_USER" ]; then
  fail_stage "[a/g]" "APP_DB_USER ($APP_DB_USER) không được trùng tài khoản quản trị POSTGRES_USER ($POSTGRES_USER)."
fi

if [ ! -f db/app-user.sh ]; then
  fail_stage "[a/g]" "Không tìm thấy script cấp quyền db/app-user.sh."
fi

if [ ! -d secrets ]; then
  fail_stage "[a/g]" "Chưa có thư mục secrets/ trên server (hãy hoàn tất Bước 1 trước)."
fi

APP_VERSION="$(git rev-parse --short HEAD)"
export APP_VERSION

docker compose config --quiet || fail_stage "[a/g]" "Cấu hình docker-compose.yml không hợp lệ."

docker compose run --rm --no-deps --entrypoint /bin/promtool prometheus \
  check config /etc/prometheus/prometheus.yml \
  || fail_stage "[a/g]" "Cấu hình Prometheus hoặc luật cảnh báo (alerts.yml) không hợp lệ."

docker compose run --rm --no-deps --entrypoint /bin/amtool alertmanager \
  check-config /etc/alertmanager/alertmanager.yml \
  || fail_stage "[a/g]" "Cấu hình Alertmanager (alertmanager.yml) không hợp lệ."

docker compose run --rm --no-deps --entrypoint /bin/sh alertmanager \
  -c 'test -f /etc/alertmanager-secrets/discord_webhook_url && test -r /etc/alertmanager-secrets/discord_webhook_url && test -s /etc/alertmanager-secrets/discord_webhook_url' \
  || fail_stage "[a/g]" "Alertmanager (UID/GID 65534) không đọc được secrets/discord_webhook_url hoặc file đang rỗng."

echo "[b/g] Build image app và bảo đảm PostgreSQL sẵn sàng..."
docker compose build app || fail_stage "[b/g]" "Build Docker image cho app thất bại."
docker compose up -d db || fail_stage "[b/g]" "Khởi động container PostgreSQL (db) thất bại."

db_ready=0
for _ in $(seq 1 20); do
  if docker compose exec -T db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" > /dev/null 2>&1; then
    db_ready=1
    break
  fi
  sleep 2
done
if [ "$db_ready" -ne 1 ]; then
  docker compose logs db --tail 30 >&2 || true
  fail_stage "[b/g]" "PostgreSQL không sẵn sàng sau thời gian chờ."
fi

echo "[c/g] Chạy migration một lần bằng tài khoản quản trị..."
if ! DB_USER="$POSTGRES_USER" DB_PASSWORD="$POSTGRES_PASSWORD" \
  docker compose run --rm --no-deps -e DB_USER -e DB_PASSWORD app python migrate.py; then
  fail_stage "[c/g]" "Migration bằng tài khoản quản trị thất bại. Đã dừng deploy trước khi khởi động app mới."
fi

echo "[d/g] Cấp quyền tối thiểu cho tài khoản ứng dụng ($APP_DB_USER)..."
if ! docker compose exec -T \
  -e POSTGRES_USER="$POSTGRES_USER" \
  -e POSTGRES_DB="$POSTGRES_DB" \
  -e APP_DB_USER="$APP_DB_USER" \
  -e APP_DB_PASSWORD="$APP_DB_PASSWORD" \
  db sh < db/app-user.sh; then
  fail_stage "[d/g]" "Cấp quyền cho tài khoản ứng dụng ($APP_DB_USER) thất bại. Đã dừng deploy."
fi

echo "[e/g] Khởi động/cập nhật 7 service (app chạy bằng $APP_DB_USER)..."
if ! docker compose up -d app alertmanager node-exporter prometheus grafana nginx; then
  fail_stage "[e/g]" "Khởi động/cập nhật các service Docker Compose thất bại."
fi

echo "[f/g] Kiểm tra cấu hình Nginx (nginx -t) rồi nạp lại..."
if ! docker compose exec -T nginx nginx -t; then
  docker compose logs nginx --tail 30 >&2 || true
  fail_stage "[f/g]" "Kiểm tra cấu hình Nginx (nginx -t) thất bại."
fi
if ! docker compose exec -T nginx nginx -s reload; then
  docker compose logs nginx --tail 30 >&2 || true
  fail_stage "[f/g]" "Reload Nginx thất bại."
fi

echo "[g/g] Chờ /health, API và xác nhận các thành phần giám sát sẵn sàng & nạp cấu hình mới..."
app_ready=0
for _ in $(seq 1 20); do
  if curl -fsS http://localhost/health > /dev/null && curl -fsS http://localhost/api/tasks > /dev/null; then
    app_ready=1
    break
  fi
  sleep 3
done
if [ "$app_ready" -ne 1 ]; then
  docker compose logs app --tail 30 >&2 || true
  fail_stage "[g/g]" "App không trả lời /health hoặc /api/tasks."
fi

metrics_code="$(curl -s -o /dev/null -w '%{http_code}' http://localhost/metrics)"
if [ "$metrics_code" != "403" ]; then
  fail_stage "[g/g]" "/metrics qua Nginx trả HTTP $metrics_code (mong đợi 403)."
fi

# Chờ Prometheus, Alertmanager, node-exporter sẵn sàng trong mạng nội bộ rồi reload đồng bộ qua HTTP
# và đối chiếu trực tiếp metric *_config_last_reload_successful == 1 cùng danh sách alert rules.
monitoring_verified=0
for _ in $(seq 1 20); do
  if docker compose exec -T app python - <<'PY' > /dev/null 2>&1
import json
import re
import urllib.request

def fetch(url, method="GET"):
    req = urllib.request.Request(url, method=method, data=b"" if method == "POST" else None)
    with urllib.request.urlopen(req, timeout=4) as resp:
        assert 200 <= resp.status < 300, f"{url} returned {resp.status}"
        return resp.read().decode("utf-8", errors="replace")

app_metrics = fetch("http://localhost:8000/metrics")
assert re.search(r"^todo_db_up\s+1(?:\.0+)?$", app_metrics, re.M), "todo_db_up != 1"
assert "flask_http_request_total" in app_metrics, "missing flask_http_request_total"

node_metrics = fetch("http://node-exporter:9100/metrics")
assert "node_cpu_seconds_total" in node_metrics, "missing node_exporter CPU metric"

fetch("http://prometheus:9090/-/ready")
fetch("http://prometheus:9090/-/reload", method="POST")
prom_metrics = fetch("http://prometheus:9090/metrics")
assert re.search(r"^prometheus_config_last_reload_successful\s+1(?:\.0+)?$", prom_metrics, re.M)

rules_payload = json.loads(fetch("http://prometheus:9090/api/v1/rules"))
assert rules_payload.get("status") == "success"
rule_names = {
    rule["name"]
    for group in rules_payload.get("data", {}).get("groups", [])
    for rule in group.get("rules", [])
}
assert {"AppDown", "DatabaseDown", "HighMemory"}.issubset(rule_names), f"missing rules: {rule_names}"

fetch("http://alertmanager:9093/-/ready")
fetch("http://alertmanager:9093/-/reload", method="POST")
am_metrics = fetch("http://alertmanager:9093/metrics")
assert re.search(r"^alertmanager_config_last_reload_successful\s+1(?:\.0+)?$", am_metrics, re.M)
PY
  then
    monitoring_verified=1
    break
  fi
  sleep 3
done

if [ "$monitoring_verified" -ne 1 ]; then
  docker compose logs prometheus --tail 25 >&2 || true
  docker compose logs alertmanager --tail 25 >&2 || true
  docker compose logs node-exporter --tail 25 >&2 || true
  fail_stage "[g/g]" "Prometheus, Alertmanager hoặc node-exporter chưa sẵn sàng hoặc nạp cấu hình mới thất bại."
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
  docker compose logs grafana --tail 30 >&2 || true
  fail_stage "[g/g]" "Grafana không trả lời qua /grafana/api/health."
fi

running_count="$(docker compose ps --status running --services | wc -l | tr -d '[:space:]')"
if [ "$running_count" -ne 7 ]; then
  docker compose ps >&2 || true
  fail_stage "[g/g]" "Số service đang chạy là $running_count (mong đợi đúng 7 service)."
fi

echo "Deploy OK: phiên bản $APP_VERSION (7/7 service sẵn sàng)"

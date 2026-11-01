#!/usr/bin/env bash
# Bước 1 (Tuần 3): Chuẩn bị server EC2 trước khi merge cấu hình mới vào main.
# Thực hiện an toàn, chạy lặp lại được, không in mật khẩu hay URL webhook ra màn hình.
set -euo pipefail
set +x
if [ ! -f docker-compose.yml ]; then
  cd "$(dirname "$0")/.."
fi

echo "=== [1/6] Kiểm tra trạng thái hiện tại trên server ==="
git status --short
echo "Commit đang chạy: $(git rev-parse --short HEAD)"
docker compose ps
curl -fsS http://localhost/health
echo ""

if [ ! -f .env ]; then
  echo "LỖI: Không tìm thấy file .env tại $(pwd)" >&2
  exit 1
fi
chmod 600 .env

set -a
# shellcheck disable=SC1091
. ./.env
set +a

echo "=== [2/6] Backup dự phòng toàn bộ database trước khi thay đổi quyền ==="
umask 077
mkdir -p backups
chmod 700 backups
backup_file="backups/pre-week3-$(date -u +%Y%m%d_%H%M%S).dump"
tmp_backup="${backup_file}.tmp"
docker compose exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > "$tmp_backup"
docker compose exec -T db pg_restore --list < "$tmp_backup" > /dev/null
mv "$tmp_backup" "$backup_file"
chmod 600 "$backup_file"
ls -lh "$backup_file"

echo "=== [3/6] Bổ sung biến môi trường Tuần 3 vào .env (giữ nguyên mật khẩu DB quản trị cũ) ==="
append_if_missing() {
  local key="$1"
  local val="$2"
  if ! grep -q "^${key}=" .env; then
    printf '\n%s=%s\n' "$key" "$val" >> .env
    echo "Đã thêm ${key} vào .env (giá trị đã được ẩn)."
  else
    echo "Đã có sẵn ${key} trong .env (giữ nguyên)."
  fi
}

append_if_missing "APP_DB_USER" "todo_app"
append_if_missing "APP_DB_PASSWORD" "$(openssl rand -hex 16)"
append_if_missing "GRAFANA_ADMIN_PASSWORD" "${NEW_GRAFANA_PASSWORD:-$(openssl rand -hex 12)}"
append_if_missing "GRAFANA_ROOT_URL" "${NEW_GRAFANA_ROOT_URL:-http://todo-devops.duckdns.org/grafana/}"
chmod 600 .env

set -a
# shellcheck disable=SC1091
. ./.env
set +a

echo "=== [4/6] Cấu hình secrets/discord_webhook_url cho Alertmanager (UID/GID 65534) ==="
sudo install -d -m 750 -o root -g 65534 secrets

need_webhook=1
if sudo test -f secrets/discord_webhook_url && sudo test -s secrets/discord_webhook_url; then
  echo "File secrets/discord_webhook_url đã tồn tại và có dữ liệu."
  need_webhook=0
fi

if [ -n "${DISCORD_WEBHOOK_URL:-}" ]; then
  need_webhook=1
fi

if [ "$need_webhook" -eq 1 ]; then
  webhook_input="${DISCORD_WEBHOOK_URL:-}"
  if [ -z "$webhook_input" ]; then
    if [ -t 0 ]; then
      read -r -s -p "Dán Discord Webhook URL (ẩn khi nhập, nhấn Enter khi xong): " webhook_input
      echo ""
    else
      echo "LỖI: Chưa có secrets/discord_webhook_url. Hãy chạy trực tiếp trên terminal SSH hoặc truyền DISCORD_WEBHOOK_URL." >&2
      exit 1
    fi
  fi
  webhook_clean=$(printf '%s' "$webhook_input" | tr -d '\r\n ')
  case "$webhook_clean" in
    https://discord.com/api/webhooks/*|https://discordapp.com/api/webhooks/*) ;;
    *)
      echo "LỖI: URL webhook không đúng định dạng https://discord.com/api/webhooks/..." >&2
      exit 1
      ;;
  esac
  printf '%s' "$webhook_clean" | sudo tee secrets/discord_webhook_url > /dev/null
  unset webhook_input webhook_clean
fi

sudo chown root:65534 secrets secrets/discord_webhook_url
sudo chmod 750 secrets
sudo chmod 640 secrets/discord_webhook_url
sudo ls -ld secrets secrets/discord_webhook_url

docker run --rm \
  -v "$(pwd)/secrets:/etc/alertmanager/secrets:ro" \
  --entrypoint /bin/sh \
  prom/alertmanager:v0.28.1 \
  -c 'id && test -f /etc/alertmanager/secrets/discord_webhook_url && test -r /etc/alertmanager/secrets/discord_webhook_url && test -s /etc/alertmanager/secrets/discord_webhook_url && echo "Alertmanager secret read check: OK (noi dung khong in ra)"'

echo "=== [5/6] Đảm bảo schema mới nhất và tạo/cấp quyền user $APP_DB_USER ==="
if [ -f app/schema.sql ]; then
  docker compose exec -T db \
    psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" < app/schema.sql
fi

APP_USER_SCRIPT=""
if [ -f db/app-user.sh ]; then
  APP_USER_SCRIPT="$(cat db/app-user.sh)"
elif git rev-parse --verify origin/week-3-monitoring:db/app-user.sh > /dev/null 2>&1; then
  APP_USER_SCRIPT="$(git show origin/week-3-monitoring:db/app-user.sh)"
else
  echo "LỖI: Không tìm thấy db/app-user.sh (hãy git fetch origin week-3-monitoring trước)." >&2
  exit 1
fi

printf '%s\n' "$APP_USER_SCRIPT" | docker compose exec -T \
  -e POSTGRES_USER="$POSTGRES_USER" \
  -e POSTGRES_DB="$POSTGRES_DB" \
  -e APP_DB_USER="$APP_DB_USER" \
  -e APP_DB_PASSWORD="$APP_DB_PASSWORD" \
  db sh

echo "=== [6/6] Bảng minh chứng role và quyền của $APP_DB_USER (đã che bí mật) ==="
docker compose exec -T -e APP_DB_USER="$APP_DB_USER" db \
  psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<'SQL'
\getenv app_db_user APP_DB_USER

SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolinherit, rolcanlogin, rolreplication, rolbypassrls
FROM pg_catalog.pg_roles
WHERE rolname IN (current_user, :'app_db_user')
ORDER BY rolname;

SELECT
    :'app_db_user' AS role_name,
    has_database_privilege(:'app_db_user', current_database(), 'CONNECT') AS db_connect,
    has_database_privilege(:'app_db_user', current_database(), 'CREATE') AS db_create,
    has_database_privilege(:'app_db_user', current_database(), 'TEMP') AS db_temp,
    has_schema_privilege(:'app_db_user', 'public', 'USAGE') AS schema_usage,
    has_schema_privilege(:'app_db_user', 'public', 'CREATE') AS schema_create;

SELECT
    c.relname AS object_name,
    pg_catalog.pg_get_userbyid(c.relowner) AS owner,
    CASE WHEN c.relkind = 'S' THEN
        concat_ws(', ',
            CASE WHEN has_sequence_privilege(:'app_db_user', c.oid, 'USAGE') THEN 'USAGE' END,
            CASE WHEN has_sequence_privilege(:'app_db_user', c.oid, 'SELECT') THEN 'SELECT' END,
            CASE WHEN has_sequence_privilege(:'app_db_user', c.oid, 'UPDATE') THEN 'UPDATE' END
        )
    ELSE
        concat_ws(', ',
            CASE WHEN has_table_privilege(:'app_db_user', c.oid, 'SELECT') THEN 'SELECT' END,
            CASE WHEN has_table_privilege(:'app_db_user', c.oid, 'INSERT') THEN 'INSERT' END,
            CASE WHEN has_table_privilege(:'app_db_user', c.oid, 'UPDATE') THEN 'UPDATE' END,
            CASE WHEN has_table_privilege(:'app_db_user', c.oid, 'DELETE') THEN 'DELETE' END,
            CASE WHEN has_table_privilege(:'app_db_user', c.oid, 'TRUNCATE') THEN 'TRUNCATE' END
        )
    END AS app_privileges
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname IN (
      'todos',
      'todos_id_seq',
      'todo_operations',
      'todo_tombstones',
      'todo_categories',
      'todo_category_tombstones'
  )
ORDER BY c.relname;
SQL

echo "=== HOÀN TẤT BƯỚC 1: Server đã sẵn sàng để merge nhánh Tuần 3 vào main ==="

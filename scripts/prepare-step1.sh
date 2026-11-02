#!/usr/bin/env bash
# Bước 1 (Tuần 3): Chuẩn bị server EC2 trước khi merge/deploy cấu hình mới vào main.
# Đặc điểm an toàn:
#   - Chạy lặp lại được (idempotent), không ghi đè mật khẩu hay webhook hợp lệ một cách âm thầm.
#   - Báo lỗi rõ ràng nếu biến bắt buộc tồn tại trong .env nhưng đang để rỗng.
#   - Không in mật khẩu hay URL webhook ra màn hình/log (luôn tắt shell tracing set +x).
#   - Không phụ thuộc cứng vào tên nhánh Git tạm: hỗ trợ đọc file tại chỗ, từ thư mục
#     copy tạm (--app-user-script), hoặc từ bất kỳ Git ref nào (--git-ref / PREPARE_GIT_REF / FETCH_HEAD).
set -euo pipefail
set +x

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || pwd)"
APP_USER_SCRIPT_PATH="${APP_USER_SCRIPT_PATH:-}"
SCHEMA_SQL_PATH="${SCHEMA_SQL_PATH:-}"
PREPARE_GIT_REF="${PREPARE_GIT_REF:-}"

non_blank() {
  [ -n "$(printf '%s' "${1:-}" | tr -d '[:space:]')" ]
}

trim_outer_whitespace() {
  local s="${1:-}"
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  printf '%s' "$s"
}

has_env_key() {
  local key="$1"
  grep -Eq "^[[:space:]]*(export[[:space:]]+)?${key}=" .env
}

load_env() {
  set +x
  if [ "$(wc -c < .env)" != "$(tr -d '\r' < .env | wc -c)" ]; then
    echo "LỖI: File .env chứa ký tự xuống dòng Windows (CRLF). Hãy chuẩn hoá bằng: sed -i 's/\r$//' .env" >&2
    exit 1
  fi
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
}

is_valid_discord_webhook() {
  local candidate="${1:-}"
  local pattern='^https://(discord|discordapp)\.com/api/webhooks/[A-Za-z0-9_-]+/[A-Za-z0-9._-]+$'
  [ "${#candidate}" -ge 50 ] && [[ "$candidate" =~ $pattern ]]
}

check_existing_webhook_valid() {
  local webhook_file="${1:-secrets/discord_webhook_url}"
  local existing_raw=""
  local existing_trimmed=""

  if ! sudo test -f "$webhook_file" || ! sudo test -s "$webhook_file"; then
    return 1
  fi

  existing_raw="$(sudo cat "$webhook_file")" || return 1
  existing_trimmed="$(trim_outer_whitespace "$existing_raw")"
  unset existing_raw

  if is_valid_discord_webhook "$existing_trimmed"; then
    unset existing_trimmed
    return 0
  fi

  unset existing_trimmed
  return 1
}

configure_discord_webhook_secret() {
  local secrets_dir="${1:-secrets}"
  local webhook_file="$secrets_dir/discord_webhook_url"
  local need_write_webhook=0
  local webhook_input=""
  local webhook_clean=""

  sudo install -d -m 750 -o root -g 65534 "$secrets_dir"

  if sudo test -d "$webhook_file"; then
    echo "LỖI: $webhook_file đang là thư mục (có thể do Docker tự tạo khi mount thiếu file). Hãy xoá thư mục rỗng đó và tạo lại file webhook." >&2
    return 1
  fi

  if sudo test -e "$webhook_file" || sudo test -L "$webhook_file"; then
    if sudo test -L "$webhook_file" || ! sudo test -f "$webhook_file"; then
      echo "LỖI: $webhook_file không phải file thường hợp lệ." >&2
      return 1
    fi
    if check_existing_webhook_valid "$webhook_file"; then
      if [ "${FORCE_ROTATE_WEBHOOK:-0}" = "1" ]; then
        echo "FORCE_ROTATE_WEBHOOK=1 được bật: sẽ cập nhật lại $webhook_file."
        need_write_webhook=1
      else
        if [ -n "${DISCORD_WEBHOOK_URL:-}" ]; then
          echo "Giữ nguyên $webhook_file hợp lệ hiện có (không ghi đè âm thầm; đặt FORCE_ROTATE_WEBHOOK=1 nếu muốn thay webhook mới)."
        else
          echo "File $webhook_file đã tồn tại và hợp lệ (giữ nguyên)."
        fi
      fi
    else
      if [ "${FORCE_ROTATE_WEBHOOK:-0}" = "1" ]; then
        need_write_webhook=1
      else
        echo "LỖI: $webhook_file đã tồn tại nhưng rỗng hoặc sai định dạng Discord Webhook." >&2
        echo "Hãy kiểm tra lại file hoặc chạy lại với FORCE_ROTATE_WEBHOOK=1 để cập nhật webhook hợp lệ." >&2
        return 1
      fi
    fi
  else
    need_write_webhook=1
  fi

  if [ "$need_write_webhook" -eq 1 ]; then
    webhook_input="${DISCORD_WEBHOOK_URL:-}"
    if [ -z "$webhook_input" ]; then
      if [ -t 0 ]; then
        read -r -s -p "Dán Discord Webhook URL (ẩn khi nhập, nhấn Enter khi xong): " webhook_input
        echo ""
      else
        echo "LỖI: Chưa có $webhook_file. Hãy chạy trên terminal SSH tương tác hoặc truyền biến môi trường DISCORD_WEBHOOK_URL." >&2
        return 1
      fi
    fi
    webhook_clean="$(trim_outer_whitespace "$webhook_input")"
    unset webhook_input
    if ! is_valid_discord_webhook "$webhook_clean"; then
      unset webhook_clean
      echo "LỖI: Giá trị webhook không hợp lệ (cần dạng https://discord.com/api/webhooks/<id>/<token>)." >&2
      return 1
    fi
    printf '%s' "$webhook_clean" | sudo tee "$webhook_file" > /dev/null
    unset webhook_clean
  fi

  sudo chown root:65534 "$secrets_dir" "$webhook_file"
  sudo chmod 750 "$secrets_dir"
  sudo chmod 640 "$webhook_file"
  sudo ls -ld "$secrets_dir" "$webhook_file"
  return 0
}

resolve_helper_content() {
  local explicit_path="$1"
  local repo_rel_path="$2"
  local basename_file
  basename_file="$(basename "$repo_rel_path")"

  if [ -n "$explicit_path" ]; then
    if [ ! -f "$explicit_path" ]; then
      echo "LỖI: Không tìm thấy file được chỉ định: $explicit_path" >&2
      return 1
    fi
    cat "$explicit_path"
    return 0
  fi

  if [ -f "$repo_rel_path" ]; then
    cat "$repo_rel_path"
    return 0
  fi

  if [ -f "$SCRIPT_DIR/../$repo_rel_path" ]; then
    cat "$SCRIPT_DIR/../$repo_rel_path"
    return 0
  fi

  if [ -f "$SCRIPT_DIR/$basename_file" ]; then
    cat "$SCRIPT_DIR/$basename_file"
    return 0
  fi

  if [ -n "$PREPARE_GIT_REF" ] && git rev-parse --verify "${PREPARE_GIT_REF}:${repo_rel_path}" > /dev/null 2>&1; then
    git show "${PREPARE_GIT_REF}:${repo_rel_path}"
    return 0
  fi

  if git rev-parse --verify "FETCH_HEAD:${repo_rel_path}" > /dev/null 2>&1; then
    git show "FETCH_HEAD:${repo_rel_path}"
    return 0
  fi

  return 1
}

if [ "${PREPARE_STEP1_LIB_ONLY:-0}" = "1" ]; then
  return 0 2>/dev/null || exit 0
fi

while [ "$#" -gt 0 ]; do
  case "$1" in
    --app-user-script)
      APP_USER_SCRIPT_PATH="${2:-}"
      shift 2
      ;;
    --schema-sql)
      SCHEMA_SQL_PATH="${2:-}"
      shift 2
      ;;
    --git-ref)
      PREPARE_GIT_REF="${2:-}"
      shift 2
      ;;
    *)
      echo "LỖI: Tham số không hợp lệ: $1" >&2
      echo "Cách dùng: bash scripts/prepare-step1.sh [--git-ref <ref>] [--app-user-script <path>] [--schema-sql <path>]" >&2
      exit 1
      ;;
  esac
done

if [ ! -f docker-compose.yml ]; then
  if [ -f "$SCRIPT_DIR/../docker-compose.yml" ]; then
    cd "$SCRIPT_DIR/.."
  else
    echo "LỖI: Hãy đứng tại thư mục gốc của project trên server (ví dụ ~/devops-todo) khi chạy script." >&2
    exit 1
  fi
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
load_env

for admin_var in POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB; do
  if ! has_env_key "$admin_var"; then
    echo "LỖI: Thiếu biến quản trị DB bắt buộc $admin_var trong .env." >&2
    exit 1
  fi
  if ! non_blank "${!admin_var:-}"; then
    echo "LỖI: Biến quản trị DB $admin_var trong .env đang để rỗng." >&2
    exit 1
  fi
done

echo "=== [2/6] Backup dự phòng toàn bộ database trước khi thay đổi quyền/schema ==="
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

echo "=== [3/6] Kiểm tra và bổ sung biến môi trường Tuần 3 vào .env (không ghi đè giá trị cũ) ==="
ensure_week3_var() {
  local key="$1"
  local default_val="$2"

  if has_env_key "$key"; then
    if ! non_blank "${!key:-}"; then
      echo "LỖI: Biến $key đã tồn tại trong .env nhưng đang để rỗng. Hãy điền giá trị hợp lệ hoặc xoá dòng rỗng trong .env rồi chạy lại." >&2
      exit 1
    fi
    echo "Giữ nguyên $key hiện có trong .env (không ghi đè)."
  else
    if ! non_blank "$default_val"; then
      echo "LỖI: Giá trị khởi tạo cho $key bị rỗng." >&2
      exit 1
    fi
    if [ -s .env ] && [ -n "$(tail -c 1 .env)" ]; then
      printf '\n' >> .env
    fi
    printf '%s=%s\n' "$key" "$default_val" >> .env
    echo "Đã bổ sung $key vào .env (giá trị bí mật không in ra log)."
  fi
}

ensure_week3_var "APP_DB_USER" "todo_app"
ensure_week3_var "APP_DB_PASSWORD" "$(openssl rand -hex 16)"
ensure_week3_var "GRAFANA_ADMIN_PASSWORD" "${NEW_GRAFANA_PASSWORD:-$(openssl rand -hex 12)}"
ensure_week3_var "GRAFANA_ROOT_URL" "${NEW_GRAFANA_ROOT_URL:-http://todo-devops.duckdns.org/grafana/}"
chmod 600 .env
load_env

if [ "$APP_DB_USER" = "$POSTGRES_USER" ]; then
  echo "LỖI: APP_DB_USER ($APP_DB_USER) không được trùng tài khoản quản trị POSTGRES_USER ($POSTGRES_USER)." >&2
  exit 1
fi

echo "=== [4/6] Cấu hình secrets/discord_webhook_url cho Alertmanager (UID/GID 65534) ==="
configure_discord_webhook_secret "secrets"

docker run --rm \
  -v "$(pwd)/secrets:/etc/alertmanager-secrets:ro" \
  --entrypoint /bin/sh \
  prom/alertmanager:v0.28.1 \
  -c 'id && test -f /etc/alertmanager-secrets/discord_webhook_url && test -r /etc/alertmanager-secrets/discord_webhook_url && test -s /etc/alertmanager-secrets/discord_webhook_url && echo "Alertmanager secret read check: OK (noi dung khong in ra)"'

echo "=== [5/6] Bảo đảm schema đủ bảng và tạo/cấp quyền user $APP_DB_USER ==="
APP_USER_SCRIPT="$(resolve_helper_content "$APP_USER_SCRIPT_PATH" "db/app-user.sh")" || {
  echo "LỖI: Không tìm thấy db/app-user.sh." >&2
  echo "Để chuẩn bị Bước 1 trước khi merge vào main, hãy dùng 1 trong 2 cách:" >&2
  echo "  Cách 1 (qua Git fetch PR/nhánh, giữ nguyên nhánh main hiện tại):" >&2
  echo "    git fetch origin pull/<SO_PR>/head && PREPARE_GIT_REF=FETCH_HEAD bash <(git show FETCH_HEAD:scripts/prepare-step1.sh)" >&2
  echo "  Cách 2 (copy 2 script lên /tmp qua scp):" >&2
  echo "    APP_USER_SCRIPT_PATH=/tmp/app-user.sh bash /tmp/prepare-step1.sh" >&2
  exit 1
}

if SCHEMA_SQL_CONTENT="$(resolve_helper_content "$SCHEMA_SQL_PATH" "app/schema.sql" 2>/dev/null)"; then
  printf '%s\n' "$SCHEMA_SQL_CONTENT" | docker compose exec -T db \
    psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"
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

echo "=== HOÀN TẤT BƯỚC 1: Server đã sẵn sàng để merge/deploy cấu hình Tuần 3 ==="

#!/bin/bash
# Dựng server EC2 mới từ con số 0 (tương thích cấu hình 7 service của Tuần 3):
#   1. Cài Docker Engine & Docker Compose plugin.
#   2. Cấu hình cập nhật DuckDNS định kỳ (nếu điền DUCKDNS_TOKEN trong User data).
#   3. Clone repo và khởi tạo .env với mật khẩu ngẫu nhiên (không in bí mật vào log).
#   4. Nếu đã có hoặc điền DISCORD_WEBHOOK_URL hợp lệ: bảo đảm secrets/ (root:65534, 750)
#      và secrets/discord_webhook_url (root:65534, 640) không bị lệch quyền sau chown -R,
#      không ghi đè webhook hợp lệ đang có, rồi chạy scripts/deploy.sh.
#      Nếu chưa có webhook hợp lệ: dừng lại với hướng dẫn rõ ràng, KHÔNG báo "SETUP XONG".
# Xem tiến độ trên server: sudo tail -f /var/log/setup-server.log
set -euo pipefail
set +x

trim_outer_whitespace() {
  local s="${1:-}"
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  printf '%s' "$s"
}

is_valid_discord_webhook() {
  local candidate="${1:-}"
  local pattern='^https://(discord|discordapp)\.com/api/webhooks/[A-Za-z0-9_-]+/[A-Za-z0-9._-]+$'
  [ "${#candidate}" -ge 50 ] && [[ "$candidate" =~ $pattern ]]
}

prepare_setup_secrets() {
  local app_dir="$1"
  local webhook_env="${2:-}"
  local secrets_dir="$app_dir/secrets"
  local webhook_file="$secrets_dir/discord_webhook_url"
  local existing_raw=""
  local existing_trimmed=""
  local webhook_clean=""

  chown -R ubuntu:ubuntu "$app_dir"
  if [ -f "$app_dir/.env" ]; then
    chmod 600 "$app_dir/.env"
  fi

  mkdir -p "$secrets_dir"
  chown root:65534 "$secrets_dir"
  chmod 750 "$secrets_dir"

  if [ -d "$webhook_file" ]; then
    echo "DỪNG SETUP: $webhook_file đang là thư mục, không phải file webhook hợp lệ." >&2
    return 1
  fi

  if [ -e "$webhook_file" ] || [ -L "$webhook_file" ]; then
    if [ -L "$webhook_file" ] || [ ! -f "$webhook_file" ]; then
      echo "DỪNG SETUP: $webhook_file không phải file thường hợp lệ." >&2
      return 1
    fi
    chown root:65534 "$webhook_file"
    chmod 640 "$webhook_file"
  fi

  if [ -f "$webhook_file" ] && [ -s "$webhook_file" ]; then
    existing_raw="$(cat "$webhook_file")" || return 1
    existing_trimmed="$(trim_outer_whitespace "$existing_raw")"
    unset existing_raw
    if ! is_valid_discord_webhook "$existing_trimmed"; then
      unset existing_trimmed
      echo "DỪNG SETUP: $webhook_file đã tồn tại nhưng sai định dạng Discord Webhook." >&2
      return 1
    fi
    unset existing_trimmed
  elif [ -n "$webhook_env" ]; then
    webhook_clean="$(trim_outer_whitespace "$webhook_env")"
    if ! is_valid_discord_webhook "$webhook_clean"; then
      unset webhook_clean
      echo "DỪNG SETUP: DISCORD_WEBHOOK_URL không đúng định dạng https://discord.com/api/webhooks/<id>/<token>." >&2
      echo "Hãy SSH vào server, chạy: cd $app_dir && bash scripts/prepare-step1.sh && bash scripts/deploy.sh" >&2
      return 1
    fi
    printf '%s' "$webhook_clean" > "$webhook_file"
    unset webhook_clean
  fi

  if [ ! -f "$webhook_file" ] || [ -d "$webhook_file" ] || [ ! -s "$webhook_file" ]; then
    echo "CHƯA HOÀN TẤT SETUP: Đã cài Docker, tải repo và tạo .env, nhưng chưa có secrets/discord_webhook_url cho Alertmanager." >&2
    echo "Hướng dẫn hoàn tất trên server:" >&2
    echo "  1. SSH vào EC2 bằng tài khoản ubuntu" >&2
    echo "  2. cd $app_dir" >&2
    echo "  3. Lưu Discord webhook và kiểm tra Bước 1: bash scripts/prepare-step1.sh (hoặc ghi vào secrets/discord_webhook_url với quyền root:65534 640)" >&2
    echo "  4. Triển khai đủ 7 service: bash scripts/deploy.sh" >&2
    return 1
  fi

  chown root:65534 "$secrets_dir" "$webhook_file"
  chmod 750 "$secrets_dir"
  chmod 640 "$webhook_file"
  return 0
}

if [ "${SETUP_SERVER_LIB_ONLY:-0}" = "1" ]; then
  return 0 2>/dev/null || exit 0
fi

install -m 600 /dev/null /var/log/setup-server.log
exec > /var/log/setup-server.log 2>&1

REPO_URL="https://github.com/ericphan2545/devops-final.git"
APP_DIR="/home/ubuntu/devops-todo"
# Điền token/webhook khi dán vào ô "User data" của EC2; KHÔNG commit giá trị thật vào Git.
DUCKDNS_DOMAIN="todo-devops"   # -> todo-devops.duckdns.org
DUCKDNS_TOKEN=""
DISCORD_WEBHOOK_URL=""

echo "[1/4] Cài đặt Docker Engine và Docker Compose plugin..."
apt-get update
apt-get install -y ca-certificates curl git openssl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
usermod -aG docker ubuntu

# 1b. Cập nhật DuckDNS ngay, lúc khởi động lại và mỗi 5 phút (không bật set -x để tránh lộ token)
if [ -n "$DUCKDNS_DOMAIN" ] && [ -n "$DUCKDNS_TOKEN" ]; then
  echo "[1b/4] Cấu hình cập nhật DuckDNS cho ${DUCKDNS_DOMAIN}.duckdns.org..."
  cat > /usr/local/sbin/duckdns-update <<EOF
#!/bin/sh
curl -fsS --retry 10 --retry-delay 5 --retry-all-errors \
  "https://www.duckdns.org/update?domains=$DUCKDNS_DOMAIN&token=$DUCKDNS_TOKEN&ip=" -o /var/log/duckdns.log
EOF
  chmod 700 /usr/local/sbin/duckdns-update
  printf '%s\n' "@reboot root /usr/local/sbin/duckdns-update" \
    "*/5 * * * * root /usr/local/sbin/duckdns-update" > /etc/cron.d/duckdns
  /usr/local/sbin/duckdns-update
fi

echo "[2/4] Tải mã nguồn về $APP_DIR..."
if [ ! -d "$APP_DIR" ]; then
  git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

echo "[3/4] Khởi tạo .env và thư mục secrets (không in giá trị mật khẩu ra log)..."
if [ ! -f .env ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    if [[ "$line" =~ ^([A-Z_]*PASSWORD)= ]]; then
      printf '%s=%s\n' "${BASH_REMATCH[1]}" "$(openssl rand -hex 16)"
    elif [[ "$line" =~ ^GRAFANA_ROOT_URL= ]] && [ -n "$DUCKDNS_DOMAIN" ]; then
      printf 'GRAFANA_ROOT_URL=http://%s.duckdns.org/grafana/\n' "$DUCKDNS_DOMAIN"
    else
      printf '%s\n' "$line"
    fi
  done < .env.example > .env
  chmod 600 .env
fi

prepare_setup_secrets "$APP_DIR" "$DISCORD_WEBHOOK_URL"

echo "[4/4] Triển khai và kiểm tra toàn bộ 7 service qua scripts/deploy.sh..."
sudo -u ubuntu bash "$APP_DIR/scripts/deploy.sh"
echo "SETUP XONG"

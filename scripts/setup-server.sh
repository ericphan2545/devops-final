#!/bin/bash
# Dựng server từ con số 0: cài Docker, tải repo, tạo .env, chạy app.
# Cách dùng: dán TOÀN BỘ file này vào ô "User data" khi tạo EC2 (Ubuntu).
# Máy tự chạy 1 lần lúc khởi động đầu tiên, mất khoảng 5 phút.
# Xem tiến độ / lỗi trên server: sudo tail -f /var/log/setup-server.log
set -euxo pipefail
# Log có mật khẩu DB và token DuckDNS (do set -x in ra), nên chỉ root đọc được
install -m 600 /dev/null /var/log/setup-server.log
exec > /var/log/setup-server.log 2>&1

REPO_URL="https://github.com/ericphan2545/devops-final.git"
APP_DIR="/home/ubuntu/devops-todo"
# Tên miền DuckDNS trỏ về server, để secret EC2_HOST không phải đổi khi IP đổi.
# Điền lúc dán vào User data; KHÔNG commit token (repo public). Để trống thì bỏ qua.
DUCKDNS_DOMAIN="todo-devops"   # -> todo-devops.duckdns.org
DUCKDNS_TOKEN=""

# 1. Cài Docker theo hướng dẫn chính thức của Docker
apt-get update
apt-get install -y ca-certificates curl git
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
usermod -aG docker ubuntu   # user ubuntu chạy docker không cần sudo

# 1b. Cập nhật DuckDNS ngay, lúc khởi động lại và mỗi 5 phút (IP công khai có thể đổi)
#     ip= để trống: DuckDNS lấy IP của chính request, tức IP công khai của server.
if [ -n "$DUCKDNS_DOMAIN" ] && [ -n "$DUCKDNS_TOKEN" ]; then
  cat > /usr/local/sbin/duckdns-update <<EOF
#!/bin/sh
curl -fsS --retry 10 --retry-delay 5 --retry-all-errors \
  "https://www.duckdns.org/update?domains=$DUCKDNS_DOMAIN&token=$DUCKDNS_TOKEN&ip=" -o /var/log/duckdns.log
EOF
  chmod 700 /usr/local/sbin/duckdns-update   # file chứa token, chỉ root đọc được
  # Mỗi 5 phút nữa, vì Elastic IP thường được gắn SAU lần khởi động đầu
  printf '%s\n' "@reboot root /usr/local/sbin/duckdns-update" \
    "*/5 * * * * root /usr/local/sbin/duckdns-update" > /etc/cron.d/duckdns
  /usr/local/sbin/duckdns-update
fi

# 2. Tải code
if [ ! -d "$APP_DIR" ]; then
  git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

# 3. Tạo .env từ .env.example, mỗi dòng *_PASSWORD được thay bằng mật khẩu ngẫu nhiên
#    Xem mật khẩu sau này: cat ~/devops-todo/.env
if [ ! -f .env ]; then
  while IFS= read -r line; do
    if [[ "$line" =~ ^([A-Z_]*PASSWORD)= ]]; then
      echo "${BASH_REMATCH[1]}=$(openssl rand -hex 16)"
    else
      echo "$line"
    fi
  done < .env.example > .env
  chmod 600 .env
fi
chown -R ubuntu:ubuntu "$APP_DIR"

# 4. Chạy app
sudo -u ubuntu docker compose up -d --build
echo "SETUP XONG"

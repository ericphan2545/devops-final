# Tuần 4 — Backup, Restore và Bảo mật

**Phụ trách:** Huỳnh Hữu Như Mẫn — MSSV 23090020 (Người số 3)  
**Phạm vi:** Đo số liệu thực nghiệm sao lưu/khôi phục (3 lần), phối hợp diễn tập Sự cố 2 (Sai mật khẩu DB), kiểm định an toàn bảo mật (UFW, SSH, Git Secrets, phân quyền `todo_app`) và xây dựng phương pháp đối chiếu dữ liệu hai lớp.

---

## 0. Quy tắc chung & Chuẩn bị môi trường

1. **Chuẩn bị môi trường:**
   - Server EC2: `ssh ubuntu@todo-devops.duckdns.org`, di chuyển vào thư mục `cd ~/devops-todo`.
   - Máy cá nhân: Mở PowerShell tại thư mục repo `devops-final`.
   - Trình duyệt: Mở trang chính `http://todo-devops.duckdns.org/` bằng **cửa sổ ẩn danh mới** để tránh bản lưu cache.
2. **Nguyên tắc an toàn:**
   - Không thực hiện push lên nhánh `main` trong lúc diễn tập trên server.
   - Tuyệt đối không in nội dung file `.env` ra màn hình (không dùng `cat .env` hay mở `nano .env` khi đang quay/chụp màn hình) để bảo vệ token webhook Discord và mật khẩu DB.
   - Thao tác lệnh đo thời gian kèm prefix `date '+%F %T' &&` để hiển thị mốc thời gian thực tế trong Terminal.

---

## 1. Đo số liệu thực nghiệm Backup & Restore (3 Lần)

### Mục tiêu:
Sao lưu dữ liệu, giả lập mất toàn bộ bảng `todos`, tiến hành khôi phục bằng `restore.sh`, đối chiếu số lượng bản ghi (14 công việc) và mã kiểm tra MD5 checksum (`55ed94880f7cf39374705f80b0c86e21`).

### Các bước thực hiện lệnh trên Server EC2:

```bash
# ---------------------------------------------------------
# LẦN 1
# ---------------------------------------------------------
date '+%F %T' && bash scripts/db-check.sh
# Kỳ vọng: so viec: 14 | ma kiem tra: 55ed94880f7cf39374705f80b0c86e21

bash scripts/backup.sh
# Kỳ vọng: Đã backup: backups/todo-YYYYMMDD-HHMMSS.sql.gz

docker compose exec db psql -U todo -d todo -c "DELETE FROM todos;"
bash scripts/db-check.sh
# Kỳ vọng: so viec: 0 | ma kiem tra: trong

time bash scripts/restore.sh backups/$(ls -t backups/ | head -n 1)
# Nhập 'yes' khi được hỏi xác nhận. Ghi lại dòng time real (Ví dụ: real 0m3.081s)

bash scripts/db-check.sh
# Kỳ vọng: so viec: 14 | ma kiem tra: 55ed94880f7cf39374705f80b0c86e21

# ---------------------------------------------------------
# LẦN 2 & LẦN 3: Lặp lại chính xác chuỗi lệnh trên
# ---------------------------------------------------------
```

### Bảng tổng hợp số liệu thực nghiệm (Bàn giao Người số 2 & 4):

| Lần | Trạng thái trước Backup | Trạng thái sau Restore | Thời gian Restore (`real`) | MD5 Checksum trùng khớp |
| :---: | :--- | :--- | :---: | :---: |
| **Lần 1** | `so viec: 14 \| ma: 55ed9488...` | `so viec: 14 \| ma: 55ed9488...` | `0m3.081s` | 100% |
| **Lần 2** | `so viec: 14 \| ma: 55ed9488...` | `so viec: 14 \| ma: 55ed9488...` | `0m2.756s` | 100% |
| **Lần 3** | `so viec: 14 \| ma: 55ed9488...` | `so viec: 14 \| ma: 55ed9488...` | `0m2.270s` | 100% |
| **Trung bình** | — | — | **`0m2.702s`** | **100%** |

---

## 2. Diễn tập Sự cố 2 — Sai mật khẩu DB (`APP_DB_PASSWORD`)

*(Phối hợp cùng Người số 1 — Đặng Vĩnh Quang)*

### Mô tả & Triệu chứng:
Đổi mật khẩu kết nối DB của ứng dụng trong `.env` sang chuỗi sai. Trình duyệt truy cập web báo lỗi **HTTP 503 (Cơ sở dữ liệu chưa sẵn sàng)**. Panel App trên Grafana vẫn `UP`, nhưng panel Database báo `DOWN`. Bot Discord gửi cảnh báo `[FIRING] DatabaseDown` sau ~1.5 phút.

### Quy trình 4 bước diễn tập trên EC2:

1. **Gây lỗi (Trigger Fault):**
   ```bash
   date '+%F %T' && sed -i 's/^APP_DB_PASSWORD=.*/APP_DB_PASSWORD=sai_mat_khau_123/' .env
   docker compose up -d app
   ```
2. **Quan sát & Kiểm tra (Observe):**
   - Trình duyệt ẩn danh vào `http://todo-devops.duckdns.org/` $\rightarrow$ Nhận lỗi **HTTP 503**.
   - Chờ kênh Discord `#canh-bao` nhận tin nhắn **`[FIRING:1] DatabaseDown`**. Chụp lại màn hình.
3. **Khoanh vùng lỗi (Isolate):**
   ```bash
   # Log ở container App (Thấy lỗi kết nối DB)
   docker compose logs app --tail 20 | grep -i "OperationalError"
   # Output: ERROR in app: Database request failed: OperationalError

   # Log ở container DB (Thấy DB từ chối mật khẩu user todo_app)
   docker compose logs db --tail 20 | grep -i "password authentication failed"
   # Output: FATAL: password authentication failed for user "todo_app"
   ```
4. **Khôi phục hệ thống (Recover):**
   ```bash
   date '+%F %T' && sed -i 's/^APP_DB_PASSWORD=.*/APP_DB_PASSWORD=todo_pass/' .env
   bash scripts/deploy.sh
   ```
   - Kiểm tra lại trang web $\rightarrow$ Nhận HTTP 200 OK.
   - Chờ Discord thông báo **`[RESOLVED] DatabaseDown`**. Chụp lại màn hình.

---

## 3. Kiểm định Bảo mật Hệ thống (Security Audit)

### 3.1. Tường lửa UFW & Cấu hình SSH (Thực hiện trên EC2)
```bash
# Kiểm tra UFW Status (Chỉ ALLOW 22/tcp OpenSSH và 80/tcp HTTP)
sudo ufw status verbose

# Kiểm tra SSH không cho đăng nhập bằng mật khẩu
sudo sshd -T | grep -E "^(passwordauthentication|permitrootlogin)"
# Kỳ vọng: passwordauthentication no | permitrootlogin without-password (hoặc no)
```

### 3.2. Quét cổng công khai & Git Secrets (Thực hiện trên Laptop / PowerShell)
```powershell
# Quét cổng mở/đóng từ bên ngoài
Test-NetConnection todo-devops.duckdns.org -Port 80   # Kết quả: True (Cổng HTTP mở)
Test-NetConnection todo-devops.duckdns.org -Port 5432 # Kết quả: False (Cổng PostgreSQL bị chặn)
Test-NetConnection todo-devops.duckdns.org -Port 3000 # Kết quả: False (Cổng Grafana bị chặn)

# Quét cây thư mục Git kiểm tra rò rỉ bí mật
git ls-files | Select-String -Pattern "(\.env$|^secrets/|^backups/)"
# Kỳ vọng: Không in ra tên file nào (Cây Git sạch 100%)
```

### 3.3. Kiểm thử phân quyền hẹp của user DB `todo_app` (Thực hiện trên EC2)
Chạy 3 câu lệnh vượt quyền quản trị bằng user `todo_app` để chứng minh PostgreSQL chặn các thao tác phá hoại:
```bash
docker compose exec db psql -U todo_app -d todo -c "DROP TABLE todos;"
# Output: ERROR: must be owner of table todos

docker compose exec db psql -U todo_app -d todo -c "TRUNCATE todos;"
# Output: ERROR: permission denied for table todos

docker compose exec db psql -U todo_app -d todo -c "CREATE TABLE thu (id int);"
# Output: ERROR: permission denied for schema public
```

---

## 4. Phương pháp đối chiếu dữ liệu hai lớp (Double-Verification)

Để chứng minh dữ liệu sau khi khôi phục từ bản sao lưu hoàn toàn toàn vẹn và khớp 100% với ứng dụng thực tế, nhóm áp dụng cơ chế xác minh 2 lớp:

1. **Lớp 1 — Đối chiếu tầng Database (Machine-level Integrity):**
   - Chạy script `bash scripts/db-check.sh` để kiểm tra đếm dòng `SELECT COUNT(*) FROM todos;` và tính mã băm `md5sum` trên nội dung dữ liệu.
   - Kết quả: Đạt chính xác **14 bản ghi** và chuỗi hash MD5 **`55ed94880f7cf39374705f80b0c86e21`** trùng khớp tuyệt đối trước khi backup và sau khi restore.
2. **Lớp 2 — Đối chiếu tầng Ứng dụng (App/UI Level Integrity):**
   - Truy cập giao diện web `http://todo-devops.duckdns.org/` bằng trình duyệt ẩn danh.
   - Xác nhận Flask App render đủ danh sách **14 thẻ công việc** trên màn hình người dùng, kết nối DB qua tài khoản `todo_app` hoạt động ổn định và không phát sinh lỗi giao diện.

---

## 5. Danh mục minh chứng & Bàn giao tài nguyên

### 5.1. Bộ ảnh minh chứng (Lưu tại `docs/evidence/week-4/security-backup/`)
- `01-backup-restore-3runs.png`: Ảnh chụp terminal chạy 3 lần restore, mã MD5 `55ed9488...` và dòng thời gian `real`.
- `02-incident2-db-password-logs.png`: Ảnh chụp log `OperationalError` ở app và `FATAL: password authentication failed` ở DB.
- `03-incident2-discord-firing-resolved.png`: Ảnh tin nhắn Discord `[FIRING]` và `[RESOLVED]` sự cố `DatabaseDown`.
- `04-ufw-sshd-status.png`: Màn hình `sudo ufw status verbose` và `sshd -T`.
- `05-port-scan-git-secrets.png`: Kết quả `Test-NetConnection` (Port 80 = True, 5432 & 3000 = False) và `git ls-files` sạch.
- `06-db-privilege-denied.png`: Màn hình 3 thông báo lỗi từ chối quyền của PostgreSQL đối với user `todo_app`.

### 5.2. Bàn giao phân công
- **Bàn giao cho Người số 1 (Đặng Vĩnh Quang):** Ảnh log + mốc thời gian Sự cố 2 để cập nhật vào `docs/playbook.md` và `docs/incidents/`.
- **Bàn giao cho Người số 2 (Ngô Tấn Đức):** Bảng số liệu restore 3 lần (trung bình 2.702s) để tổng hợp vào `docs/experiments.md`.
- **Bàn giao cho Người số 4 (Phan Tiến Thịnh):** Soạn thảo hoàn chỉnh nội dung **Section 6: Security and Reliability** để đưa vào bài Báo cáo Paper (PDF 6–10 trang) và file video clip thu âm giải thích phần việc cá nhân.
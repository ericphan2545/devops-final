# PLAYBOOK – QUY TRÌNH XỬ LÝ SỰ CỐ

**Dự án:** DevOps Final Project – Todo Application  
**Môi trường:** AWS EC2, Ubuntu, Docker Compose, Nginx, PostgreSQL  
**Người phụ trách:** Đặng Vĩnh Quang – Diễn tập sự cố và Playbook

---

## 1. Tổng quan

Tài liệu này mô tả quy trình phát hiện, kiểm tra, xử lý và khôi phục hệ thống khi xảy ra các sự cố trong quá trình vận hành ứng dụng Todo.

Ba tình huống được thực hiện trong phạm vi diễn tập:

1. Container ứng dụng bị dừng.
2. Mật khẩu kết nối cơ sở dữ liệu không chính xác.
3. Cổng HTTP 80 bị chặn bởi AWS Security Group.

Mục tiêu là kiểm tra khả năng phát hiện sự cố, giám sát hệ thống, xác định nguyên nhân và khôi phục ứng dụng sau khi xảy ra lỗi.

## 2. Thông tin môi trường

| Thành phần | Mô tả |
|---|---|
| Máy chủ | AWS EC2 – Ubuntu |
| Ứng dụng | Todo Web Application |
| Quản lý container | Docker Compose |
| Reverse Proxy | Nginx |
| Cơ sở dữ liệu | PostgreSQL |
| Giám sát | Prometheus và Grafana |
| Địa chỉ website | http://todo-devops.duckdns.org |
| Thư mục dự án | `/home/ubuntu/devops-todo` |
| Đường dẫn kiểm tra sức khỏe | `/health` |

### 2.1. Các lệnh kiểm tra thường dùng

Kiểm tra trạng thái container:

```bash
docker compose ps
```

Kiểm tra tình trạng hoạt động của ứng dụng:

```bash
curl -i http://localhost/health
```

Xem log của ứng dụng:

```bash
docker compose logs app --tail 30
```

Xem log của Nginx:

```bash
docker compose logs nginx --tail 30
```

## 3. Quy trình xử lý sự cố chung

Khi xảy ra sự cố, thực hiện lần lượt các bước:

1. **Phát hiện:** Xác định dấu hiệu bất thường từ website, hệ thống giám sát hoặc thông báo cảnh báo.
2. **Kiểm tra:** Kiểm tra trạng thái container và khả năng truy cập ứng dụng.
3. **Thu thập thông tin:** Ghi nhận log, ảnh chụp màn hình và thời điểm xảy ra sự cố.
4. **Xác định nguyên nhân:** Phân tích thông tin thu thập được để tìm nguyên nhân.
5. **Khắc phục:** Thực hiện các thao tác cần thiết để xử lý lỗi.
6. **Xác nhận:** Kiểm tra lại website và các dịch vụ liên quan sau khi khắc phục.
7. **Ghi nhận:** Lưu kết quả, thời gian phát hiện, thời gian khôi phục và bài học kinh nghiệm.

---

## 4. Tình huống 1 – Container ứng dụng bị dừng

### 4.1. Mục tiêu

Mô phỏng tình huống container ứng dụng bị dừng đột ngột và kiểm tra khả năng phát hiện sự cố của hệ thống giám sát.

### 4.2. Thực hiện mô phỏng

Dừng container ứng dụng bằng lệnh:

```bash
docker compose stop app
```

### 4.3. Dấu hiệu nhận biết

Sau khi container ứng dụng bị dừng, dự kiến có các hiện tượng:

- Website không thể truy cập hoặc trả về lỗi HTTP 502.
- Container ứng dụng không còn ở trạng thái đang chạy.
- Log Nginx có thể xuất hiện lỗi kết nối đến ứng dụng.
- Prometheus/Alertmanager có thể gửi cảnh báo AppDown.
- Grafana hiển thị trạng thái ứng dụng DOWN.

### 4.4. Kiểm tra và xác định nguyên nhân

Kiểm tra trạng thái container:

```bash
docker compose ps
```

Kiểm tra log ứng dụng:

```bash
docker compose logs app --tail 30
```

Kiểm tra log Nginx:

```bash
docker compose logs nginx --tail 30
```

### 4.5. Khôi phục hệ thống

Khởi động lại container ứng dụng:

```bash
docker compose start app
```

Kiểm tra lại trạng thái:

```bash
docker compose ps
```

Kiểm tra Health Check:

```bash
curl -i http://localhost/health
```

Cuối cùng, truy cập website để xác nhận ứng dụng đã hoạt động trở lại.

### 4.6. Ghi nhận kết quả

- Ngày và giờ thực hiện: 2026-11-09
- Hiện tượng xảy ra: Sau khi chạy lệnh docker compose stop app, container ứng dụng devops-todo-app-1 chuyển sang trạng thái Stopped. Khi kiểm tra đường dẫn /health từ máy chủ EC2, hệ thống trả về lỗi HTTP 502 Bad Gateway.
- Nguyên nhân: Container ứng dụng bị dừng nên Nginx không thể chuyển tiếp yêu cầu đến dịch vụ ứng dụng.
- Thời điểm ghi nhận trong log: 15:28:10 UTC, ứng dụng nhận tín hiệu dừng (term).
- Kết quả khôi phục: Chạy lệnh docker compose start app để khởi động lại container. Sau đó, container chuyển sang trạng thái Up và lệnh curl http://localhost/health trả về {"status":"ok"}.
- Ảnh chứng minh: [cung cấp sau]
- Kết quả cuối cùng: Đã khôi phục thành công. Ứng dụng hoạt động trở lại và Health Check trả về trạng thái OK.

---

## 5. Tình huống 2 – Sai mật khẩu kết nối cơ sở dữ liệu

### 5.1. Mục tiêu

Mô phỏng lỗi xác thực khi ứng dụng kết nối PostgreSQL và kiểm tra khả năng khôi phục sau khi cấu hình lại mật khẩu chính xác.

### 5.2. Thực hiện mô phỏng

Thay đổi giá trị `APP_DB_PASSWORD` trong file `.env` trên máy chủ thành một mật khẩu không chính xác.

Sau đó thực hiện lệnh:

```bash
docker compose up -d app
```

**Lưu ý:** Không đưa mật khẩu cơ sở dữ liệu vào ảnh chụp màn hình, log công khai hoặc tài liệu báo cáo.

### 5.3. Dấu hiệu nhận biết

Các hiện tượng có thể xuất hiện:

- Trang chính của ứng dụng trả về lỗi HTTP 503.
- Đường dẫn `/health` có thể trả về HTTP 500.
- Log ứng dụng xuất hiện lỗi xác thực PostgreSQL.
- Hệ thống giám sát có thể gửi cảnh báo DatabaseDown.
- Container ứng dụng vẫn có thể chạy nhưng không kết nối được cơ sở dữ liệu.

### 5.4. Kiểm tra và xác định nguyên nhân

Kiểm tra trạng thái container:

```bash
docker compose ps
```

Kiểm tra log ứng dụng:

```bash
docker compose logs app --tail 30
```

Kiểm tra Health Check:

```bash
curl -i http://localhost/health
```

### 5.5. Khôi phục hệ thống

1. Khôi phục mật khẩu DB chính xác trong file `.env`.
2. Chạy script triển khai của dự án:

```bash
bash scripts/deploy.sh
```

3. Kiểm tra trạng thái container:

```bash
docker compose ps
```

4. Kiểm tra lại ứng dụng:

```bash
curl -i http://localhost/health
```

5. Truy cập website để xác nhận ứng dụng hoạt động bình thường.

### 5.6. Ghi nhận kết quả

- Ngày và giờ thực hiện: [Điền thời gian thực tế]
- Hiện tượng xảy ra: [Ghi nhận kết quả thực tế]
- Log lỗi cơ sở dữ liệu: [Bổ sung đường dẫn]
- Thời gian phát hiện: [Điền số liệu]
- Thời gian khôi phục: [Điền số liệu]
- Ảnh và log minh chứng: [Bổ sung đường dẫn]
- Kết quả khôi phục: [Đã xác nhận / Chưa xác nhận]

**Trạng thái hiện tại:** Đã thực hiện mô phỏng lỗi. Đang chờ khôi phục mật khẩu DB chính xác và xác nhận ứng dụng hoạt động trở lại.

---

## 6. Tình huống 3 – Cổng HTTP 80 bị chặn

### 6.1. Mục tiêu

Mô phỏng tình huống người dùng bên ngoài không thể truy cập website do cổng HTTP 80 bị chặn trong AWS Security Group.

Tình huống này giúp kiểm tra sự khác biệt giữa trạng thái hoạt động nội bộ của ứng dụng trên EC2 và khả năng truy cập website từ bên ngoài.

### 6.2. Phân công phối hợp

| Thành viên | Nhiệm vụ |
|---|---|
| Thành viên số 1 | SSH vào EC2, kiểm tra Health Check, thử truy cập website, thu thập log và chụp ảnh |
| Thành viên số 4 (Eric) | Thao tác xóa và khôi phục quy tắc HTTP TCP 80 trong AWS Security Group |

### 6.3. Thực hiện mô phỏng

Thành viên số 4 thực hiện các thao tác trên AWS Console:

1. Truy cập dịch vụ EC2.
2. Mở mục Security Groups.
3. Chọn Security Group đang gắn với máy chủ ứng dụng.
4. Chọn Edit inbound rules.
5. Tạm thời xóa quy tắc HTTP TCP 80.
6. Lưu thay đổi.

**Lưu ý quan trọng:** Không xóa quy tắc SSH TCP 22 vì cần giữ kết nối SSH để kiểm tra máy chủ.

### 6.4. Dấu hiệu nhận biết

Sau khi cổng 80 bị chặn, dự kiến có các hiện tượng:

- Người dùng không thể truy cập website từ bên ngoài.
- Kết nối TCP đến cổng 80 thất bại hoặc bị timeout.
- Kết nối SSH qua cổng 22 vẫn hoạt động.
- Ứng dụng có thể vẫn hoạt động bình thường bên trong EC2.
- Hệ thống giám sát nội bộ có thể vẫn hiển thị ứng dụng ở trạng thái UP.

### 6.5. Kiểm tra và xác định nguyên nhân

Từ máy tính cá nhân, kiểm tra kết nối website:

```bash
curl -I --max-time 5 http://todo-devops.duckdns.org
```

Từ EC2, kiểm tra ứng dụng nội bộ:

```bash
curl -i http://localhost/health
```

Kiểm tra trạng thái container:

```bash
docker compose ps
```

Nếu website bên ngoài không truy cập được nhưng Health Check nội bộ vẫn thành công, có thể xác định vấn đề nằm ở lớp kết nối mạng bên ngoài thay vì bản thân ứng dụng.

### 6.6. Khôi phục hệ thống

Thành viên số 4 khôi phục quy tắc HTTP TCP 80 ban đầu trong AWS Security Group.

Sau đó, thành viên số 1 thực hiện:

1. Truy cập lại website từ trình duyệt.
2. Kiểm tra Health Check nội bộ.
3. Kiểm tra trạng thái container.
4. Xác nhận website đã truy cập được trở lại.

### 6.7. Ghi nhận kết quả

- Ngày và giờ thực hiện: [Điền thời gian thực tế]
- Người thao tác Security Group: [Điền tên]
- Kết quả truy cập từ bên ngoài: [Ghi nhận thực tế]
- Kết quả Health Check nội bộ: [Ghi nhận thực tế]
- Thời gian khôi phục: [Điền số liệu]
- Ảnh và log minh chứng: [Bổ sung đường dẫn]
- Kết quả khôi phục: [Đã xác nhận / Chưa xác nhận]

**Trạng thái hiện tại:** Chờ phối hợp với thành viên số 4 (Eric) để thực hiện mô phỏng.

---

## 7. Tổng hợp kết quả diễn tập

| Tình huống | Mô phỏng | Xác nhận khôi phục | Trạng thái |
|---|---|---|---|
| Container ứng dụng bị dừng | Đã thực hiện | [Bổ sung kết quả] | Đã có ảnh minh chứng |
| Sai mật khẩu DB | Đã thực hiện | Đang chờ mật khẩu chính xác | Chưa hoàn tất |
| Chặn cổng HTTP 80 | Chưa thực hiện | Chưa thực hiện | Chờ Eric phối hợp |

---

## 8. Bài học kinh nghiệm

Hoàn thiện phần này sau khi thực hiện đầy đủ ba tình huống.

Các nội dung cần đánh giá:

- Vai trò của Health Check và hệ thống giám sát trong việc phát hiện sự cố.
- Tầm quan trọng của việc quản lý mật khẩu và thông tin kết nối cơ sở dữ liệu.
- Vai trò của AWS Security Group trong việc kiểm soát truy cập từ bên ngoài.
- Cách phân biệt lỗi ứng dụng, lỗi cơ sở dữ liệu và lỗi kết nối mạng.
- Tầm quan trọng của việc thu thập log và xác nhận hệ thống hoạt động trở lại sau khi khắc phục.

---

**Trạng thái tài liệu:** Bản nháp – chờ bổ sung kết quả thực tế, ảnh chụp màn hình và xác nhận khôi phục của các tình huống còn lại.
# PLAYBOOK – QUY TRÌNH XỬ LÝ SỰ CỐ

**Dự án:** DevOps Final Project – Todo Application  
**Môi trường:** AWS EC2, Ubuntu, Docker Compose, Nginx, PostgreSQL  
**Người phụ trách:** Đặng Vĩnh Quang – Thành viên số 1  
**Trạng thái:** Bản dự thảo, đang bổ sung minh chứng và kết quả khôi phục

---

## 1. Tổng quan

Tài liệu mô tả quy trình phát hiện, kiểm tra, xác định nguyên nhân và khôi phục hệ thống khi xảy ra sự cố trong quá trình vận hành ứng dụng Todo.

Ba tình huống được lựa chọn để diễn tập:

1. Container ứng dụng bị dừng.
2. Mật khẩu kết nối cơ sở dữ liệu không chính xác.
3. Cổng HTTP 80 bị chặn bởi AWS Security Group.

Mục tiêu là đánh giá khả năng phát hiện sự cố, sử dụng log và hệ thống giám sát để khoanh vùng nguyên nhân, đồng thời xác nhận ứng dụng hoạt động bình thường sau khi khắc phục.

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
| Health Check | `/health` |

### 2.1. Các lệnh kiểm tra thường dùng

Thực hiện các lệnh trong thư mục dự án trên EC2.

**Kiểm tra trạng thái container:**

```bash
docker compose ps
```

**Kiểm tra Health Check nội bộ:**

```bash
curl -i http://localhost/health
```

**Xem log ứng dụng:**

```bash
docker compose logs app --tail 30
```

**Xem log Nginx:**

```bash
docker compose logs nginx --tail 30
```

Các lệnh này hỗ trợ kiểm tra trạng thái dịch vụ và xác định nguyên nhân khi ứng dụng không hoạt động như mong đợi.

## 3. Quy trình xử lý sự cố chung

Khi xảy ra sự cố, thực hiện lần lượt:

1. **Phát hiện:** Nhận biết dấu hiệu bất thường từ website, Health Check, Grafana hoặc thông báo Discord.
2. **Kiểm tra:** Kiểm tra trạng thái container và khả năng truy cập ứng dụng.
3. **Thu thập thông tin:** Ghi lại thời điểm, log và ảnh chụp màn hình cần thiết.
4. **Xác định nguyên nhân:** Phân tích log và trạng thái dịch vụ để khoanh vùng lỗi.
5. **Khắc phục:** Thực hiện thao tác khôi phục phù hợp với nguyên nhân.
6. **Xác nhận:** Kiểm tra lại website, Health Check và trạng thái container.
7. **Ghi nhận:** Lưu kết quả, thời gian xử lý và bài học kinh nghiệm.

---

## 4. Tình huống 1 – Container ứng dụng bị dừng

### 4.1. Mục tiêu

Mô phỏng tình huống container ứng dụng bị dừng đột ngột, từ đó kiểm tra khả năng phát hiện sự cố của Nginx, Prometheus, Grafana và Discord.

### 4.2. Thực hiện mô phỏng

Dừng container ứng dụng:

```bash
docker compose stop app
```

### 4.3. Dấu hiệu nhận biết

Sau khi container ứng dụng bị dừng, có thể xuất hiện các hiện tượng:

- Website không thể truy cập hoặc trả về HTTP 502 Bad Gateway.
- Container ứng dụng không còn ở trạng thái đang chạy.
- Log Nginx xuất hiện lỗi kết nối đến dịch vụ ứng dụng.
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

Nếu container app đã dừng và Nginx không thể kết nối đến dịch vụ ứng dụng, nguyên nhân có thể được xác định là container app không hoạt động.

### 4.5. Khôi phục hệ thống

Khởi động lại container:

```bash
docker compose start app
```

Kiểm tra trạng thái:

```bash
docker compose ps
```

Kiểm tra Health Check:

```bash
curl -i http://localhost/health
```

Cuối cùng, truy cập website từ trình duyệt để xác nhận ứng dụng hoạt động trở lại.

### 4.6. Kết quả diễn tập thực tế

- **Ngày thực hiện:** 09/11/2026.
- **Hiện tượng:** Sau khi chạy `docker compose stop app`, container `devops-todo-app-1` chuyển sang trạng thái Stopped.
- **Kết quả kiểm tra:** Endpoint `/health` trên EC2 trả về HTTP 502 Bad Gateway.
- **Nguyên nhân:** Container ứng dụng bị dừng nên Nginx không thể chuyển tiếp yêu cầu đến dịch vụ ứng dụng.
- **Thời điểm ghi nhận trong log:** 15:28:10 UTC, ứng dụng nhận tín hiệu dừng (term).
- **Khôi phục:** Chạy `docker compose start app`. Container chuyển sang trạng thái Up và Health Check trả về `{"status":"ok"}`.
- **Kết quả cuối cùng:** Đã khôi phục thành công, ứng dụng hoạt động trở lại.

**Minh chứng cần bổ sung:**
- Ảnh trạng thái container trước và sau khi dừng ứng dụng.
- Ảnh lỗi HTTP 502.
- Ảnh kết quả Health Check sau khi khôi phục.
- Log liên quan đến sự cố.

---

## 5. Tình huống 2 – Sai mật khẩu kết nối cơ sở dữ liệu

### 5.1. Mục tiêu

Mô phỏng lỗi xác thực khi ứng dụng kết nối PostgreSQL và kiểm tra khả năng phát hiện, khoanh vùng cũng như khôi phục sự cố.

### 5.2. Thực hiện mô phỏng

Trước khi thay đổi cấu hình, cần sao lưu file `.env` chứa thông tin kết nối ban đầu.

Sau đó thay đổi giá trị `APP_DB_PASSWORD` trong `.env` trên EC2 thành một giá trị không chính xác.

Tạo lại riêng container ứng dụng:

```bash
docker compose up -d --no-deps app
```

**Lưu ý bảo mật:**
- Không hiển thị mật khẩu trong ảnh chụp màn hình hoặc tài liệu báo cáo.
- Không commit file `.env` lên GitHub.
- Không thay đổi mật khẩu thật của PostgreSQL trong tình huống này.

### 5.3. Dấu hiệu nhận biết

Các hiện tượng có thể xuất hiện:

- Trang chính của ứng dụng trả về HTTP 503.
- Endpoint `/health` trả về HTTP 500.
- Log ứng dụng xuất hiện lỗi xác thực PostgreSQL.
- Hệ thống giám sát có thể gửi cảnh báo DatabaseDown.
- Container ứng dụng vẫn chạy nhưng không thể kết nối cơ sở dữ liệu.

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

Nếu log PostgreSQL xuất hiện thông báo xác thực thất bại đối với user `todo_app`, có thể xác định mật khẩu ứng dụng đang sử dụng không khớp với mật khẩu được cấu hình trong PostgreSQL.

### 5.5. Khôi phục hệ thống

1. Khôi phục file `.env` ban đầu từ bản sao lưu an toàn.
2. Tạo lại riêng container ứng dụng để nạp cấu hình chính xác:

```bash
docker compose up -d --no-deps app
```

3. Kiểm tra trạng thái container:

```bash
docker compose ps
```

4. Kiểm tra Health Check:

```bash
curl -i http://localhost/health
```

5. Truy cập website để xác nhận ứng dụng hoạt động bình thường.

**Lưu ý:** Không chạy script thay đổi mật khẩu PostgreSQL để khôi phục tình huống này. Mục tiêu là đưa cấu hình ứng dụng về giá trị ban đầu, không thay đổi mật khẩu thực tế của database.

### 5.6. Kết quả diễn tập thực tế

- **Ngày thực hiện:** 09/11/2026.
- **Hiện tượng:** Sau khi thay đổi `APP_DB_PASSWORD` thành giá trị không chính xác và tạo lại container ứng dụng, endpoint `/health` trả về HTTP 500 Internal Server Error với nội dung `cannot connect to database`.
- **Nguyên nhân:** Mật khẩu ứng dụng sử dụng để xác thực với PostgreSQL không khớp với mật khẩu của user `todo_app`.
- **Bằng chứng từ log:** PostgreSQL ghi nhận lỗi `FATAL: password authentication failed for user "todo_app"`.
- **Cảnh báo giám sát:** Discord gửi cảnh báo `[FIRING:1] DatabaseDown app (app:8000 critical)`. Chỉ số `todo_db_up` bằng 0 liên tục trong 1 phút.
- **Kết quả mô phỏng:** Đã tạo được tình huống lỗi kết nối cơ sở dữ liệu và xác nhận hệ thống giám sát phát hiện sự cố.
- **Kết quả khôi phục:** Chưa xác nhận.
- **Ảnh và log:** Cần bổ sung ảnh lỗi HTTP 500, log PostgreSQL và thông báo Discord DatabaseDown.

<Chưa hoàn tất: cần khôi phục cấu hình ban đầu, kiểm tra Health Check và xác nhận website hoạt động trở lại.>

---

## 6. Tình huống 3 – Cổng HTTP 80 bị chặn

### 6.1. Mục tiêu

Mô phỏng tình huống người dùng bên ngoài không thể truy cập website do cổng HTTP 80 bị chặn trong AWS Security Group.

Tình huống này giúp kiểm tra sự khác biệt giữa trạng thái hoạt động nội bộ của ứng dụng trên EC2 và khả năng truy cập website từ bên ngoài.

### 6.2. Phân công phối hợp

| Thành viên | Nhiệm vụ |
|---|---|
| Thành viên số 1 – Đặng Vĩnh Quang | SSH vào EC2, kiểm tra Health Check, thử truy cập website, thu thập log và chụp ảnh |
| Thành viên số 4 – Eric | Thao tác xóa và khôi phục quy tắc HTTP TCP 80 trong AWS Security Group |

### 6.3. Thực hiện mô phỏng

Thành viên số 4 thực hiện trên AWS Console:

1. Truy cập dịch vụ EC2.
2. Mở mục Security Groups.
3. Chọn Security Group đang gắn với máy chủ ứng dụng.
4. Chọn Edit inbound rules.
5. Ghi lại quy tắc ban đầu, sau đó tạm thời xóa quy tắc HTTP TCP 80.
6. Lưu thay đổi.

**Lưu ý quan trọng:** Không xóa quy tắc SSH TCP 22 vì cần giữ kết nối SSH để kiểm tra máy chủ.

### 6.4. Dấu hiệu nhận biết

Sau khi cổng 80 bị chặn, có thể xuất hiện:

- Người dùng bên ngoài không thể truy cập website.
- Kết nối TCP đến cổng 80 thất bại hoặc bị timeout.
- Kết nối SSH qua cổng 22 vẫn hoạt động.
- Ứng dụng có thể vẫn hoạt động bình thường bên trong EC2.
- Hệ thống giám sát nội bộ có thể vẫn hiển thị ứng dụng ở trạng thái UP.

### 6.5. Kiểm tra và xác định nguyên nhân

Từ máy tính cá nhân, kiểm tra website:

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

Nếu website bên ngoài không truy cập được nhưng Health Check nội bộ vẫn thành công, có thể khoanh vùng vấn đề ở lớp kết nối mạng bên ngoài thay vì bản thân ứng dụng.

### 6.6. Khôi phục hệ thống

Thành viên số 4 khôi phục quy tắc HTTP TCP 80 ban đầu trong AWS Security Group.

Sau đó, thành viên số 1:

1. Truy cập lại website từ trình duyệt.
2. Kiểm tra Health Check nội bộ.
3. Kiểm tra trạng thái container.
4. Xác nhận website truy cập được trở lại.

### 6.7. Kết quả diễn tập thực tế

- **Ngày và giờ thực hiện:** Chưa thực hiện.
- **Người thao tác Security Group:** Eric – thành viên số 4.
- **Kết quả truy cập từ bên ngoài:** Chưa ghi nhận.
- **Kết quả Health Check nội bộ:** Chưa ghi nhận.
- **Thời gian khôi phục:** Chưa ghi nhận.
- **Ảnh và log minh chứng:** Chưa có.
- **Kết quả khôi phục:** Chưa xác nhận.

<Chưa hoàn tất: cần phối hợp với thành viên số 4 để thực hiện mô phỏng và ghi nhận kết quả thực tế.>

---

## 7. Tổng hợp kết quả diễn tập

| Tình huống | Mô phỏng | Khôi phục | Trạng thái |
|---|---|---|---|
| Container ứng dụng bị dừng | Đã thực hiện | Đã xác nhận | Hoàn thành, cần bổ sung ảnh |
| Sai mật khẩu DB | Đã thực hiện | Chưa xác nhận | Chờ khôi phục và kiểm tra |
| Chặn cổng HTTP 80 | Chưa thực hiện | Chưa thực hiện | Chờ phối hợp với Eric |

## 8. Bài học kinh nghiệm

Qua các tình huống diễn tập, nhóm có thể đánh giá một số khía cạnh quan trọng trong vận hành hệ thống:

- **Health Check và Monitoring:** Health Check, Prometheus và Grafana hỗ trợ phát hiện trạng thái bất thường của ứng dụng và cơ sở dữ liệu.
- **Quản lý thông tin xác thực:** Cấu hình mật khẩu kết nối database cần được quản lý cẩn thận để tránh lỗi xác thực.
- **Kiểm soát truy cập mạng:** AWS Security Group quyết định khả năng truy cập dịch vụ từ bên ngoài máy chủ.
- **Khoanh vùng sự cố:** Cần phân biệt lỗi ứng dụng, lỗi cơ sở dữ liệu và lỗi kết nối mạng để lựa chọn phương án khắc phục phù hợp.
- **Thu thập bằng chứng:** Log, ảnh chụp màn hình và kết quả Health Check giúp xác nhận nguyên nhân cũng như trạng thái sau khi khôi phục.

Phần đánh giá cuối cùng sẽ được cập nhật sau khi hoàn thành cả ba tình huống.

---

## 9. Danh sách công việc còn lại

- [ ] Bổ sung ảnh và log cho tình huống App Down.
- [ ] Khôi phục cấu hình DB ban đầu và xác nhận Health Check trả HTTP 200.
- [ ] Bổ sung ảnh lỗi DB, log PostgreSQL và cảnh báo Discord.
- [ ] Phối hợp với Eric thực hiện tình huống chặn cổng HTTP 80.
- [ ] Bổ sung ảnh Security Group trước và sau khi khôi phục.
- [ ] Ghi nhận thời gian và kết quả thực tế của từng tình huống.
- [ ] Hoàn thiện phần bài học kinh nghiệm sau khi có đủ kết quả.

**Kết luận:** Playbook đã có quy trình xử lý cho cả ba tình huống. Tuy nhiên, tình huống sai mật khẩu DB chưa xác nhận khôi phục và tình huống chặn cổng HTTP 80 chưa được diễn tập. Tài liệu sẽ được cập nhật sau khi hoàn thành các bước còn thiếu và thu thập đầy đủ minh chứng.
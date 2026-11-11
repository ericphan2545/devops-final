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
date '+%F %T' && docker compose stop app
```

### 4.3. Dấu hiệu nhận biết

Sau khi container ứng dụng bị dừng, có thể xuất hiện các hiện tượng:

Sau khi container ứng dụng bị dừng, có thể xuất hiện
các hiện tượng sau:

- Website không thể truy cập hoặc trả về HTTP 502 Bad Gateway.
- Endpoint /health không phản hồi bình thường.
- Container app chuyển sang trạng thái Stopped.
- Log Nginx xuất hiện lỗi kết nối đến dịch vụ ứng dụng.
- Prometheus phát hiện không thể scrape app:8000 liên tục trong khoảng 1 phút.
- Alertmanager gửi cảnh báo AppDown đến Discord với trạng thái FIRING.
- Grafana hiển thị panel App ở trạng thái DOWN.

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
date '+%F %T' && docker compose start app
```

Kiểm tra trạng thái:

```bash
docker compose ps
```

Kiểm tra Health Check:

```bash
curl -i http://localhost/health
```

- Chờ Prometheus scrape ứng dụng thành công.
- Xác nhận cảnh báo AppDown chuyển sang RESOLVED trên Discord.
- Xác nhận website truy cập bình thường trở lại.

### 4.6. Kết quả diễn tập thực tế

- **Ngày thực hiện:** 09/11/2026.
- **Hiện tượng:** Sau khi chạy `docker compose stop app`, container `devops-todo-app-1` chuyển sang trạng thái Stopped.
- **Kết quả kiểm tra:** Endpoint `/health` trả về HTTP 502 Bad Gateway do Nginx không thể kết nối đến ứng dụng.
- **Nguyên nhân:** Container ứng dụng bị dừng, khiến Nginx không thể chuyển tiếp yêu cầu đến backend.
- **Thời điểm ghi nhận trong log:** 22:28:10, ứng dụng nhận tín hiệu dừng (term).
- **Khôi phục:** Chạy `docker compose start app`. Container chuyển sang trạng thái Up và Health Check trả về `{"status":"ok"}`.
- **Kết quả cuối cùng:** Đã khôi phục thành công, ứng dụng hoạt động trở lại.

**Minh chứng:**
- [Ảnh dừng, khôi phục và cảnh báo](evidence/week-4/incidents/incident-01-app-down/).
- [Biên bản và mốc đã đối chiếu](incidents/2026-11-09-app-down.md).

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
- **Hiện tượng:** Sau khi thay đổi giá trị `APP_DB_PASSWORD` thành mật khẩu không chính xác trong file `.env` và tạo lại container ứng dụng, endpoint `/health` trả về HTTP 500 Internal Server Error với nội dung `cannot connect to database`.
- **Nguyên nhân:** Mật khẩu ứng dụng sử dụng để xác thực với PostgreSQL không khớp với mật khẩu của user `todo_app`.
- **Bằng chứng từ log:** PostgreSQL ghi nhận lỗi `FATAL: password authentication failed for user "todo_app"`.
- **Cảnh báo giám sát:** Discord Alert Bot gửi cảnh báo `[FIRING:1] DatabaseDown` khi chỉ số `todo_db_up` bằng 0 liên tục trong 1 phút.
- **Khôi phục:** Đã phối hợp với thành viên Eric để khôi phục cấu hình mật khẩu database.
- **Cảnh báo sau khôi phục:** Discord ghi nhận trạng thái `[RESOLVED] DatabaseDown`.
- **Kết quả cuối cùng:** Ảnh kiểm tra sau khôi phục xác nhận HTTP 200, status=ok lúc 10:56:45 UTC ngày 10/11/2026. Chưa đủ mốc đối chiếu để tính thời gian cảnh báo/phục hồi chính xác.

**Minh chứng:**
- [Ảnh lỗi, Discord và HTTP 200 sau khôi phục](evidence/week-4/incidents/incident-02-database-down/).
- [Biên bản kết nối database](incidents/2026-11-09-database-down.md).

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
- Discord không gửi cảnh báo AppDown hoặc DatabaseDown vì ứng dụng và database vẫn hoạt động nội bộ.
- Sự cố nằm ở lớp truy cập mạng bên ngoài (AWS Security Group), không phải lỗi của ứng dụng hoặc database.

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

- **Ngày thực hiện:** 10/11/2026.
- **Người thao tác Security Group:** Eric – thành viên số 4.
- **Thao tác gây lỗi:** Xóa quy tắc inbound HTTP TCP 80 trong AWS Security Group.
- **Kết quả truy cập từ bên ngoài:** Website không thể truy cập, trình duyệt hiển thị `ERR_CONNECTION_TIMED_OUT`; PowerShell ghi nhận lỗi kết nối timeout.
- **Kết quả kiểm tra nội bộ:** Các container vẫn hoạt động. Endpoint `/health` trên EC2 trả về HTTP 200 OK với nội dung `{"status":"ok"}`.
- **Nguyên nhân:** Kết nối HTTP từ Internet đến EC2 bị chặn bởi AWS Security Group.
- **Cảnh báo Discord:** Không phát sinh cảnh báo AppDown hoặc DatabaseDown trong thời gian diễn tập.
- **Khôi phục:** Eric thực hiện thêm lại quy tắc inbound HTTP TCP 80 theo cấu hình ban đầu.
- **Kết quả khôi phục:** Cần xác nhận lại khả năng truy cập website từ bên ngoài sau khi khôi phục.

**Minh chứng:**
- [Ảnh timeout bên ngoài và HTTP 200 nội bộ](evidence/week-4/incidents/incident-03-port-80/).
- [Biên bản HTTP 80](incidents/2026-11-10-http-80-blocked.md).

---

## 7. Tổng hợp kết quả diễn tập

| Tình huống | Mô phỏng | Khôi phục | Trạng thái |
|---|---|---|---|
| Container ứng dụng bị dừng | Đã thực hiện | Đã xác nhận status=ok | Có ảnh dừng/khôi phục; thiếu mốc cảnh báo/phục hồi chính xác |
| Sai mật khẩu DB | Đã thực hiện | Đã có ảnh HTTP 200 sau khôi phục | Có ảnh lỗi/Discord/phục hồi; chưa tính thời gian khi mốc chưa khớp |
| Chặn cổng HTTP 80 | Đã thực hiện | Đã xác nhận HTTP 200 từ bên ngoài (11/11) | Có ảnh timeout bên ngoài, HTTP 200 nội bộ và mốc CloudTrail xóa/mở rule |

## 8. Bài học kinh nghiệm

Qua các tình huống diễn tập, nhóm có thể đánh giá một số khía cạnh quan trọng trong vận hành hệ thống:

- **Health Check và Monitoring:** Health Check, Prometheus và Grafana hỗ trợ phát hiện trạng thái bất thường của ứng dụng và cơ sở dữ liệu.
- **Quản lý thông tin xác thực:** Cấu hình mật khẩu kết nối database cần được quản lý cẩn thận để tránh lỗi xác thực.
- **Kiểm soát truy cập mạng:** AWS Security Group quyết định khả năng truy cập dịch vụ từ bên ngoài máy chủ.
- **Khoanh vùng sự cố:** Cần phân biệt lỗi ứng dụng, lỗi cơ sở dữ liệu và lỗi kết nối mạng để lựa chọn phương án khắc phục phù hợp.
- **Thu thập bằng chứng:** Log, ảnh chụp màn hình và kết quả Health Check giúp xác nhận nguyên nhân cũng như trạng thái sau khi khôi phục.

Cả ba tình huống đã có ảnh diễn tập. Các mốc thời gian được ghi theo ảnh nguồn trong biên bản; không tính số liệu khi thiếu bằng chứng đối chiếu.

---

## 9. Hoàn thiện minh chứng

- [x] Lưu ảnh dừng và khởi động lại app, kết quả Health Check và hai trạng thái cảnh báo AppDown.
- [x] Lưu ảnh lỗi xác thực DB, cảnh báo DatabaseDown và HTTP 200 sau khôi phục.
- [x] Lưu ảnh timeout bên ngoài khi chặn HTTP 80 và HTTP 200 nội bộ trên EC2.
- [x] Bổ sung mốc CloudTrail xóa/mở lại HTTP 80 và ảnh HTTP 200 từ bên ngoài.
- [ ] Ghi đầy đủ ngày/múi giờ Discord, giờ thao tác khôi phục để tính các thời lượng còn thiếu.

**Kết luận:** Playbook có quy trình và bằng chứng diễn tập cho cả ba sự cố; app và kết nối DB đã có bằng chứng phục hồi. Truy cập bên ngoài sau khi mở HTTP 80 đã được xác nhận; vẫn cần bổ sung các mốc còn thiếu trước khi chốt số liệu thời gian.

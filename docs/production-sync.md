# Bật đồng bộ thật với Flask/PostgreSQL

Bản Flask trong repo dùng PostgreSQL thật qua `/health`, `/api/tasks` và `/api/operations`. Không có nút mô phỏng mất mạng trên trang Flask. Link Sites xem giao diện trước đây là một bản mô phỏng riêng; nó không phải server EC2.

## Chạy thử bản thật trên máy cá nhân

Cần Docker Engine và Docker Compose; trên Windows có thể dùng Docker Desktop với Linux containers. Trong thư mục `devops-final-git`:

1. Tạo `.env` từ `.env.example` (nếu chưa có) và đổi các mật khẩu `POSTGRES_PASSWORD`, `APP_DB_PASSWORD`, `GRAFANA_ADMIN_PASSWORD` (bảo đảm `APP_DB_USER` khác `POSTGRES_USER`; nếu thử trên máy cá nhân có thể đặt `GRAFANA_ROOT_URL=http://localhost/grafana/`).
2. Tạo file `secrets/discord_webhook_url` chứa URL Discord webhook thử nghiệm hợp lệ (ngoài Git) để Alertmanager đọc được.
3. Chạy quy trình triển khai chuẩn (kiểm tra cấu hình → build app → chờ DB → chạy `migrate.py` một lần bằng tài khoản quản trị → cấp quyền `todo_app` → khởi động 7 service → kiểm tra health/API/Grafana):

```bash
bash scripts/deploy.sh
docker compose ps
curl --fail http://localhost/health
curl --fail http://localhost/api/tasks
```

*(Lưu ý: Từ tuần 3, `app/entrypoint.sh` chỉ chạy Gunicorn bằng tài khoản quyền hẹp `APP_DB_USER`, không còn tự chạy `migrate.py` trong entrypoint).*

Mở `http://localhost/`. Ở cuối danh sách, nhãn xanh chỉ xuất hiện sau khi máy chủ và DB trả lời thành công, danh sách đã được đọc lại và hàng đợi rỗng. Thêm một việc rồi tải lại trang: việc phải còn trong PostgreSQL.

## Đưa lên EC2

1. Tạo EC2 Ubuntu 24.04 theo cấu hình môn học; cho phép HTTP 80 và SSH 22 từ nguồn quản trị của bạn. Cài Docker Engine và Docker Compose trên máy đó.
2. Nếu nâng cấp server EC2 đang chạy từ tuần 1–2 lên cấu hình tuần 3: **thực hiện Bước 1 chuẩn bị server trước** (backup DB dự phòng, bổ sung biến tuần 3 vào `.env`, tạo `secrets/discord_webhook_url` với quyền `root:65534` `640`, tạo và cấp quyền `todo_app`), sau đó mới merge/pull cấu hình mới vào `main` và chạy `bash scripts/deploy.sh`.
3. Kiểm tra sau triển khai:

```bash
docker compose ps
curl --fail http://localhost/health
curl --fail http://localhost/api/tasks
curl -I http://localhost/metrics
curl --fail http://localhost/grafana/api/health
```

Mở `http://<IP-public-hoặc-DuckDNS>/` trong trình duyệt. Trang và API phải được phục vụ từ **cùng ứng dụng Flask qua Nginx**. Trình duyệt gọi API tương đối trên server đó; không cần ghi IP hay mật khẩu PostgreSQL vào JavaScript.

Không dùng link Sites xem thử làm địa chỉ kiểm tra DB của đồ án. Sau khi có server, dùng địa chỉ EC2 hoặc tên miền trỏ vào server để kiểm tra hệ thống thật.

## Kiểm tra lưu và đồng bộ

- Có mạng: thêm/xoá; chờ trạng thái Đã đồng bộ rồi tải lại để kiểm tra dữ liệu máy chủ.
- Mở cùng địa chỉ ứng dụng từ trình duyệt khác: dữ liệu đã gửi phải được đọc lại từ PostgreSQL.
- Tắt mạng khi trang đang mở: thao tác vẫn lưu trong IndexedDB; số thay đổi chờ gửi tăng.
- Bật mạng: ứng dụng kiểm tra `/health`, gửi hàng đợi và đọc lại dữ liệu. Chỉ sau khi xác nhận thành công mới báo đã đồng bộ.
- Server trả 401/403/404 hoặc DB không sẵn sàng: hiển thị lỗi hoặc chưa kết nối, giữ thao tác đang chờ. Không báo xanh chỉ vì máy có Internet.
- Footer hiển thị phiên bản. Thông tin kết nối và số thao tác chờ gửi nằm cuối danh sách; bấm Đồng bộ lại để thử gửi thủ công.

Để tải lại trang khi mất mạng trên EC2, cần HTTPS và một lần tải thành công trước đó. HTTP với IP public vẫn lưu dữ liệu khi trang đang mở, nhưng không bảo đảm mở lại trang ngoại tuyến. Các origin khác nhau (IP/tên miền/giao thức/cổng) có bộ nhớ trình duyệt riêng.

## Nếu chưa thấy nhãn xanh

```bash
docker compose logs --tail 80 app
docker compose logs --tail 80 db
curl -i http://localhost/health
curl -i http://localhost/api/tasks
```

Nếu `/api/tasks` trả 404, kiểm tra server đã chạy đúng bản nâng cấp có API. Nếu `/health` báo lỗi, kiểm tra DB, `.env`, quyền của `APP_DB_USER` và bước migration quản trị trong `scripts/deploy.sh`. Không xoá volume bằng `down -v` để sửa giao diện hoặc thử kết nối.

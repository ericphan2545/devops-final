# Bật đồng bộ thật với Flask/PostgreSQL

Bản Flask trong repo dùng PostgreSQL thật qua `/health`, `/api/tasks` và `/api/operations`. Không có nút mô phỏng mất mạng trên trang Flask. Link Sites xem giao diện trước đây là một bản mô phỏng riêng; nó không phải server EC2.

## Chạy thử bản thật trên máy cá nhân

Cần Docker Engine và Docker Compose; trên Windows có thể dùng Docker Desktop với Linux containers. Trong thư mục `devops-final-git`, mở PowerShell:

```powershell
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
```

Mở `.env` và đặt mật khẩu DB trước lần chạy đầu tiên, sau đó:

```powershell
docker compose config --quiet
docker compose up -d --build
docker compose ps
curl.exe --fail http://localhost/health
curl.exe --fail http://localhost/api/tasks
```

Mở `http://localhost/`. Khi vào Cài đặt, nhãn xanh chỉ xuất hiện sau khi máy chủ và DB trả lời thành công, danh sách đã được đọc lại và hàng đợi rỗng. Thêm một việc rồi tải lại trang: việc phải còn trong PostgreSQL.

## Đưa lên EC2

1. Tạo EC2 Ubuntu 24.04 theo cấu hình môn học; cho phép HTTP 80 và SSH 22 từ nguồn quản trị của bạn. Cài Docker Engine và Docker Compose trên máy đó.
2. Đưa **đầy đủ mã nguồn đã cập nhật** lên server. Nếu dùng Git, commit/push bản nâng cấp vào nhánh của nhóm trước khi clone/pull trên server. Bản nâng cấp cần cả API Flask, migration và schema đã chuẩn bị ở bước offline-first, không chỉ ba file giao diện.
3. Trong thư mục dự án trên server, tạo `.env` từ `.env.example` nếu chưa có và đổi mật khẩu DB trước lần chạy đầu tiên.
4. Chạy:

```bash
docker compose config --quiet
bash scripts/deploy.sh
docker compose ps
curl --fail http://localhost/health
curl --fail http://localhost/api/tasks
```

Mở `http://<IP-public-EC2>/` trong trình duyệt. Trang và API phải được phục vụ từ **cùng ứng dụng Flask qua Nginx**. Trình duyệt gọi API tương đối trên server đó; không cần ghi IP hay mật khẩu PostgreSQL vào JavaScript.

Không dùng link Sites xem thử làm địa chỉ kiểm tra DB của đồ án. Sau khi có server, dùng địa chỉ EC2 hoặc tên miền trỏ vào server để kiểm tra hệ thống thật.

## Kiểm tra lưu và đồng bộ

- Có mạng: thêm/sửa/hoàn thành/xoá; chờ hàng đợi về 0 rồi tải lại để kiểm tra dữ liệu máy chủ.
- Mở cùng địa chỉ ứng dụng từ trình duyệt khác: dữ liệu đã gửi phải được đọc lại từ PostgreSQL.
- Tắt mạng khi trang đang mở: thao tác vẫn lưu trong IndexedDB; số thay đổi chờ gửi tăng.
- Bật mạng: ứng dụng kiểm tra `/health`, gửi hàng đợi và đọc lại dữ liệu. Chỉ sau khi xác nhận thành công mới báo đã đồng bộ.
- Server trả 401/403/404 hoặc DB không sẵn sàng: hiển thị lỗi hoặc chưa kết nối, giữ thao tác đang chờ. Không báo xanh chỉ vì máy có Internet.
- `Đồng bộ lần cuối` là ngày và giờ hoàn tất một vòng đồng bộ, không phải giờ bấm nút.

Để tải lại trang khi mất mạng trên EC2, cần HTTPS và một lần tải thành công trước đó. HTTP với IP public vẫn lưu dữ liệu khi trang đang mở, nhưng không bảo đảm mở lại trang ngoại tuyến. Các origin khác nhau (IP/tên miền/giao thức/cổng) có bộ nhớ trình duyệt riêng.

## Nếu chưa thấy nhãn xanh

```bash
docker compose logs --tail 80 app
docker compose logs --tail 80 db
curl -i http://localhost/health
curl -i http://localhost/api/tasks
```

Nếu `/api/tasks` trả 404, kiểm tra server đã chạy đúng bản nâng cấp có API. Nếu `/health` báo lỗi, kiểm tra DB, `.env` và log migration. Không xoá volume bằng `down -v` để sửa giao diện hoặc thử kết nối.

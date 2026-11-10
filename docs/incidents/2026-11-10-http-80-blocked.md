# Sự cố: Website Todo không thể truy cập do chặn cổng HTTP 80 (diễn tập)

- **Ngày:** 2026-11-10 (giờ Việt Nam, UTC+7)
- **Người xử lý:** Đặng Vĩnh Quang; Eric thao tác AWS Security Group.
- **Loại:** Diễn tập có chủ đích, xóa quy tắc inbound HTTP TCP 80 trong AWS Security Group.
- **Mức độ:** Nghiêm trọng đối với khả năng truy cập từ bên ngoài; ứng dụng nội bộ vẫn hoạt động.

## Diễn biến

| Giờ (UTC+7) | Việc xảy ra | Nguồn |
|---|---|---|
| 2026-11-10 19:45:36 | Eric xóa quy tắc inbound HTTP TCP 80 | --- |
| 2026-11-10 19:45:55 | Truy cập website từ trình duyệt bị `ERR_CONNECTION_TIMED_OUT` | [Ảnh trình duyệt](docs\evidence\week-4\incidents\incident-03-port-80\01-delete-rule-http-tcp-80.png) |
| 2026-11-10 19:46:05 | `curl.exe` từ máy cá nhân timeout sau khoảng 10 giây | [Ảnh PowerShell](docs\evidence\week-4\incidents\incident-03-port-80\01-delete-rule-http-tcp-80.png) |
| 2026-11-10 19:47:21 | Health Check nội bộ trên EC2 trả HTTP 200 | [Ảnh terminal](docs\evidence\week-4\incidents\incident-03-port-80\02-check-docker-and-health-check.png) |
| Chưa ghi nhận | Discord không gửi cảnh báo cho tình huống này | --- |

## Số liệu

| Chỉ số | Mốc | Thời gian |
|---|---|---|
| Từ lúc chặn cổng đến lúc ghi nhận lỗi bên ngoài | 19:45:36 → 19:45:55 | Khoảng 19 giây |
| Thời gian từ lúc chặn cổng đến Health Check | 19:45:36 → 19:47:21 | Khoảng 1 phút 45 giây |
| Discord FIRING/RESOLVED | Không có | Không áp dụng |

## Phát hiện

Sau khi quy tắc inbound HTTP TCP 80 bị xóa khỏi AWS Security Group, người dùng bên ngoài không thể truy cập website.

Trình duyệt hiển thị:

```text
ERR_CONNECTION_TIMED_OUT
```

Lệnh kiểm tra từ máy cá nhân cũng bị timeout sau khoảng 10 giây.

Trong khi đó, Health Check nội bộ trên EC2 vẫn hoạt động:

```text
HTTP/1.1 200 OK
{"status":"ok"}
```

Điều này cho thấy ứng dụng và Nginx vẫn hoạt động bên trong máy chủ, nhưng khả năng truy cập từ Internet bị ảnh hưởng.

## Nguyên nhân

Quy tắc inbound HTTP TCP 80 trong AWS Security Group bị xóa có chủ đích để diễn tập.

Khi cổng 80 không còn được cho phép, các yêu cầu HTTP từ bên ngoài không thể đến được máy chủ EC2.

Sự cố nằm ở lớp kết nối mạng bên ngoài, không phải lỗi của ứng dụng hoặc PostgreSQL.

## Cách xử lý

- Kiểm tra website từ máy tính cá nhân bằng trình duyệt và PowerShell.
- Xác nhận lỗi `ERR_CONNECTION_TIMED_OUT`.
- SSH vào EC2 để kiểm tra Health Check nội bộ:

```bash
curl -i http://localhost/health
```

- Xác nhận kết quả HTTP 200 và trạng thái container vẫn hoạt động.
- Eric khôi phục quy tắc inbound HTTP TCP 80 trong AWS Security Group.
- Sau khi khôi phục, cần kiểm tra lại website từ bên ngoài và xác nhận truy cập thành công.

## Bài học và việc cần làm

- Website không truy cập được từ Internet không đồng nghĩa với việc ứng dụng bên trong EC2 đã dừng.
- Cần phân biệt lỗi ứng dụng với lỗi kết nối mạng.
- Health Check nội bộ giúp xác định ứng dụng vẫn hoạt động trong khi truy cập bên ngoài bị gián đoạn.
- AWS Security Group cần duy trì quy tắc HTTP TCP 80 để người dùng truy cập website.
- Tình huống này không tạo Discord alert theo thiết kế/ghi nhận của nhóm.
- Cần ghi lại thời gian Eric xóa và khôi phục rule để tính chính xác thời gian gián đoạn.
- Bổ sung ảnh Security Group sau khi khôi phục và kết quả truy cập website HTTP 200 từ bên ngoài.

**Kết luận:** Đã mô phỏng thành công tình huống chặn cổng HTTP 80. Website bên ngoài bị timeout trong khi Health Check nội bộ vẫn trả HTTP 200. Nhóm xác nhận tình huống này không gửi Discord alert.
# Sự cố: Website Todo không thể truy cập do chặn cổng HTTP 80 (diễn tập)

- **Ngày:** 2026-11-10 (giờ Việt Nam, UTC+7)
- **Người xử lý:** Đặng Vĩnh Quang; Eric thao tác AWS Security Group.
- **Loại:** Diễn tập có chủ đích, xóa quy tắc inbound HTTP TCP 80 trong AWS Security Group.
- **Mức độ:** Nghiêm trọng đối với khả năng truy cập từ bên ngoài; ứng dụng nội bộ vẫn hoạt động.

## Diễn biến

| Giờ Việt Nam (UTC+7) | Việc xảy ra | Nguồn |
|---|---|---|
| 2026-11-10 18:59:52 | Eric xóa rule inbound HTTP TCP 80 (0.0.0.0/0) trong Security Group | [CloudTrail RevokeSecurityGroupIngress](../evidence/week-4/incidents/incident-03-port-80/03-cloudtrail-revoke-port-80.png) |
| Khoảng 19:48 theo đồng hồ máy chụp | Trình duyệt báo ERR_CONNECTION_TIMED_OUT; curl.exe timeout sau khoảng 10 giây | [Ảnh truy cập bên ngoài bị timeout](../evidence/week-4/incidents/incident-03-port-80/01-delete-rule-http-tcp-80.png) |
| 2026-11-10 19:47:21 | /health nội bộ trả HTTP 200, status=ok; Date header ghi 12:47:21 GMT | [Ảnh Health Check nội bộ HTTP 200](../evidence/week-4/incidents/incident-03-port-80/02-check-docker-and-health-check.png) |
| 2026-11-10 20:50:53 | Eric thêm lại rule inbound HTTP TCP 80 (0.0.0.0/0); còn thiếu ảnh truy cập bên ngoài sau khôi phục | [CloudTrail AuthorizeSecurityGroupIngress](../evidence/week-4/incidents/incident-03-port-80/04-cloudtrail-authorize-port-80.png) |

Giờ xóa và thêm lại rule lấy từ CloudTrail Event history, trường `eventTime` (11:59:52Z và 13:50:53Z, cộng 7 giờ ra giờ Việt Nam). Giữ riêng giờ máy chụp và Date header server; không lấy chúng để suy ra thời điểm xóa/mở rule. Tình huống chỉ chặn kết nối bên ngoài nên không kỳ vọng cảnh báo AppDown/DatabaseDown từ giám sát nội bộ.

## Số liệu

| Chỉ số | Mốc | Thời gian |
|---|---|---|
| Từ lúc chặn cổng đến lúc ghi nhận lỗi bên ngoài | 18:59:52 → khoảng 19:48 | Không tính: ảnh timeout là lúc nhóm kiểm tra, không phải lúc lỗi bắt đầu |
| Thời gian rule HTTP 80 bị xóa (website bên ngoài không truy cập được) | 18:59:52 → 20:50:53 (CloudTrail) | 1 giờ 51 phút 01 giây |
| Health Check nội bộ | 19:47:21 | HTTP 200 |
| Discord FIRING/RESOLVED | Không có | Không áp dụng |

Khoảng 1 giờ 51 phút là thời gian rule bị xóa trong buổi diễn tập, không dùng làm số đo tốc độ khôi phục.

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
- Thời gian xóa và khôi phục rule đã lấy từ CloudTrail (18:59:52 và 20:50:53).
- Bổ sung ảnh Security Group sau khi khôi phục và kết quả truy cập website HTTP 200 từ bên ngoài.

**Kết luận:** Đã mô phỏng thành công tình huống chặn cổng HTTP 80. Website bên ngoài bị timeout trong khi Health Check nội bộ vẫn trả HTTP 200. Nhóm xác nhận tình huống này không gửi Discord alert. Cần bổ sung bằng chứng truy cập bên ngoài sau khi khôi phục rule để xác nhận hoàn tất toàn bộ quá trình.

# Sự cố: Todo App không kết nối được PostgreSQL (diễn tập)

- **Ngày:** 2026-11-09 (giờ Việt Nam, UTC+7)
- **Người xử lý:** Đặng Vĩnh Quang; Eric hỗ trợ khôi phục cấu hình database.
- **Loại:** Diễn tập có chủ đích, thay đổi `APP_DB_PASSWORD` thành giá trị không chính xác.
- **Mức độ:** Nghiêm trọng (ứng dụng không thể kết nối cơ sở dữ liệu).

## Diễn biến

| Giờ (UTC+7) | Việc xảy ra | Nguồn |
|---|---|---|
| 22:51:28 | Endpoint `/health` trả HTTP 500 Internal Server Error | Ảnh terminal, Date: 15:51:28 GMT |
| 22:51:28 | PostgreSQL ghi nhận lỗi xác thực user `todo_app` | Log PostgreSQL |
| Chưa xác định | Discord gửi `[FIRING:1] DatabaseDown` | Ảnh Discord, giao diện hiển thị 10:03 SA |
| Chưa ghi nhận | Eric khôi phục mật khẩu/cấu hình database | Thông tin phối hợp trong nhóm |
| Chưa ghi nhận | Discord gửi `[RESOLVED] DatabaseDown` | Ảnh Discord, giao diện hiển thị 10:45 SA |

*Lưu ý: Hai mốc giờ Discord được ghi theo đúng giờ hiển thị trên ảnh. Chưa xác nhận ngày và múi giờ của chúng nên không dùng để tính thời gian phát hiện hoặc phục hồi.*

## Số liệu

| Chỉ số | Mốc | Thời gian |
|---|---|---|
| Lỗi database xuất hiện | 22:51:28 | Đã ghi nhận |
| Từ lúc xảy ra lỗi đến Discord FIRING | Chưa đối chiếu được | Chưa tính |
| Thời gian ứng dụng bị lỗi | Chưa có mốc Health Check phục hồi chính xác | Chưa tính |
| Discord RESOLVED | 10:45 SA (theo ảnh) | Chưa đối chiếu được |

## Phát hiện

Sau khi thay đổi `APP_DB_PASSWORD` thành giá trị không chính xác và tạo lại container app, endpoint `/health` trả về:

- HTTP 500 Internal Server Error.
- Nội dung JSON: `{"detail":"cannot connect to database","status":"error"}`.

Log PostgreSQL ghi nhận nhiều lần lỗi:

```text
FATAL: password authentication failed for user "todo_app"
```

Discord gửi cảnh báo:

```text
[FIRING:1] DatabaseDown app (app:8000 critical)
```

Nội dung cảnh báo cho biết metric `todo_db_up` bằng 0 liên tục trong 1 phút.

Sau đó Discord hiển thị:

```text
[RESOLVED] DatabaseDown app (app:8000 critical)
```

## Nguyên nhân

Mật khẩu ứng dụng sử dụng để xác thực với PostgreSQL không khớp với mật khẩu của user `todo_app`.

Container ứng dụng vẫn chạy nhưng không thể thiết lập kết nối database, dẫn đến Health Check thất bại.

## Cách xử lý

- Kiểm tra biến `APP_DB_PASSWORD` trong `.env` nhưng không hiển thị mật khẩu ra màn hình hoặc ảnh chụp.
- Kiểm tra log ứng dụng và PostgreSQL.
- Xác nhận lỗi xác thực của user `todo_app`.
- Eric hỗ trợ khôi phục mật khẩu/cấu hình database về giá trị đúng.
- Cần kiểm tra lại Health Check sau khi khôi phục:

```bash
curl -i http://localhost/health
```

- Xác nhận website hoạt động bình thường và container app kết nối database thành công.

**Lưu ý:** Không đưa mật khẩu database hoặc nội dung file `.env` vào tài liệu và Git.

## Bài học và việc cần làm

- Không nên chỉ dựa vào trạng thái container để đánh giá ứng dụng đang hoạt động bình thường.
- Cần kiểm tra Health Check và log PostgreSQL để xác định lỗi xác thực database.
- Cảnh báo DatabaseDown giúp phát hiện vấn đề kết nối DB ngay cả khi container app vẫn đang chạy.
- Cần sao lưu cấu hình trước khi thay đổi mật khẩu và chỉ khôi phục từ bản sao lưu an toàn.
- Bổ sung ảnh Health Check HTTP 200 sau khi Eric khôi phục database.
- Đối chiếu thời gian Discord với log server để tính thời gian phát hiện và phục hồi chính xác.

**Kết luận:** Đã mô phỏng thành công lỗi xác thực PostgreSQL và xác nhận hệ thống gửi cảnh báo DatabaseDown. Eric đã hỗ trợ khôi phục cấu hình database. Tuy nhiên, chưa có ảnh Health Check HTTP 200 sau khi khôi phục để xác nhận đầy đủ trạng thái hoạt động của ứng dụng.
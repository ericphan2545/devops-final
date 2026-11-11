# Sự cố: Todo App không kết nối được PostgreSQL (diễn tập)

- **Ngày diễn tập:** 2026-11-09; ảnh xác nhận Health Check sau khôi phục ghi ngày 2026-11-10 (giờ Việt Nam, UTC+7).
- **Người xử lý:** Đặng Vĩnh Quang; Eric hỗ trợ khôi phục cấu hình database.
- **Loại:** Diễn tập có chủ đích, thay đổi `APP_DB_PASSWORD` thành giá trị không chính xác.
- **Mức độ:** Nghiêm trọng (ứng dụng không thể kết nối cơ sở dữ liệu).

## Diễn biến

| Giờ Việt Nam (UTC+7) | Việc xảy ra | Nguồn |
|---|---|---|
| 2026-11-09 22:51:28 | /health trả HTTP 500; Date header ghi 15:51:28 GMT | [Ảnh HTTP 500 và log PostgreSQL](../evidence/week-4/incidents/incident-02-database-down/01-change-dbpassword-wrong-format.png) |
| 2026-11-09 22:51:28 | PostgreSQL báo password authentication failed for user todo_app | [Ảnh HTTP 500 và log PostgreSQL](../evidence/week-4/incidents/incident-02-database-down/01-change-dbpassword-wrong-format.png) |
| Chưa xác định ngày/múi giờ | Discord FIRING DatabaseDown; ảnh hiển thị 10:03 SA tại 09/11 | [Ảnh Discord DatabaseDown](../evidence/week-4/incidents/incident-02-database-down/02-wait-for-discord-announ.png) |
| Chưa có giờ chính xác | Eric hỗ trợ khôi phục cấu hình/mật khẩu ứng dụng | Phối hợp trong nhóm |
| Chưa xác định ngày/múi giờ | Discord RESOLVED DatabaseDown; ảnh hiển thị 10:45 SA tại 09/11 | [Ảnh Discord DatabaseDown](../evidence/week-4/incidents/incident-02-database-down/02-wait-for-discord-announ.png) |
| 2026-11-10 17:56:45 | Xác nhận /health trả HTTP 200, status=ok; Date header ghi 10:56:45 GMT | [Ảnh kiểm tra sau khôi phục](../evidence/week-4/incidents/incident-02-database-down/03-health-check-after-recover-db-password.jpg) |

Mốc HTTP 200 là thời điểm kiểm tra sau khôi phục, không phải thời điểm ứng dụng bắt đầu hồi phục. Hai giờ Discord chưa có ngày/múi giờ đi kèm, nên không ghép với log server để tính thời gian phát hiện hoặc downtime.

## Số liệu

| Chỉ số | Mốc | Kết quả |
|---|---|---|
| Health Check lỗi | 2026-11-09 22:51:28 (UTC+7) | HTTP 500, không kết nối được database |
| Health Check sau khôi phục | 2026-11-10 17:56:45 (UTC+7) | HTTP 200, status=ok |
| Từ lúc lỗi đến Discord FIRING | Chưa đối chiếu được ngày/múi giờ Discord | Chưa tính |
| Downtime và thời gian phục hồi | Chưa có mốc bắt đầu hồi phục chính xác | Chưa tính |

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
- Kiểm tra Health Check sau khi khôi phục:

```bash
curl -i http://localhost/health
```

- [Ảnh kiểm tra sau khôi phục](../evidence/week-4/incidents/incident-02-database-down/03-health-check-after-recover-db-password.jpg) xác nhận HTTP 200 và status=ok; ảnh này chứng minh app đã kết nối DB tại lúc kiểm tra, không xác định thời điểm bắt đầu hồi phục.

**Lưu ý:** Không đưa mật khẩu database hoặc nội dung file `.env` vào tài liệu và Git.

## Bài học và việc cần làm

- Không nên chỉ dựa vào trạng thái container để đánh giá ứng dụng đang hoạt động bình thường.
- Cần kiểm tra Health Check và log PostgreSQL để xác định lỗi xác thực database.
- Cảnh báo DatabaseDown giúp phát hiện vấn đề kết nối DB ngay cả khi container app vẫn đang chạy.
- Cần sao lưu cấu hình trước khi thay đổi mật khẩu và chỉ khôi phục từ bản sao lưu an toàn.
- Đã bổ sung ảnh Health Check HTTP 200 sau khôi phục; lần sau cần ghi giờ ngay trước và sau thao tác khôi phục.
- Đối chiếu thời gian Discord với log server để tính thời gian phát hiện và phục hồi chính xác.

**Kết luận:** Đã diễn tập lỗi xác thực PostgreSQL, có ảnh cảnh báo DatabaseDown và ảnh HTTP 200 sau khôi phục. Thời gian phát hiện, downtime và thời gian phục hồi chưa được tính vì các mốc chưa đủ để đối chiếu chính xác.

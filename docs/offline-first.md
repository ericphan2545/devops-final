# Thiết kế ngoại tuyến và đồng bộ

## Dữ liệu

PostgreSQL: `todos` giữ ID, UUID ổn định, title, due_date, due_time, priority (0 không đặt, 1 cao, 2 trung bình, 3 thấp), tags, completed, updated_at.

`todo_operations` giữ kết quả theo UUID thao tác; `todo_tombstones` giữ UUID đã xoá.

IndexedDB `todo-workspace-v1`, object store `workspace`, key `state` chứa:

- `serverTasks`: snapshot server đã xác nhận.
- `queue`: các thao tác chưa xác nhận, mỗi thao tác có op_id, type, client_id, payload, created_at.
- `lastSynced`: thời điểm đối chiếu thành công khi hàng đợi rỗng.
- `lease`: quyền đồng bộ ngắn hạn của tab; một giao dịch IndexedDB quyết định tab giữ lease.

UI được dựng từ snapshot cộng các thao tác chờ. Xoá được áp dụng ngay trong projection nhưng vẫn giữ thao tác trong queue đến khi server xác nhận.

## Một lần gửi

1. Ghi thao tác vào IndexedDB trong giao dịch readwrite rồi mới báo đã lưu.
2. Tab nhận lease, kiểm tra `/health` và lấy danh sách server.
3. Gửi thao tác cũ nhất lên `/api/operations`, timeout 7 giây.
4. Server khoá theo op_id, trả kết quả cũ nếu đã xử lý. Nếu chưa, khoá theo client_id, thay đổi dữ liệu và ghi kết quả trong cùng giao dịch.
5. Client cập nhật snapshot và bỏ thao tác sau khi nhận xác nhận đúng op_id/client_id.
6. Mất phản hồi: thao tác vẫn trong queue, lần sau gửi lại cùng mã.
7. Kết thúc lấy lại danh sách. Chỉ nhãn xanh khi health/API đều thành công và queue rỗng.

Không xoá thao tác bị server từ chối một cách im lặng: nó vẫn được giữ và lỗi được hiển thị. Trường hợp việc đã bị xoá ở server thì xoá thắng cập nhật cũ; client được thông báo và dọn thao tác liên quan.

## Nhiều tab và nhiều thiết bị

Lease IndexedDB kéo dài 30 giây, được gia hạn trước mỗi request; request timeout 7 giây. BroadcastChannel thông báo các tab cùng origin về dữ liệu mới. Server vẫn chống trùng nếu hai tab gửi lại cùng thao tác.

Không có tài khoản hoặc phân quyền riêng. Cập nhật cùng trường theo thứ tự nhận ở server; đây không phải CRDT hay trình giải quyết xung đột có lịch sử phiên bản.

## Cache trang

Service Worker có scope `/`, tên cache theo APP_VERSION. Network-first cho navigation, CSS và JS; khi mạng/server lỗi thì dùng bản cache. Không can thiệp API, health, metrics hoặc POST.

HTTPS hoặc localhost là điều kiện để đăng ký Service Worker. Trang phải từng được mở và cache thành công. IndexedDB vẫn dùng được cho trang đang mở khi không có Service Worker, nhưng lúc đó không hứa mở lại toàn bộ trang ngoại tuyến.

Chưa triển khai Background Sync khi trình duyệt đóng. Khi ứng dụng mở, nó thử lại theo sự kiện online, khi trở lại tab và theo chu kỳ 25 giây.

## Form không JavaScript

Thêm, xoá và hoàn thành vẫn dùng POST trên server. Các trường metadata có name chuẩn trong form. Mọi xử lý JavaScript là phần nâng cấp; nếu không mở được IndexedDB, ứng dụng giữ form gốc và báo rõ ngoại tuyến chưa sẵn sàng.

## Kiểm chứng cần làm trên trình duyệt triển khai

- Offline rồi reload sau khi SW ready, kiểm tra lại dữ liệu/hàng đợi.
- Tắt mạng sau khi server nhận request nhưng trước khi client nhận response, kiểm tra không trùng.
- Hai tab cùng origin cập nhật và gửi lại thao tác.
- Hai thiết bị sửa cùng một trường; xác nhận quy tắc last received wins.
- Từ chối/xoá bộ nhớ site: không được giả báo dữ liệu vẫn được giữ.
- Giữ dữ liệu sau migration của volume tuần 1; không chạy down -v.


## Phân loại tuỳ chỉnh

Snapshot IndexedDB schema 1 bổ sung `categories`. Snapshot cũ chưa có trường này được điền từ bootstrap khi mở ứng dụng; ba ID `ca-nhan`, `devops`, `hoc-tap` được giữ nguyên.

Hàng đợi nhận loại `category_create` trước các thao tác tạo/sửa công việc sử dụng nhóm đó. `op_id` vẫn được lưu trong nhật ký PostgreSQL cùng giao dịch với phân loại. Gửi lại khi mất phản hồi không tạo thêm dòng.

Server chuẩn hoá tên để nhận diện trùng (không phân biệt dấu, hoa/thường, khoảng trắng thừa), nhưng giữ tên hiển thị đầu tiên. Khi hai thiết bị tạo cùng tên với UUID khác nhau, phản hồi trả ID nhóm đã có. Client đổi ID nhóm trong các thao tác công việc đang chờ rồi mới gửi tiếp. Không gửi dữ liệu mẫu hoặc chỉ lưu tên nhóm trong localStorage.

Migration tạo bảng `todo_categories` và seed ba nhóm cũ bằng `ON CONFLICT DO NOTHING`; không sửa hoặc xoá công việc, không xoá nhóm tuỳ chỉnh khi chạy migration lại.


### Xoá phân loại

Menu ⋯ cạnh từng nhóm mở hộp thoại xác nhận, nêu số công việc được gỡ nhãn. Giữ lại hoặc Escape huỷ thao tác. Xác nhận ghi `category_delete` vào IndexedDB trước khi ẩn nhóm, bỏ nhãn khỏi danh sách dự chiếu và chuyển bộ lọc đang xem về Tất cả; không xoá công việc.

`category_delete` dùng UUID của nhóm tuỳ chỉnh hoặc một trong ba ID cũ. API ghi nhật ký thao tác, lưu ID vào `todo_category_tombstones`, xoá nhóm và dùng `array_remove` gỡ nhãn khỏi công việc trong cùng giao dịch. Khoá giao dịch chung với tạo nhóm/ghi thẻ công việc ngăn trường hợp ghi đồng thời để lại nhãn mồ côi. Migration không seed lại ID đã có bản ghi xoá. Người dùng có thể tạo lại cùng tên với ID mới.

`GET /api/tasks` bổ sung `deletedCategories`; snapshot schema 1 bổ sung trường này nhưng vẫn đọc được snapshot cũ. Client ẩn nhãn đã xoá khi đọc snapshot/hàng đợi. Payload thao tác công việc đang chờ không bị viết lại khi xoá nhóm, để giữ nguyên dấu vân tay khi gửi lại một yêu cầu đã được server nhận nhưng mất phản hồi. Server bỏ qua nhãn có bản ghi xoá khi xử lý thao tác cũ; nhãn không tồn tại và chưa từng được xoá vẫn bị từ chối. Phản hồi ID chuẩn của nhóm trùng tên cũng ánh xạ lại `category_delete` đang chờ.

Khi tắt JavaScript, form `POST /categories/delete` với `category_id` vẫn xoá nhóm và giữ công việc; không có hộp thoại xác nhận bằng JavaScript trong chế độ này.

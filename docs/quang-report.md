# PHẦN BÁO CÁO – NGƯỜI SỐ 1

# KIẾN TRÚC VÀ THIẾT KẾ HỆ THỐNG

## 1. Tổng quan kiến trúc

Dự án xây dựng hệ thống Todo Application dưới dạng ứng dụng web, triển khai trên máy chủ Amazon EC2 sử dụng hệ điều hành Ubuntu 24.04. Hệ thống sử dụng Docker Compose để quản lý các dịch vụ và Docker Network để hỗ trợ giao tiếp nội bộ giữa các container.

Kiến trúc hệ thống gồm 7 dịch vụ chính:

- **Nginx:** Đóng vai trò Reverse Proxy và là điểm tiếp nhận các yêu cầu HTTP từ người dùng thông qua cổng 80. Nginx chuyển tiếp yêu cầu đến ứng dụng Flask và hỗ trợ truy cập Grafana thông qua đường dẫn `/grafana/`.
- **Flask / Gunicorn:** Chạy ứng dụng Todo trên cổng nội bộ 8000. Ứng dụng cung cấp các chức năng chính, đồng thời có endpoint `/health` để kiểm tra trạng thái hoạt động và `/metrics` để cung cấp dữ liệu giám sát.
- **PostgreSQL 17:** Hệ quản trị cơ sở dữ liệu lưu trữ dữ liệu của ứng dụng. PostgreSQL giao tiếp với Flask thông qua Docker Network và sử dụng volume `db-data` để lưu trữ dữ liệu lâu dài.
- **Node Exporter:** Thu thập các thông số tài nguyên của máy chủ EC2, bao gồm CPU, RAM và dung lượng ổ đĩa.
- **Prometheus:** Thu thập metrics từ ứng dụng Flask và Node Exporter. Prometheus cũng đánh giá các quy tắc cảnh báo để phát hiện những vấn đề của hệ thống.
- **Grafana:** Cung cấp giao diện dashboard để theo dõi và trực quan hóa các thông số giám sát. Grafana sử dụng Prometheus làm nguồn dữ liệu.
- **Alertmanager:** Tiếp nhận cảnh báo từ Prometheus và chuyển tiếp thông báo đến kênh Discord của nhóm.

*Sơ đồ kiến trúc hệ thống được trình bày tại Hình 1.*

## 2. Thiết kế triển khai và mạng

Hệ thống được triển khai trên Amazon EC2 với Ubuntu 24.04. Docker Compose được sử dụng để khởi chạy và quản lý các container. Các dịch vụ giao tiếp với nhau thông qua mạng nội bộ Docker Compose Network.

Nginx là thành phần duy nhất được thiết kế làm điểm truy cập HTTP công khai thông qua cổng 80. AWS Security Group kiểm soát lưu lượng truy cập vào máy chủ, trong đó cổng 80 phục vụ truy cập ứng dụng và cổng 22 phục vụ kết nối SSH để quản trị máy chủ.

Các cổng của ứng dụng Flask, PostgreSQL và những dịch vụ giám sát được sử dụng trong phạm vi giao tiếp nội bộ. Không nên mở trực tiếp các cổng này ra Internet.

Đối với cơ sở dữ liệu, hệ thống sử dụng Docker volume có tên `db-data` nhằm duy trì dữ liệu ngay cả khi container PostgreSQL được khởi động lại hoặc tạo lại.

Thiết kế này giúp phân tách các thành phần ứng dụng, cơ sở dữ liệu và giám sát, đồng thời hạn chế việc công khai những dịch vụ không cần thiết.

## 3. Thiết kế giám sát và cảnh báo

Hệ thống tích hợp Prometheus, Grafana, Node Exporter và Alertmanager để theo dõi trạng thái hoạt động của ứng dụng và máy chủ.

Prometheus định kỳ thu thập metrics từ endpoint `/metrics` của ứng dụng Flask và Node Exporter. Các dữ liệu này được Grafana sử dụng để hiển thị trên dashboard.

Khi phát hiện điều kiện bất thường theo các quy tắc cảnh báo đã cấu hình, Prometheus gửi cảnh báo đến Alertmanager. Alertmanager tiếp tục chuyển thông báo đến Discord để các thành viên trong nhóm có thể theo dõi và xử lý sự cố.

Việc tích hợp hệ thống giám sát giúp nhóm nhận biết các vấn đề như ứng dụng ngừng hoạt động, lỗi kết nối cơ sở dữ liệu và tình trạng sử dụng tài nguyên máy chủ.

## 4. Tích hợp CI/CD

Mã nguồn dự án được quản lý thông qua GitHub Repository. Các thành viên thực hiện thay đổi mã nguồn và đóng góp thông qua quy trình Pull Request và Merge vào nhánh chính.

GitHub Actions được sử dụng để tự động thực hiện các bước kiểm thử, build và triển khai ứng dụng lên EC2 theo workflow đã cấu hình.

Cách triển khai này giúp giảm thao tác thủ công khi cập nhật ứng dụng. Các thành viên có thể đóng góp mã nguồn mà không cần sử dụng chung tài khoản AWS. Quyền truy cập trực tiếp vào máy chủ được quản lý riêng thông qua SSH.

# NHỮNG KHÓ KHĂN VÀ THÁCH THỨC

## 1. Đảm bảo tính sẵn sàng của ứng dụng

Trong quá trình kiểm tra hệ thống, nhóm đã thực hiện tình huống mô phỏng ứng dụng bị ngừng hoạt động bằng cách dừng container Flask.

Khi container ứng dụng dừng, Nginx không thể chuyển tiếp yêu cầu đến dịch vụ phía sau. Kết quả kiểm tra endpoint `/health` từ bên ngoài trả về lỗi HTTP 502 Bad Gateway.

Nhóm tiến hành kiểm tra trạng thái container và log của Nginx để xác định nguyên nhân. Sau khi khởi động lại container ứng dụng, endpoint `/health` trả về HTTP 200 với nội dung `{"status":"ok"}`.

Qua tình huống này, nhóm nhận thấy việc kiểm tra trạng thái container cần được kết hợp với health check và giám sát từ bên ngoài để xác định chính xác tình trạng hoạt động của ứng dụng.

## 2. Lỗi xác thực và kết nối cơ sở dữ liệu

Một vấn đề khác được phát hiện trong quá trình diễn tập là cấu hình sai mật khẩu kết nối PostgreSQL.

Trong tình huống này, container Flask vẫn ở trạng thái hoạt động nhưng không thể xác thực với PostgreSQL. Endpoint `/health` trả về HTTP 500 do không thể kết nối cơ sở dữ liệu.

Log của PostgreSQL ghi nhận lỗi `password authentication failed` đối với người dùng `todo_app`. Hệ thống giám sát cũng ghi nhận chỉ số `todo_db_up=0` và Alertmanager gửi cảnh báo `DatabaseDown` đến Discord.

Sự cố cho thấy trạng thái container đang chạy không đồng nghĩa với việc toàn bộ chức năng ứng dụng hoạt động bình thường. Việc kiểm tra kết nối cơ sở dữ liệu là cần thiết để đánh giá chính xác tình trạng hệ thống.

Quá trình khôi phục cần sử dụng lại cấu hình môi trường ban đầu và tạo lại container ứng dụng, tránh thay đổi mật khẩu thực tế của PostgreSQL trong quá trình diễn tập.

## 3. Quản lý quyền truy cập AWS và cấu hình mạng

Dự án sử dụng tài khoản AWS riêng do thành viên phụ trách quản lý thay vì tiếp tục sử dụng môi trường AWS Academy Learner Lab. Cách triển khai này giúp máy chủ duy trì hoạt động mà không phụ thuộc vào thời gian của phiên lab.

Tuy nhiên, quyền truy cập AWS Console và quản trị hạ tầng được giới hạn cho thành viên quản lý tài khoản. Vì vậy, những công việc cần thao tác trực tiếp trên AWS, chẳng hạn thay đổi AWS Security Group, phải được phối hợp với thành viên có quyền truy cập.

Đây là một thách thức trong quá trình tổ chức diễn tập sự cố và thu thập bằng chứng. Nhóm cần phân công rõ trách nhiệm và thống nhất thời gian thực hiện trước khi tiến hành những thao tác ảnh hưởng đến hạ tầng.

## 4. Phối hợp triển khai và diễn tập sự cố

Dự án sử dụng GitHub Actions để tự động hóa quá trình triển khai. Tuy nhiên, việc triển khai phiên bản mới trong lúc đang diễn tập sự cố có thể làm thay đổi trạng thái hệ thống và ảnh hưởng đến kết quả kiểm tra.

Ví dụ, quá trình deploy có thể tạo lại container ứng dụng hoặc thực hiện các script cấu hình cơ sở dữ liệu. Điều này có thể khiến diễn biến sự cố không còn đúng với kịch bản ban đầu.

Do đó, nhóm cần thống nhất thời gian diễn tập và tạm dừng các hoạt động deploy không cần thiết trong thời gian kiểm tra. Mỗi tình huống cần ghi nhận thời điểm gây lỗi, thời điểm phát hiện, quá trình khoanh vùng nguyên nhân và thời điểm khôi phục.

Việc chuẩn hóa quy trình giúp kết quả kiểm tra có thể được đối chiếu, tổng hợp và sử dụng làm bằng chứng trong báo cáo cuối kỳ.
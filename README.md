# Todo · DevOps Final Project

Ứng dụng quản lý công việc dùng Flask và PostgreSQL, triển khai bằng Docker Compose trên AWS EC2. Giao diện tối giản, tập trung vào việc ghi lại, tìm và quản lý công việc.

## Chức năng

- Xem, thêm và xoá công việc; dữ liệu được lưu trong PostgreSQL.
- Giao diện tiếng Việt, một cột, thích ứng điện thoại và máy tính.
- Tìm công việc không phân biệt chữ hoa/thường và dấu tiếng Việt; nhấn `/` để tìm nhanh khi không nhập liệu.
- Sắp xếp theo thứ tự ID cũ nhất, mới nhất hoặc tên A–Z.
- Đếm ký tự, giới hạn ô nhập 200 ký tự và chặn tên chỉ có khoảng trắng trong trình duyệt.
- Xác nhận trước khi xoá; chọn **Giữ lại** hoặc nhấn **Escape** để huỷ hộp thoại.
- Giao diện sáng/tối, ghi nhớ lựa chọn trên trình duyệt khi localStorage khả dụng.
- Hiển thị mã phiên bản triển khai ở cuối trang.

Lọc và sắp xếp chỉ thay đổi cách xem danh sách trên trình duyệt, không cập nhật dữ liệu trong DB. Cũ/mới dựa trên ID, không phải ngày tạo. Ứng dụng hiện chưa có đăng nhập, deadline, người phụ trách hoặc đánh dấu hoàn thành.

Khi JavaScript tắt, các form xem/thêm/xoá vẫn hoạt động; tìm kiếm, sắp xếp, theme và hộp thoại xác nhận không được kích hoạt. Validation phía trình duyệt không thay thế validation phía server.

## Công nghệ và kiến trúc

| Thành phần | Vai trò |
| --- | --- |
| Flask, Gunicorn | Xử lý request và phục vụ ứng dụng tại cổng 8000 trong mạng Compose |
| PostgreSQL 17, psycopg | Lưu công việc trong bảng `todos` |
| Nginx | Nhận HTTP ở cổng 80 và chuyển tiếp vào app |
| Docker Compose | Chạy ba service `db`, `app`, `nginx` và quản lý volume |
| HTML/Jinja, CSS, JavaScript | Giao diện, tìm kiếm, sắp xếp và thao tác trên trình duyệt |
| pytest | Kiểm thử ứng dụng với PostgreSQL thật |
| AWS EC2 | Máy chủ triển khai; cấu hình mục tiêu Ubuntu 24.04, t3.small |

![Sơ đồ kiến trúc](docs/architecture.png)

```text
Trình duyệt
    │ HTTP :80
    ▼
  Nginx → Flask/Gunicorn :8000 → PostgreSQL 17 :5432
                                      │
                                      ▼
                                 volume db-data
```

- Chỉ Nginx publish cổng 80 ra host; app và DB không publish cổng.
- Các service trong cùng mạng Compose có thể kết nối với nhau.
- App đợi PostgreSQL healthy trước khi khởi động.
- Nginx chặn đường dẫn `/metrics` bằng HTTP 403; Prometheus sau này có thể lấy metrics trực tiếp từ app trong mạng Compose.
- `/health` kiểm tra khả năng kết nối từ app tới DB.
- Volume `db-data` lưu dữ liệu độc lập với vòng đời container; volume không phải một thành phần mạng và không thay thế backup.

Mở [file sơ đồ](docs/architecture.drawio) bằng diagrams.net để chỉnh sửa. Nếu thay đổi kiến trúc, xuất lại `docs/architecture.png`.

## Cấu trúc thư mục

```text
devops-final/
├── app/
│   ├── .dockerignore
│   ├── Dockerfile
│   ├── app.py
│   ├── requirements.txt
│   ├── static/
│   │   ├── style.css         # Giao diện Todo tối giản, responsive, sáng/tối
│   │   └── app.js            # Tìm kiếm, sắp xếp, validation và xác nhận xoá
│   └── templates/
│       └── index.html       # Template Jinja
├── db/init.sql
├── nginx/default.conf
├── scripts/
│   ├── setup-server.sh      # Khởi tạo EC2 qua User data
│   └── deploy.sh            # Build, chạy và kiểm tra health
├── tests/test_app.py
├── docs/
│   ├── architecture.drawio
│   ├── architecture.png
│   └── evidence/            # Ảnh và video minh chứng tuần 1
├── .env.example
├── .gitignore
├── docker-compose.yml
├── pytest.ini
├── requirements-dev.txt
└── README.md
```

Giao diện không dùng CDN hoặc thư viện frontend bên ngoài. Flask phục vụ CSS và JavaScript qua `/static/`.

## Chạy trên máy cá nhân

Yêu cầu: Git, Docker Engine và Docker Compose plugin. Trên Windows có thể dùng Docker Desktop chạy Linux containers.

```bash
git clone https://github.com/ericphan2545/devops-final.git
cd devops-final
```

Tạo file `.env` từ file mẫu. Trong PowerShell:

```powershell
Copy-Item .env.example .env
```

Trong Linux, macOS hoặc Git Bash:

```bash
cp .env.example .env
```

Mở `.env`, giữ tên biến và thay mật khẩu mẫu trước lần tạo DB đầu tiên:

```dotenv
POSTGRES_USER=todo
POSTGRES_PASSWORD=YOUR_OWN_PASSWORD
POSTGRES_DB=todo
```

Thay `YOUR_OWN_PASSWORD` bằng mật khẩu của nhóm; bài thực hành có thể dùng mật khẩu dài gồm chữ và số để tránh lỗi escape biến. Không commit `.env`.

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

Mở **http://localhost**. Mong đợi có ba service đang chạy, DB healthy và giao diện thêm/xoá hoạt động. Template Jinja phải chạy qua Flask; mở trực tiếp `app/templates/index.html` sẽ không chạy được ứng dụng.

Nếu đang làm trên nhánh UI, chạy Compose tại chính thư mục checkout nhánh đó để xem bản chưa merge. Những thay đổi chưa vào `main` sẽ chưa xuất hiện khi server clone `main`.

## Triển khai lên EC2

### Chuẩn bị server

Tạo Ubuntu Server 24.04 x86_64, t3.small, ổ 20 GiB. Gắn Elastic IP nếu môi trường lab cho phép. Security Group cần cho phép HTTP 80 và SSH 22 từ nguồn quản trị/deploy phù hợp.

### Cách 1: khởi tạo bằng User data

Dán toàn bộ nội dung `scripts/setup-server.sh` vào **Advanced details → User data** khi tạo instance.

Script hiện thực hiện:

1. Cài Docker Engine và Compose plugin.
2. Thêm user `ubuntu` vào nhóm Docker.
3. Clone repo vào `/home/ubuntu/devops-todo`.
4. Tạo `.env` với mật khẩu ngẫu nhiên nếu file chưa có.
5. Build và chạy Compose.

Xem tiến độ trên server:

```bash
sudo tail -f /var/log/setup-server.log
```

Chờ `SETUP XONG`, rồi mở `http://<ELASTIC_IP>` bằng IP thật.
Script clone nhánh mặc định; cần merge code vào nhánh đó trước khi dựng một server mới.
Script hiện dùng `set -x`, có thể ghi mật khẩu sinh ra vào log. Không công khai log này; cần tắt tracing quanh đoạn tạo mật khẩu khi hoàn thiện script.

### Cách 2: triển khai thủ công

Cài Docker Engine và Compose plugin theo bước cài đặt của nhóm, kiểm tra:

```bash
docker --version
docker compose version
```

User `ubuntu` cần có quyền chạy Docker. Kết nối lại sau khi được thêm vào nhóm Docker, rồi:

```bash
git clone https://github.com/ericphan2545/devops-final.git ~/devops-todo
cd ~/devops-todo
cp .env.example .env
nano .env
```

Đổi mật khẩu trong `.env` trước khi chạy:

```bash
docker compose config --quiet
bash scripts/deploy.sh
```

Các file `.sh` cần dùng xuống dòng **LF** khi chạy trên Linux.

### Cập nhật phiên bản đã merge

Trên server:

```bash
cd ~/devops-todo
git switch main
git pull --ff-only origin main
bash scripts/deploy.sh
```

`deploy.sh` lấy mã commit hiện tại, export `APP_VERSION`, chạy `docker compose up -d --build`, reload Nginx và thử `/health` tối đa 20 lần, cách nhau 3 giây. Thời gian thực tế còn phụ thuộc thời gian phản hồi HTTP.

Thành công có dòng `Deploy OK: phiên bản <mã commit>`. Tải lại web và đối chiếu mã ở footer. Nếu giao diện còn cache cũ, nhấn **Ctrl + Shift + R**.

Chạy Compose không đặt `APP_VERSION` sẽ dùng giá trị mặc định `dev`. Script deploy chưa tự rollback khi health lỗi; nó báo lỗi và in log app.

## Kiểm tra giao diện và vận hành

Sau khi đổi UI, kiểm tra:

- Thêm một công việc, tải lại trang và xác nhận công việc còn.
- Tìm bằng từ có dấu/không dấu; thử từ khoá không tồn tại và xoá tìm kiếm.
- Đổi thứ tự cũ/mới và A–Z.
- Nhấn xoá, thử **Giữ lại**, sau đó xoá một công việc thử.
- Đổi sáng/tối và tải lại trang.
- Thu nhỏ cửa sổ hoặc xem trên điện thoại; thử tên công việc dài.
- Đối chiếu phiên bản ở footer với commit triển khai.

Trên server:

```bash
docker compose ps
curl http://localhost/health
curl -I http://localhost/metrics
docker compose logs app --tail 30
docker compose logs nginx --tail 30
docker compose logs db --tail 30
```

Trong PowerShell, dùng `curl.exe` thay cho `curl` nếu lệnh bị ánh xạ sang cmdlet PowerShell. Kết quả mong đợi: `/health` trả `{"status":"ok"}`, `/metrics` qua Nginx trả HTTP 403.

## Dữ liệu và vòng đời lab

Thêm một công việc dễ nhận biết, chạy rồi tải lại trang:

```bash
docker compose down
docker compose up -d
```

Công việc phải còn nguyên. Kiểm tra tương tự sau một lần deploy mới.

**`docker compose down -v` xoá volume và dữ liệu DB. Không dùng lệnh này để cập nhật giao diện.**

`init.sql` chỉ tự chạy khi PostgreSQL khởi tạo thư mục dữ liệu còn trống. Đổi mật khẩu trong `.env` không tự đổi mật khẩu trong DB đã có.

Theo ghi chú lab trước đây của nhóm, môi trường Sandbox có thể xoá EC2, Elastic IP và dữ liệu khi End Lab. Cần kiểm tra hành vi của phiên lab đang dùng: nếu tài nguyên bị xoá, phải dựng lại server và khôi phục dữ liệu từ backup nếu đã có; nếu chỉ dừng instance và vẫn giữ ổ đĩa/Elastic IP, có thể khởi động lại để tiếp tục. Khi IP hoặc key pair đổi, cập nhật cấu hình deploy tương ứng.

## Kiểm thử tự động

`tests/test_app.py` có bốn test dùng PostgreSQL thật:

| Test | Mục đích |
| --- | --- |
| `test_health_ok` | Health trả `ok` khi kết nối DB thành công |
| `test_add_then_read_back` | Thêm việc và đọc lại qua giao diện |
| `test_empty_title_is_not_saved` | Tên chỉ có khoảng trắng không tạo dữ liệu |
| `test_delete_removes_todo` | Xoá việc và xác nhận nó không còn trên trang |

Repo dùng `from app.app import app, get_db` cùng `pythonpath = .` trong `pytest.ini`; giữ hai cấu hình này đồng bộ.

`requirements-dev.txt` hiện đang trống. Trước khi dùng nó trong CI, cần bổ sung dependencies. Để chạy thử bằng PowerShell trong lúc đó:

```powershell
python -m pip install -r app/requirements.txt pytest
docker run -d --name pg-test -p 127.0.0.1:55432:5432 -e POSTGRES_USER=todo -e POSTGRES_PASSWORD=testpass -e POSTGRES_DB=todo postgres:17
docker exec pg-test pg_isready -U todo -d todo
```

Đợi PostgreSQL báo nhận kết nối, rồi:

```powershell
$env:DB_HOST = "localhost"
$env:PGPORT = "55432"
$env:DB_NAME = "todo"
$env:DB_USER = "todo"
$env:DB_PASSWORD = "testpass"
python -m pytest -v
```

`PGPORT` đặt cổng cho libpq vì app hiện không đọc `DB_PORT`. Mật khẩu `testpass` chỉ dành cho DB test. Không trỏ test vào DB đang sử dụng: test có ghi/xoá dữ liệu và chưa dọn hết sau mỗi lần chạy.

Xong việc, xoá container test:

```bash
docker rm -f pg-test
```

## CI/CD và phạm vi tuần 2

### Đã có trong code hiện tại

- Dockerfile, Docker Compose và volume `db-data`.
- Bốn bài test và cấu hình pytest.
- Script khởi tạo server, script deploy và biến phiên bản.
- Giao diện tối giản trong `app/templates/` và `app/static/`.

### Cần hoàn thiện hoặc xác nhận

- `requirements-dev.txt` chưa có nội dung.
- Chưa có `.github/workflows/ci-cd.yml` trong folder được kiểm tra.
- GitHub Secrets và trạng thái pipeline cần xác nhận trên GitHub.
- Chưa ghi nhận kết quả chạy test, pipeline hoặc EC2 trong lần cập nhật README này.

Luồng mục tiêu theo yêu cầu tuần 2:

```text
Push main → test với PostgreSQL tạm → build image → deploy EC2 → /health
Pull request vào main → test → build, không deploy
```

Workflow cần dùng `needs` để chỉ chạy job sau khi job trước thành công. Test lỗi thì build/deploy bị bỏ qua và server giữ bản trước. Health lỗi sau deploy khiến pipeline báo đỏ, không đồng nghĩa có rollback tự động.

Người giữ server cấu hình hai repository secrets `EC2_HOST`, `EC2_SSH_KEY`. Không commit private key. Server phải đang bật và kết nối SSH được khi deploy. Nếu dựng lại server làm thay đổi IP/key, cập nhật secrets.

Script hiện build image trên EC2, chưa dùng registry. Khi viết workflow cần bảo đảm server triển khai đúng commit đã vượt qua CI.

## Thành viên và phân công

Phân công tuần 1 được giữ theo README trước. Phần tuần 2 cần cập nhật theo công việc thực tế, không suy ra từ việc đã có file trong repo.

| Thành viên | MSSV | Phần việc tuần 1 |
| --- | --- | --- |
| Phan Tiến Thịnh | 23090023 | Tạo repo và app mẫu; EC2, Security Group, Elastic IP; cài Docker, triển khai, kiểm tra và setup-server.sh |
| Ngô Tấn Đức | 23090008 | Dockerfile, Compose, .env.example, .gitignore, Nginx, sơ đồ và README |
| Đặng Vĩnh Quang | 23090005 | Chưa ghi nhận phân công trong README trước |
| Huỳnh Hữu Như Mẫn | 23090020 | Chưa ghi nhận phân công trong README trước |

## Minh chứng tuần 1

Giữ trạng thái ghi nhận trong README trước; các ảnh không xác nhận trạng thái server ở thời điểm hiện tại.

- [x] Sơ đồ kiến trúc ([drawio](docs/architecture.drawio), [PNG](docs/architecture.png)).
- [x] EC2 Running ([ảnh](docs/evidence/ec2-running.png)).
- [x] Security Group có cổng 22 và 80 ([ảnh](docs/evidence/security-group.png)).
- [x] Docker và Compose versions ([ảnh](docs/evidence/docker-version.png)).
- [x] Ba service đang chạy, DB healthy ([ảnh](docs/evidence/compose-up-ps.png)).
- [x] App thêm/xoá ([giao diện trước khi cải tiến UI](docs/evidence/app-web.png), [video](docs/evidence/demo.mp4)).
- [x] Health/metrics ([ảnh](docs/evidence/health-metrics.png), [health qua IP public](docs/evidence/health-public-ip.png)).
- [ ] Xác nhận dữ liệu còn sau down/up ([ảnh thao tác](docs/evidence/compose-down-up.png)).
- [ ] Mỗi thành viên có commit cho phần việc thực tế.
- [x] Video demo ngắn ([video](docs/evidence/demo.mp4)).

Ảnh thuộc nhiều phiên lab nên IP có thể khác nhau. Cần chụp lại giao diện mới sau khi triển khai để minh chứng khớp code.

## Checklist minh chứng tuần 2

- [ ] Log bốn test PASSED trên PostgreSQL tạm.
- [ ] Trang Actions có ba job test, build, deploy xanh.
- [ ] Log deploy có `Deploy OK` và mã phiên bản.
- [ ] Phiên bản web khớp commit đã được kiểm tra.
- [ ] Dữ liệu còn sau deploy.
- [ ] Commit cố ý làm test lỗi bị chặn; build/deploy skip và web giữ mã cũ.
- [ ] Revert commit lỗi, pipeline xanh trở lại.
- [ ] Có hai tên secrets EC2_HOST và EC2_SSH_KEY, không lộ giá trị.
- [ ] Video push thay đổi → pipeline → giao diện cập nhật.
- [ ] Đo thời gian ba lần chạy.

| Lần | Mã commit | Total duration | Ghi chú |
| --- | --- | --- | --- |
| 1 | Chưa đo | Chưa đo | |
| 2 | Chưa đo | Chưa đo | |
| 3 | Chưa đo | Chưa đo | |

## Xử lý lỗi thường gặp

| Triệu chứng | Kiểm tra và xử lý |
| --- | --- |
| Web không mở được | Kiểm tra instance, Security Group HTTP 80, dùng http:// và đúng IP |
| Docker permission denied | Kiểm tra nhóm Docker, kết nối lại sau usermod |
| Giao diện cũ hoặc mất CSS | Build lại app, kiểm tra có app/static và route /static/style.css; tải lại bằng Ctrl + Shift + R |
| 502 sau deploy | Kiểm tra log app; sau khi app đã chạy, reload Nginx |
| DB sai mật khẩu | Đối chiếu mật khẩu tạo DB ban đầu với .env; không xoá volume khi cần giữ dữ liệu |
| Thiếu bảng todos | Kiểm tra init.sql và lần tạo volume; sao lưu trước thao tác làm mất dữ liệu |
| Script lỗi ký tự CRLF | Chuyển .sh sang LF, lưu và commit lại |
| Test không import được app | Kiểm tra pytest.ini và câu import phải đồng bộ |
| Test không kết nối DB | Kiểm tra DB test đã sẵn sàng, DB_HOST, PGPORT và các biến DB_* |

## Nguồn và phần việc tiếp theo

Nguồn app: starter được viết với sự hỗ trợ của AI (Claude). Phần UI và tài liệu được cải tiến với sự hỗ trợ của AI (Codex); nhóm kiểm tra và chịu trách nhiệm cho bản nộp.

CI/CD đầy đủ cần hoàn thiện theo checklist tuần 2. HTTPS, đăng nhập, giám sát đầy đủ, backup và rollback tự động chưa được cấu hình trong repo hiện tại.

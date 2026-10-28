# Todo · DevOps Final Project

Ứng dụng quản lý công việc dùng **Flask + PostgreSQL**, triển khai bằng **Docker Compose trên AWS EC2**, đặt sau **Nginx** và tự động kiểm tra/triển khai bằng **GitHub Actions**.

- **Repository:** [ericphan2545/devops-final](https://github.com/ericphan2545/devops-final)
- **Địa chỉ triển khai của nhóm:** [todo-devops.duckdns.org](http://todo-devops.duckdns.org)
- **Nhánh triển khai tự động:** `main`; thay đổi từ nhánh tính năng được kiểm tra qua pull request trước khi merge.
- **Phạm vi đồ án:** tuần 1 — server và triển khai đầu tiên; tuần 2 — Docker và CI/CD. Giao diện mới, phân loại tuỳ chỉnh và offline-first là **phần bonus**, không thay thế yêu cầu của hai tuần.

## Mục lục

- [1. Thành viên và phân công](#1-thành-viên-và-phân-công)
- [2. Công nghệ và kiến trúc](#2-công-nghệ-và-kiến-trúc)
- [3. Tuần 1 — Server và triển khai đầu tiên](#3-tuần-1--server-và-triển-khai-đầu-tiên)
- [4. Tuần 2 — Docker và CI/CD](#4-tuần-2--docker-và-cicd)
- [5. Phần bonus — Giao diện và quản lý công việc](#5-phần-bonus--giao-diện-và-quản-lý-công-việc)
- [6. Cấu trúc repository](#6-cấu-trúc-repository)
- [7. Chạy trên máy cá nhân](#7-chạy-trên-máy-cá-nhân)
- [8. Triển khai EC2 và DuckDNS](#8-triển-khai-ec2-và-duckdns)
- [9. Kiểm thử và kiểm tra vận hành](#9-kiểm-thử-và-kiểm-tra-vận-hành)
- [10. Dữ liệu, migration và đồng bộ](#10-dữ-liệu-migration-và-đồng-bộ)
- [11. Endpoint và form](#11-endpoint-và-form)
- [12. Minh chứng tuần 1 và tuần 2](#12-minh-chứng-tuần-1-và-tuần-2)
- [13. Xử lý sự cố](#13-xử-lý-sự-cố)
- [14. Nguồn và ghi chú](#14-nguồn-và-ghi-chú)

## 1. Thành viên và phân công

| Thành viên | MSSV | Nhiệm vụ tuần 1 | Nhiệm vụ tuần 2 |
| --- | --- | --- | --- |
| **Phan Tiến Thịnh** | 23090023 | Quản lý project/repo, app mẫu; tạo EC2, cài Docker, triển khai và chuẩn bị `setup-server.sh` | Quản lý project, server và tên miền **DuckDNS** |
| **Ngô Tấn Đức** | 23090008 | Dockerfile, Compose, môi trường, Nginx, sơ đồ kiến trúc và README | Cập nhật README; thiết kế/cải tiến **UI (bonus)** |
| **Đặng Vĩnh Quang** | 23090005 | — | workflow CI/CD, chạy pipeline, đo thời gian ba lần, kiểm tra dữ liệu sau deploy và demo chặn lỗi |
| **Huỳnh Hữu Như Mẫn** | 23090020 | — |test với PostgreSQL, script deploy/mã phiên bản và GitHub Secrets |

**UI là phần bonus, không tính vào nhiệm vụ bắt buộc của tuần 1–2.**

## 2. Công nghệ và kiến trúc

| Thành phần | Công nghệ/cấu hình trong repo |
| --- | --- |
| Backend | Python 3.12, Flask, Gunicorn; container chạy bằng user thường |
| Database | PostgreSQL 17, dữ liệu lưu trong volume `db-data` |
| Reverse proxy | Nginx, nhận HTTP cổng 80 |
| Đóng gói | Dockerfile và Docker Compose |
| CI/CD | GitHub Actions; pytest, Docker build, SSH deploy |
| Hạ tầng | EC2 Ubuntu 24.04; cấu hình nhóm dùng t3.small, ổ 20 GiB |
| Tên miền | DuckDNS: `todo-devops.duckdns.org` |
| Frontend bonus | Jinja2, HTML, CSS Variables, Vanilla JavaScript; không dùng thư viện frontend/CDN |
| Lưu ngoại tuyến | IndexedDB, localStorage cho lựa chọn giao diện, Service Worker cho bộ nhớ trang |

![Sơ đồ kiến trúc triển khai tuần 1](docs/architecture.png)

```text
Người dùng
    │ HTTP :80 — todo-devops.duckdns.org
    ▼
EC2 Ubuntu 24.04
    └── Docker Compose
         ├── Nginx :80  ──► Flask/Gunicorn :8000 ──► PostgreSQL :5432
         │                                              └── volume db-data
         └── App và DB giao tiếp qua mạng nội bộ Compose

GitHub → Actions: test → build → SSH vào EC2 → scripts/deploy.sh → /health
```

Chỉ Nginx publish cổng ra host. App và PostgreSQL không publish cổng trực tiếp ra Internet. `/health` kiểm tra kết nối DB; Nginx chặn truy cập `/metrics` từ bên ngoài bằng HTTP 403. File nguồn sơ đồ: [architecture.drawio](docs/architecture.drawio). Hình tuần 1 mô tả kiến trúc triển khai cơ bản; chi tiết bonus xem [thiết kế đồng bộ](docs/offline-first.md).

## 3. Tuần 1 — Server và triển khai đầu tiên

**Mục tiêu:** ứng dụng chạy trên EC2, thêm/xoá công việc được, có sơ đồ kiến trúc, README và minh chứng triển khai.

| Bước | Nội dung | File/kết quả trong dự án |
| --- | --- | --- |
| 1 | Tạo repo, đưa app mẫu lên GitHub | Mã nguồn Flask, template và dependencies trong `app/` |
| 2 | Viết Dockerfile | [app/Dockerfile](app/Dockerfile) |
| 3 | Docker Compose, môi trường và Git ignore | [docker-compose.yml](docker-compose.yml), [.env.example](.env.example), [.gitignore](.gitignore) |
| 4 | Cấu hình Nginx | [nginx/default.conf](nginx/default.conf) |
| 5–7 | Tạo EC2, cài Docker, triển khai và kiểm tra | [scripts/setup-server.sh](scripts/setup-server.sh), minh chứng trong `docs/evidence/` |
| 8–9 | Sơ đồ kiến trúc và tài liệu | `docs/architecture.*`, README này |

Điểm cần chứng minh khi demo tuần 1:

- Ba service `nginx`, `app`, `db` hoạt động; DB báo healthy.
- Mở ứng dụng qua địa chỉ server, thêm và xoá công việc.
- `/health` trả `{"status":"ok"}`; `/metrics` qua Nginx trả 403.
- Dữ liệu còn sau `docker compose down` rồi `docker compose up -d` **không dùng `-v`**.
- Có sơ đồ, README, lịch sử đóng góp của thành viên và video demo.

## 4. Tuần 2 — Docker và CI/CD

**Mục tiêu:** mỗi lần push/merge vào `main`, GitHub Actions chạy test, build và deploy lên EC2; test lỗi thì không deploy. Docker và volume từ tuần 1 tiếp tục được sử dụng.

### Bước 1 — Test tự động

[tests/test_app.py](tests/test_app.py) chạy với PostgreSQL thật. Bốn kiểm tra nền tảng của tuần 2 gồm:

| Test | Ý nghĩa |
| --- | --- |
| `test_health_ok` | `/health` phản ánh kết nối DB thành công |
| `test_add_then_read_back` | Thêm việc rồi đọc lại từ DB |
| `test_empty_title_is_not_saved` | Tên chỉ có khoảng trắng không tạo dữ liệu |
| `test_delete_removes_todo` | Xoá việc khỏi DB và danh sách |

Bộ test hiện có thêm các trường hợp cho API, migration, phân loại và đồng bộ bonus. [pytest.ini](pytest.ini) cấu hình import từ thư mục gốc; [requirements-dev.txt](requirements-dev.txt) chứa dependencies kiểm thử.

### Bước 2 — Deploy và mã phiên bản

[scripts/deploy.sh](scripts/deploy.sh) lấy mã commit hiện tại, gán `APP_VERSION`, build/chạy Compose, reload Nginx và kiểm tra `/health` tối đa 20 lần, cách nhau 3 giây. Thành công sẽ in `Deploy OK: phiên bản ...`; thất bại sẽ in log app và trả mã lỗi.

`APP_VERSION` được truyền qua Compose. Trong UI bonus, xem **Cài đặt → Thông tin ứng dụng → Phiên bản**. Nếu chạy Compose mà chưa gán biến này, ứng dụng hiển thị `dev`.

### Bước 3 — GitHub Secrets

Tạo tại **Settings → Secrets and variables → Actions** của repository:

| Secret | Giá trị/công dụng |
| --- | --- |
| `EC2_HOST` | `todo-devops.duckdns.org` — địa chỉ SSH của server |
| `EC2_SSH_KEY` | Toàn bộ private key của key pair đang được server chấp nhận |

Không đưa private key, mật khẩu DB hoặc token DuckDNS vào Git. Khi đổi key pair phải cập nhật `EC2_SSH_KEY`; khi IP đổi, DuckDNS cần được cập nhật đúng để `EC2_HOST` tiếp tục trỏ tới server.

### Bước 4 — Workflow CI/CD

Workflow: [.github/workflows/ci-cd.yml](.github/workflows/ci-cd.yml).

| Job | Công việc | Điều kiện |
| --- | --- | --- |
| `test` | Dựng PostgreSQL 17 tạm, cài dependencies, chạy `pytest -v` với Python 3.12 | Push vào `main` hoặc pull request hướng vào `main` |
| `build` | Build image từ `app/Dockerfile` | Job `test` thành công |
| `deploy` | SSH vào EC2, pull `main`, chạy `scripts/deploy.sh` | Job `build` thành công và sự kiện là push vào `main` |

```text
Pull request → test → build                  (không deploy)
Push main    → test → build → deploy → kiểm tra /health
                 └─ lỗi: build/deploy bị bỏ qua
```

Job build kiểm tra Dockerfile; server build lại image khi deploy, chưa dùng container registry. Test Node.js cho bonus hiện chạy riêng, chưa được thêm vào workflow. Nếu `/health` hỏng sau deploy, pipeline báo lỗi; script hiện **chưa tự rollback**. Trường hợp test hỏng trước deploy thì bản lỗi không được đưa lên server.

### Bước 5 — Chạy pipeline, kiểm tra dữ liệu và đo thời gian

Sau một thay đổi hợp lệ đã vào `main`, đối chiếu ba job xanh, dòng `Deploy OK`, mã phiên bản trên web và dữ liệu đã có trước lần deploy.

Bảng dưới ghi số liệu lấy từ mục **Total duration** trong GitHub Actions. Ba lần chạy trên `main` dưới đây đều có test, build và deploy thành công; mỗi lần có ảnh riêng, xác định theo mã commit:

| Lần | Mã commit | Total duration | Link lần chạy/ghi chú |
| --- | --- | --- | --- |
| 1 | `6f8fb86` | **1 phút 9 giây** | [Ảnh Actions: test → build → deploy thành công](docs/evidence/week-2/05-main-pipeline-success-69s.png) |
| 2 | `a1f876e` | **1 phút 9 giây** | [Ảnh Actions: lần chạy #15](docs/evidence/week-2/11-main-pipeline-a1f876e-69s.png) |
| 3 | `df43fa1` | **1 phút 9 giây** | [Ảnh Actions: lần chạy #17](docs/evidence/week-2/12-main-pipeline-df43fa1-69s.png) |

### Bước 6 — Demo pipeline chặn lỗi

Theo kịch bản môn học: ghi lại phiên bản đang chạy, tạo một commit demo làm sai kết quả `/health`, rồi theo dõi test đỏ, build/deploy bị skipped và server vẫn giữ phiên bản trước. Sau đó `git revert` **đúng commit demo lỗi**, push và kiểm tra pipeline xanh trở lại. Thực hiện có chủ đích trong buổi demo của nhóm; không để commit lỗi ở trạng thái cuối cùng.

Minh chứng CI/CD cần được ghi từ GitHub Actions và server thực tế, không dùng kết quả test cục bộ thay cho log deploy.

## 5. Phần bonus — Giao diện và quản lý công việc

**Phụ trách thiết kế/cải tiến UI: Ngô Tấn Đức.** Phần này phát triển thêm trên nền ứng dụng đồ án, được tách khỏi nhiệm vụ bắt buộc tuần 1–2.

- Workspace rộng, phủ chiều cao màn hình; responsive, menu thu gọn và giao diện sáng/tối được ghi nhớ.
- Thêm/sửa công việc tối đa 200 ký tự; đếm ký tự, chặn tên rỗng hoặc toàn khoảng trắng.
- Lên lịch ngày/giờ, ưu tiên Cao/Trung bình/Thấp, đánh dấu hoàn thành và xác nhận trước khi xoá.
- Xem Tất cả, Hôm nay, Sắp tới và Lịch; nhóm ngày không lặp công việc, lịch có chấm báo ngày có việc.
- Tìm kiếm tiếng Việt có/không dấu bằng phím `/`; sắp xếp theo ID, tên, ngày hẹn hoặc ưu tiên.
- Tiến độ hôm nay nằm trên danh sách, tính từ dữ liệu thực của ngày đó.
- Nút **+** cạnh PHÂN LOẠI tạo nhóm có tên tối đa 40 ký tự và màu riêng; kiểm tra tên trùng, lưu nhóm vào PostgreSQL. Ba nhóm Cá nhân, DevOps, Học tập được tạo ban đầu; mỗi việc gắn tối đa 10 nhóm.
- Menu **⋯** cạnh mỗi phân loại có thao tác **Xoá phân loại**, kèm xác nhận và số việc bị gỡ nhãn. Chỉ xoá nhãn, giữ nguyên công việc và các nhãn khác; nhóm đang xem bị xoá sẽ chuyển về Tất cả. Trên desktop, nút hiện khi rê chuột hoặc focus; trên màn hình cảm ứng nút luôn hiển thị.
- Cài đặt tập trung phần giao diện, kết nối, hàng đợi, đồng bộ thủ công và phiên bản.
- IndexedDB giữ thao tác ngoại tuyến; khi kết nối phục hồi, gửi hàng đợi và đọc lại dữ liệu từ server. Không báo đã đồng bộ chỉ dựa vào việc máy có Internet.
- Form thêm/hoàn thành/xoá vẫn gửi POST chuẩn khi JavaScript bị tắt; tìm kiếm tại chỗ, lịch tương tác, modal và offline cần JavaScript.

Ứng dụng hiện dùng danh sách chung, chưa có tài khoản riêng, phân quyền theo người dùng hay nhắc việc nền. Bản Flask trong repo gọi API thật và lưu PostgreSQL. Bản Sites dùng để xem thử trước đây là môi trường mô phỏng riêng, không phải địa chỉ triển khai EC2 của nhóm.

## 6. Cấu trúc repository

```text
.github/workflows/ci-cd.yml   # test → build → deploy
app/
  app.py                    # Form, API, health và endpoint Service Worker
  categories.py             # Kiểm tra và lưu phân loại
  migrate.py                # Migration giữ dữ liệu hiện có
  schema.sql                # Schema chuẩn
  Dockerfile
  entrypoint.sh             # Migration trước Gunicorn
  requirements.txt
  templates/index.html
  static/
    app.js                  # UI, IndexedDB và đồng bộ
    style.css
    service-worker.js
  .dockerignore
db/init.sql                 # Schema cho DB mới; khớp app/schema.sql
nginx/default.conf
scripts/
  setup-server.sh           # Bootstrap EC2 và cập nhật DuckDNS
  deploy.sh                 # Triển khai và kiểm tra health
tests/
  test_app.py               # Pytest với PostgreSQL
  offline.test.cjs           # Logic client với Node.js
docs/
  architecture.drawio
  architecture.png
  evidence/
  offline-first.md
  production-sync.md
.env.example
.gitattributes
.gitignore
docker-compose.yml
pytest.ini
requirements-dev.txt
README.md
```

## 7. Chạy trên máy cá nhân

Cần Git, Docker Engine và Docker Compose plugin. Trên Windows, dùng Docker Desktop với Linux containers.

```bash
git clone https://github.com/ericphan2545/devops-final.git
cd devops-final
```

Nếu đang xem README trên nhánh `UI-new` và phần bonus chưa merge vào `main`, chuyển sang đúng nhánh để thử các thay đổi đó:

```bash
git switch UI-new
```

Tạo `.env` nếu chưa có. PowerShell:

```powershell
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
```

Linux/macOS/Git Bash:

```bash
test -f .env || cp .env.example .env
```

Mở `.env`, đổi `POSTGRES_PASSWORD` trước lần tạo DB đầu tiên. Các biến mẫu gồm `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`; Compose truyền cấu hình tương ứng sang app dưới tên `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`.

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

Mở [http://localhost](http://localhost). `db` cần healthy, `app` và `nginx` cần hoạt động.

## 8. Triển khai EC2 và DuckDNS

### Dựng server bằng User data

Dùng [scripts/setup-server.sh](scripts/setup-server.sh) trên EC2 Ubuntu 24.04. Điền token DuckDNS khi cấu hình User data; giữ `DUCKDNS_TOKEN` trong file trên Git là rỗng.

Script cài Docker/Compose, chuẩn bị quyền cho user `ubuntu`, clone repo vào `/home/ubuntu/devops-todo`, tạo `.env` nếu chưa có và khởi động hệ thống. Khi có token, script tạo tác vụ cập nhật DuckDNS lúc khởi động và mỗi 5 phút.

DuckDNS ánh xạ tên miền tới IP public hiện tại, không biến IP thành IP tĩnh. Truy cập/SSH dùng `todo-devops.duckdns.org`; không cần đổi `EC2_HOST` mỗi khi IP đổi nếu bản ghi đã được cập nhật đúng.

Security Group cần cho phép HTTP 80 và SSH 22 từ nguồn quản trị/deploy phù hợp. Repo hiện phục vụ HTTP, chưa cấu hình chứng chỉ HTTPS.

Xem log bootstrap bằng `sudo tail -f /var/log/setup-server.log`. Script có shell tracing và log có thể chứa mật khẩu/token; file log và script cập nhật DuckDNS được đặt quyền chỉ root đọc. Không đưa log chứa giá trị bí mật vào minh chứng.

### Deploy thủ công

Sau khi code đã được commit/push và merge vào `main`, chạy trên server:

```bash
cd ~/devops-todo
git status
git switch main
git pull --ff-only origin main
bash scripts/deploy.sh
```

Nếu server có thay đổi cục bộ, xử lý chúng trước khi pull; không ghi đè hoặc reset mù. Với deploy tự động, workflow thực hiện pull/deploy trên server sau khi test và build thành công.

## 9. Kiểm thử và kiểm tra vận hành

### Kiểm tra hệ thống

Chạy trên máy đang phục vụ Compose:

```bash
docker compose ps
curl --fail http://localhost/health
curl -I http://localhost/metrics
docker compose logs --tail 50 app
docker compose logs --tail 50 nginx
```

Kết quả mong đợi: health trả `{"status":"ok"}`, metrics qua Nginx trả 403. Trong PowerShell dùng `curl.exe` nếu `curl` đang là alias.

### Chạy test cục bộ với DB riêng

Cần Python và PostgreSQL; lệnh dưới tạo DB kiểm thử bằng Docker, không trỏ test vào DB đang phục vụ người dùng:

```bash
docker run -d --name todo-test-db -p 127.0.0.1:55432:5432 -e POSTGRES_USER=todo -e POSTGRES_PASSWORD=testpass -e POSTGRES_DB=todo_test postgres:17
python -m pip install -r requirements-dev.txt
docker exec todo-test-db pg_isready -U todo -d todo_test
```

Chờ DB ready, rồi trong PowerShell:

```powershell
$env:DB_HOST = "localhost"
$env:PGPORT = "55432"
$env:DB_NAME = "todo_test"
$env:DB_USER = "todo"
$env:DB_PASSWORD = "testpass"
python -m pytest -v
```

Linux/macOS/Git Bash:

```bash
DB_HOST=localhost PGPORT=55432 DB_NAME=todo_test DB_USER=todo DB_PASSWORD=testpass python -m pytest -v
```

Test tạo schema ngẫu nhiên riêng rồi dọn khi xong. Bộ test của bản UI/phân loại đã được kiểm tra với **36 trường hợp pytest** trên PostgreSQL; đây là kết quả kiểm thử cục bộ, không phải xác nhận trạng thái một lần chạy GitHub Actions.

Kiểm thử logic bonus bằng Node.js, không cần cài thư viện frontend:

```bash
node tests/offline.test.cjs
```

Trên UI, kiểm tra thêm: tạo nhóm mới, gắn vào việc, lọc/tìm không dấu, sửa lịch, hoàn thành, huỷ xoá bằng Escape, đổi theme và gửi hàng đợi sau khi mạng phục hồi.

## 10. Dữ liệu, migration và đồng bộ

### Lưu bền và nâng cấp

`db-data` giữ dữ liệu khi thay hoặc tạo lại container trên cùng host. Volume không phải bản sao lưu khi host/ổ đĩa bị mất. `docker compose down -v` xoá volume; không dùng lệnh đó để đổi UI hoặc nâng schema.

`app/entrypoint.sh` chạy migration trước Gunicorn. Migration bổ sung metadata, UUID, nhật ký thao tác, tombstone và bảng phân loại; giữ công việc và ba ID phân loại cũ. Có thể chạy migration lại mà không seed trùng hoặc xoá nhóm tuỳ chỉnh. Migration dùng khoá giao dịch; công việc cũ được cấp UUID và `client_id` có default PostgreSQL để cách ghi cũ chỉ có title vẫn hoạt động.

`db/init.sql` chỉ được PostgreSQL tự chạy khi khởi tạo thư mục dữ liệu rỗng. Sửa file này không tự nâng cấp volume cũ; cần rebuild/chạy app để entrypoint thực hiện migration. Sau khi có bản cập nhật:

```bash
docker compose up -d --build
docker compose exec -T nginx nginx -s reload
```

Sao lưu DB trước thay đổi lớn. Đổi mật khẩu trong `.env` không tự đổi mật khẩu đã được lưu trong DB cũ.

### Ngoại tuyến và chống gửi trùng

Thao tác được ghi vào IndexedDB trước khi báo đã lưu. Mỗi công việc và thao tác có UUID ổn định; server lưu kết quả thao tác trong cùng giao dịch với thay đổi dữ liệu. Khi mất phản hồi, client gửi lại cùng `op_id` và server trả kết quả đã có.

Chỉ xoá thao tác khỏi hàng đợi sau xác nhận hợp lệ. Xoá thắng cập nhật cũ nhờ tombstone. Hai thiết bị sửa cùng trường dùng giá trị server nhận sau cùng; đây chưa phải hệ thống cộng tác có lịch sử phiên bản. Phân loại mới được gửi trước công việc tham chiếu tới nhóm đó. Xoá nhóm được ghi vào hàng đợi `category_delete`; server giữ bản ghi trong `todo_category_tombstones` và `/api/tasks` trả `deletedCategories`. Thao tác cũ từ thiết bị khác vẫn lưu được nội dung công việc nhưng không gắn lại nhãn đã xoá.

### Giới hạn cần biết

- Service Worker cần **HTTPS hoặc localhost**, và trang phải từng tải/cache thành công. Với HTTP qua IP hoặc DuckDNS, trang đang mở vẫn lưu thao tác ngoại tuyến, nhưng chưa bảo đảm tải lại toàn bộ trang khi mất mạng.
- Cache dành cho trang, CSS, JS; không cache API, `/health`, `/metrics` hoặc POST.
- Chưa có đồng bộ nền khi đóng hẳn trình duyệt; ứng dụng thử lại khi mở/trở lại tab, có mạng và theo chu kỳ khi đang hoạt động.
- Bộ nhớ trình duyệt gắn với origin. Chuyển từ IP sang DuckDNS hoặc từ HTTP sang HTTPS tạo vùng lưu trữ khác; đồng bộ hết thay đổi ở địa chỉ cũ trước khi chuyển.

Chi tiết: [docs/offline-first.md](docs/offline-first.md) và [docs/production-sync.md](docs/production-sync.md).

## 11. Endpoint và form

| Endpoint | Vai trò |
| --- | --- |
| `GET /` | Trang công việc dựng từ dữ liệu PostgreSQL |
| `POST /add` | Thêm công việc qua form |
| `POST /complete/<id>` | Hoàn thành/huỷ hoàn thành |
| `POST /delete/<id>` | Xoá công việc |
| `POST /categories/add` | Tạo phân loại qua form |
| `POST /categories/delete` | Xoá phân loại qua form; giữ công việc |
| `GET /health` | Kiểm tra kết nối DB |
| `GET /metrics` | Metrics của app; bị Nginx chặn từ bên ngoài |
| `GET /api/tasks` | Công việc và phân loại đã lưu |
| `GET /api/categories` | Danh sách phân loại |
| `POST /api/operations` | Thao tác `create`, `update`, `delete`, `category_create`, `category_delete` |
| `GET /service-worker.js` | Bộ nhớ trang ngoại tuyến, scope `/` |

API, health và endpoint Service Worker dùng `Cache-Control: no-store`. Một `op_id` dùng lại với payload khác nhận HTTP 409. Tên phân loại được chuẩn hoá khi kiểm tra trùng; server trả ID nhóm đã có nếu hai thiết bị tạo cùng tên. Client cập nhật ID nhóm trong các thao tác chưa gửi trước khi tiếp tục đồng bộ. Phiên bản này hỗ trợ tạo và xoá nhóm, chưa hỗ trợ sửa tên. Xoá nhóm gỡ nhãn khỏi mọi công việc trong cùng giao dịch và lưu bản ghi xoá; khi migration chạy lại, nhóm đã xoá không tự được tạo lại.

## 12. Minh chứng tuần 1 và tuần 2

### Tuần 1 — File đã lưu trong repo

| Nội dung | Minh chứng |
| --- | --- |
| EC2 và Security Group | [EC2 Running](docs/evidence/ec2-running.png), [Security Group](docs/evidence/security-group.png) |
| Docker và Compose | [Phiên bản Docker](docs/evidence/docker-version.png), [Container Up/healthy](docs/evidence/compose-up-ps.png) |
| Health và giới hạn metrics | [Health/metrics](docs/evidence/health-metrics.png), [Truy cập health](docs/evidence/health-public-ip.png) |
| Ứng dụng và dữ liệu | [Giao diện bản trước](docs/evidence/app-web.png), [Down/up giữ dữ liệu](docs/evidence/compose-down-up.png) |
| Sơ đồ và video | [Sơ đồ PNG](docs/architecture.png), [File draw.io](docs/architecture.drawio), [Video demo](docs/evidence/demo.mp4) |

Các ảnh/video trên thuộc bản triển khai trước. Chụp bổ sung khi cần chứng minh giao diện bonus hoặc trạng thái server sau bản cập nhật.

### Tuần 2 — Minh chứng thực hiện

Các ảnh dưới đây ghi lại quá trình kiểm thử, cấu hình Secrets và chạy CI/CD của nhóm tại thời điểm chụp. Ảnh được lưu tại [docs/evidence/week-2](docs/evidence/week-2/); không bao gồm giá trị private key hay GitHub Secrets.

| Nội dung | Kết quả thể hiện trong ảnh |
| --- | --- |
| Cấu hình Secrets | Đã khai báo `EC2_HOST` và `EC2_SSH_KEY` |
| Kiểm thử cục bộ | Bốn test nền tảng đạt, `4 passed in 1.32s`; đây là kết quả cục bộ của bản tại thời điểm chụp |
| Kiểm tra pull request | PR #12, #13 và #14 có test/build xanh; deploy được bỏ qua đúng điều kiện chỉ deploy khi push `main` |
| Pipeline trên `main` | Ba commit `6f8fb86`, `a1f876e`, `df43fa1`: test → build → deploy xanh; Total duration mỗi lần **1 phút 9 giây** |
| Triển khai EC2 | Log có `Deploy OK: phiên bản 6f8fb86` |
| Demo lỗi và hoàn tác | PR #16: commit lỗi `7eb15fd` làm test đỏ, build bị bỏ qua; commit revert `50734b6` đưa test/build về xanh |

<details>
<summary>1. GitHub Actions Secrets</summary>

![Hai GitHub Actions Secrets EC2_HOST và EC2_SSH_KEY](docs/evidence/week-2/01-github-actions-secrets.png)

</details>

<details>
<summary>2. Bốn bài kiểm thử với PostgreSQL trên máy cá nhân</summary>

![Bốn test pytest đạt với PostgreSQL, thời gian 1,32 giây](docs/evidence/week-2/02-pytest-four-passed.png)

Ảnh này minh chứng chạy test cục bộ; không thay thế log pytest trong job `test` của GitHub Actions.

</details>

<details>
<summary>3. Pull request hợp lệ: test và build thành công</summary>

PR #12 thay đổi nội dung sidebar:

![PR 12 có test và build thành công, deploy bỏ qua](docs/evidence/week-2/04-pr-sidebar-checks-passed.png)

PR #13 cập nhật README:

![PR 13 có test và build thành công, deploy bỏ qua](docs/evidence/week-2/07-pr-readme-checks-passed.png)

PR #14 cập nhật README lần thứ ba:

![PR 14 có test và build thành công, deploy bỏ qua](docs/evidence/week-2/13-pr14-checks-passed.png)

Job deploy trên pull request bị bỏ qua theo cấu hình workflow; chỉ push vào `main` mới triển khai.

</details>

<details>
<summary>4. Pipeline trên main và triển khai EC2 thành công</summary>

![Pipeline main commit 6f8fb86 có ba job xanh, tổng thời gian 1 phút 9 giây](docs/evidence/week-2/05-main-pipeline-success-69s.png)

![Pipeline main commit a1f876e có ba job xanh, tổng thời gian 1 phút 9 giây](docs/evidence/week-2/11-main-pipeline-a1f876e-69s.png)

![Pipeline main commit df43fa1 có ba job xanh, tổng thời gian 1 phút 9 giây](docs/evidence/week-2/12-main-pipeline-df43fa1-69s.png)

![Log triển khai EC2 báo Deploy OK phiên bản 6f8fb86](docs/evidence/week-2/06-ec2-deploy-log.png)

Log có cảnh báo biến `POSTGRES_DB` chưa được thiết lập trong ngữ cảnh lệnh; cần kiểm tra cấu hình nếu cảnh báo còn xuất hiện ở lần triển khai tiếp theo. Dòng `Deploy OK` là kết quả được ghi trong ảnh, chưa thay thế minh chứng đối chiếu phiên bản và dữ liệu trên web.

</details>

<details>
<summary>5. Test lỗi chặn build</summary>

![Demo test thất bại, build và deploy bị bỏ qua trên pull request](docs/evidence/week-2/03-test-failure-blocks-build-deploy.png)

</details>

<details>
<summary>6. Demo làm hỏng health check và revert trên PR 16</summary>

Commit `7eb15fd` làm test thất bại; build bị bỏ qua:

![PR 16 health check lỗi, test đỏ và build bị bỏ qua](docs/evidence/week-2/09-health-test-failure-pr16.png)

Sau commit `50734b6` — `Revert "Demo: break health check"`, test và build thành công trở lại:

![PR 16 sau revert có test và build xanh trở lại](docs/evidence/week-2/10-revert-health-test-passed-pr16.png)

Hai ảnh ghi lại chu kỳ lỗi → revert trên **pull request**. Deploy trên PR vốn bị bỏ qua theo điều kiện workflow; bộ ảnh này chưa chứng minh một lần push `main` lỗi và phiên bản EC2 được giữ nguyên.

</details>

**Minh chứng cần bổ sung để hoàn tất yêu cầu tuần 2:**

- Log pytest bên trong job `test` của GitHub Actions.
- Web hiển thị mã commit vừa triển khai và dữ liệu cũ còn sau deploy.
- Kịch bản test lỗi trên `main` giữ nguyên phiên bản server, kèm lần chạy xanh sau revert theo yêu cầu môn học.
- Video push → pipeline → web cập nhật.

Ảnh log triển khai và ảnh revert được gửi lặp lại chỉ hiển thị một lần, không tính thành các lần chạy khác nhau. Ảnh chụp phần README cũ là tài liệu tham chiếu, không dùng làm minh chứng CI/CD.

## 13. Xử lý sự cố

| Triệu chứng | Kiểm tra và cách xử lý |
| --- | --- |
| Không mở được web | Kiểm tra EC2 Running, rule HTTP 80, `docker compose ps` và đúng địa chỉ HTTP |
| Tên miền trỏ sai IP | Kiểm tra bản ghi DuckDNS và tác vụ `/usr/local/sbin/duckdns-update`; không công khai token |
| Docker báo permission denied | Kiểm tra user thuộc nhóm `docker`; đăng xuất/đăng nhập lại sau khi thêm nhóm |
| Nginx trả 502 | Xem log app/DB, kiểm tra migration; reload Nginx sau khi thay container app |
| DB báo sai mật khẩu | Đối chiếu `.env` với mật khẩu dùng lúc tạo volume; không xoá volume nếu cần giữ dữ liệu |
| Thiếu bảng/cột hoặc API phân loại lỗi | Kiểm tra đã có đủ code mới và entrypoint chạy migration; rebuild app |
| CI không kết nối được DB | Kiểm tra service PostgreSQL và các biến `DB_*` trong workflow |
| SSH invalid format/publickey | Kiểm tra toàn bộ private key trong `EC2_SSH_KEY` và key pair đúng với server |
| SSH timeout | Kiểm tra EC2, DNS, rule SSH 22 và kết nối từ runner |
| Pull không fast-forward | Xem `git status` trên server và đối chiếu thay đổi trước khi cập nhật; không tự ghi đè code |
| Script báo `$'\r'` | File `.sh` cần LF; repo có `.gitattributes` cho shell/Python/SQL |
| Pipeline đỏ ở health | Đọc log deploy/app/DB; container Up chưa bảo đảm ứng dụng kết nối DB được |
| UI báo chưa đồng bộ | Kiểm tra `/health`, `/api/tasks` và lỗi trong Cài đặt; giữ hàng đợi để gửi lại |

## 14. Nguồn và ghi chú

App mẫu ban đầu được xây dựng với hỗ trợ AI (Claude); phần giao diện, đồng bộ và tài liệu có hỗ trợ AI (Codex). Nhóm kiểm tra, hiểu mã nguồn và chịu trách nhiệm với bản nộp. Phân công cá nhân ở mục 1 ghi theo đóng góp nhóm xác nhận.

Các thư viện Python được ghim phiên bản trong [app/requirements.txt](app/requirements.txt) và [requirements-dev.txt](requirements-dev.txt). Thiết kế ngoại tuyến tham khảo [Service Worker](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API) và [IndexedDB](https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API).

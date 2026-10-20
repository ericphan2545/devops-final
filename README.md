# Todo App – DevOps Final Project

## Giới thiệu
App todo đơn giản (Flask + PostgreSQL) dùng để thực hành DevOps.
Chức năng: xem, thêm và xoá công việc.

Nguồn app: app mẫu viết với sự hỗ trợ của AI (Claude).
Phần việc của nhóm: Docker, CI/CD, giám sát, bảo mật, backup.

## Kiến trúc
![Sơ đồ kiến trúc](docs/architecture.png)

Luồng request:
Trình duyệt → Nginx (80) → Flask/Gunicorn (8000) → PostgreSQL 17 (5432).

Hệ thống được cấu hình chạy bằng Docker Compose trên EC2 t3.small,
Ubuntu 24.04, sử dụng Elastic IP.

- Chỉ Nginx publish cổng 80 ra ngoài.
- App và PostgreSQL giao tiếp qua mạng Docker Compose.
- App đợi PostgreSQL healthy rồi mới khởi động.
- Volume db-data lưu dữ liệu khi tạo lại container.
- Nginx chặn truy cập /metrics từ bên ngoài bằng HTTP 403.
- Endpoint /health kiểm tra kết nối từ app tới DB.

File sơ đồ chỉnh sửa: [architecture.drawio](docs/architecture.drawio).

## Cấu trúc thư mục
```text
devops-final/
├── .env.example
├── .gitignore
├── README.md
├── docker-compose.yml
├── app/
│   ├── .dockerignore
│   ├── Dockerfile
│   ├── app.py
│   ├── requirements.txt
│   └── templates/
│       └── index.html
├── db/
│   └── init.sql
├── nginx/
│   └── default.conf
└── docs/
    ├── architecture.drawio
    └── architecture.png
```

## Triển khai
1. Tạo EC2 Ubuntu 24.04, t3.small, gắn Elastic IP.
2. Cấu hình Security Group cho HTTP cổng 80 và SSH cổng 22.
3. Cài Docker Engine và Docker Compose plugin.
4. Clone repo:

   ```bash
   git clone https://github.com/ericphan2545/devops-final.git
   cd devops-final
   ```

   Nếu cấu hình vẫn nằm trên nhánh docker-setup, chuyển sang nhánh đó:

   ```bash
   git switch docker-setup
   ```

5. Tạo file biến môi trường:

   ```bash
   cp .env.example .env
   nano .env
   ```

   Đổi POSTGRES_PASSWORD trước lần chạy đầu.
   Không commit file .env chứa mật khẩu thật.

6. Kiểm tra cấu hình và chạy:

   ```bash
   docker compose config --quiet
   docker compose up -d --build
   docker compose ps
   ```

7. Mở `http://<ELASTIC_IP>` bằng trình duyệt, thay placeholder bằng IP thật.

## Kiểm tra
Thêm và xoá thử một công việc trên giao diện.

Trên server chạy:

```bash
curl http://localhost/health
curl -I http://localhost/metrics
```

Kết quả mong đợi:
- /health trả {"status":"ok"}.
- /metrics trả HTTP 403.
- docker compose ps có ba service đang chạy, db healthy.

Kiểm tra lưu dữ liệu: thêm một công việc rồi chạy:

```bash
docker compose down
docker compose up -d
```

Tải lại trang, công việc đã thêm phải còn.

**Lưu ý:** `docker compose down -v` sẽ xoá volume và dữ liệu DB.
File init.sql chỉ tự chạy khi volume PostgreSQL còn trống.
Đổi mật khẩu trong .env sau lần tạo DB đầu tiên không tự đổi mật khẩu trong DB.

## Xem log
```bash
docker compose logs app --tail 20
docker compose logs nginx --tail 20
docker compose logs db --tail 20
```

## Thành viên và phân công
| Thành viên | MSSV | Phần việc |
| --- | --- | --- |
| Điền tên | Điền MSSV | Điền phần việc |

## Minh chứng tuần 1
Đánh dấu sau khi kiểm tra và thu thập minh chứng thực tế:

- [ ] Sơ đồ kiến trúc .drawio và PNG.
- [ ] EC2 Running: Ubuntu 24.04, t3.small, Elastic IP.
- [ ] Security Group có cổng 22 và 80.
- [ ] Kết quả docker --version và docker compose version.
- [ ] Ba service đang chạy, db healthy.
- [ ] App thêm và xoá được công việc.
- [ ] /health trả ok, /metrics trả 403.
- [ ] Dữ liệu còn sau khi down rồi up.
- [ ] Mỗi thành viên có commit cho phần việc thực tế.
- [ ] Video demo ngắn.

## Phạm vi tuần 1
Đóng gói app, cấu hình Docker Compose, Nginx và tài liệu triển khai.
CI/CD, giám sát và backup được bổ sung ở các tuần tiếp theo.
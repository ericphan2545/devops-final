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
├── scripts/
│   └── setup-server.sh
└── docs/
    ├── architecture.drawio
    └── architecture.png
```

## Triển khai
Lab dùng AWS Academy Sandbox: **mỗi lần End Lab, toàn bộ tài nguyên bị xoá**
(EC2, Elastic IP, dữ liệu DB). Vì vậy server được dựng lại bằng script
`scripts/setup-server.sh`, và Elastic IP sẽ khác sau mỗi lần dựng lại.

### Cách 1: tự động bằng User data (dùng mỗi phiên lab)
1. Launch EC2: Ubuntu 24.04, t3.small, key pair vockey, ổ gp2 20 GB,
   Security Group mở cổng 22 (SSH) và 80 (HTTP).
2. Ở **Advanced details → User data**, dán toàn bộ nội dung `scripts/setup-server.sh`,
   rồi điền `DUCKDNS_TOKEN` ở đầu (token xem ở duckdns.org, không commit).
3. Cấp Elastic IP mới và gắn vào instance.
4. Chờ khoảng 5 phút rồi mở `http://todo-devops.duckdns.org`.
   Server tự báo IP mới cho DuckDNS (lúc khởi động và mỗi 5 phút), nên secret
   `EC2_HOST` (= `todo-devops.duckdns.org`) không phải sửa sau mỗi lần dựng lại.

Script tự cài Docker, clone repo vào `~/devops-todo`, tạo `.env` với mật khẩu
ngẫu nhiên và chạy `docker compose up -d --build`.

Trên server:

```bash
sudo tail -f /var/log/setup-server.log   # xem tiến độ, thấy "SETUP XONG" là xong
cat ~/devops-todo/.env                   # xem mật khẩu đã tạo
```

### Cách 2: làm tay
1. Tạo EC2 và Security Group như trên, gắn Elastic IP.
2. Cài Docker Engine và Docker Compose plugin.
3. Clone repo:

   ```bash
   git clone https://github.com/ericphan2545/devops-final.git devops-todo
   cd devops-todo
   ```

4. Tạo file biến môi trường:

   ```bash
   cp .env.example .env
   nano .env
   ```

   Đổi POSTGRES_PASSWORD trước lần chạy đầu.
   Không commit file .env chứa mật khẩu thật.

5. Kiểm tra cấu hình và chạy:

   ```bash
   docker compose config --quiet
   docker compose up -d --build
   docker compose ps
   ```

6. Mở `http://<ELASTIC_IP>` bằng trình duyệt, thay placeholder bằng IP thật.

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
| Thành viên | MSSV | Phần việc tuần 1 |
| --- | --- | --- |
| Phan Tiến Thịnh | 23090023 | Tạo repo và đưa app mẫu lên GitHub; tạo EC2, Security Group, Elastic IP; cài Docker; triển khai và kiểm tra trên server; viết script setup-server.sh |
| Ngô Tấn Đức | 23090008 | Viết Dockerfile; docker-compose.yml, .env.example, .gitignore; cấu hình Nginx; sơ đồ kiến trúc; README |
| Đặng Vĩnh Quang | 23090005 | Hiện tại chưa có |
| Huỳnh Hữu Như Mẫn | 23090020 | Hiện tại chưa có |

## Minh chứng tuần 1
Đánh dấu sau khi kiểm tra và thu thập minh chứng thực tế:

- [x] Sơ đồ kiến trúc .drawio và PNG ([drawio](docs/architecture.drawio), [png](docs/architecture.png)).
- [x] EC2 Running: Ubuntu 24.04, t3.small, Elastic IP ([ảnh](docs/evidence/ec2-running.png)).
- [x] Security Group có cổng 22 và 80 ([ảnh](docs/evidence/security-group.png)).
- [x] Kết quả docker --version và docker compose version ([ảnh](docs/evidence/docker-version.png)).
- [x] Ba service đang chạy, db healthy ([ảnh](docs/evidence/compose-up-ps.png)).
- [x] App thêm và xoá được công việc ([ảnh](docs/evidence/app-web.png), [video](docs/evidence/demo.mp4)).
- [x] /health trả ok, /metrics trả 403 ([ảnh](docs/evidence/health-metrics.png), [qua IP public](docs/evidence/health-public-ip.png)).
- [ ] Dữ liệu còn sau khi down rồi up ([ảnh down/up](docs/evidence/compose-down-up.png)).
- [ ] Mỗi thành viên có commit cho phần việc thực tế.
- [x] Video demo ngắn ([video](docs/evidence/demo.mp4)).

Lưu ý: ảnh minh chứng được chụp ở nhiều phiên lab khác nhau,
nên Elastic IP trong các ảnh có thể khác nhau (xem mục Triển khai).

## Phạm vi tuần 1
Đóng gói app, cấu hình Docker Compose, Nginx và tài liệu triển khai.
CI/CD, giám sát và backup được bổ sung ở các tuần tiếp theo.
"""
App todo mẫu cho đồ án DevOps.

Nguồn: app mẫu (starter) được viết với sự hỗ trợ của AI (Claude).
Phần việc của nhóm là phần DevOps: Docker, CI/CD, giám sát, bảo mật, backup.

Chức năng: thêm / xem / xoá việc cần làm, lưu trong PostgreSQL.
Endpoint phục vụ vận hành:
  /health  -> kiểm tra app còn sống và kết nối được DB (dùng cho giám sát)
  /metrics -> số liệu cho Prometheus (thư viện prometheus-flask-exporter tự tạo)
"""
import os

import psycopg
from flask import Flask, redirect, render_template, request
from prometheus_flask_exporter import PrometheusMetrics

app = Flask(__name__)
PrometheusMetrics(app)  # tự thêm endpoint /metrics

# Phiên bản đang chạy, hiện ở cuối trang. Tuần 2 sẽ gán bằng mã commit
# để nhìn là biết bản nào đang chạy trên server.
APP_VERSION = os.environ.get("APP_VERSION", "dev")


def get_db():
    # Thông tin DB lấy từ biến môi trường (file .env), không ghi cứng trong code
    return psycopg.connect(
        host=os.environ["DB_HOST"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        connect_timeout=3,
    )


@app.get("/")
def index():
    with get_db() as conn:
        todos = conn.execute("SELECT id, title FROM todos ORDER BY id").fetchall()
    return render_template("index.html", todos=todos, version=APP_VERSION)


@app.post("/add")
def add():
    title = request.form.get("title", "").strip()
    if title:
        with get_db() as conn:
            conn.execute("INSERT INTO todos (title) VALUES (%s)", (title,))
    return redirect("/")


@app.post("/delete/<int:todo_id>")
def delete(todo_id):
    with get_db() as conn:
        conn.execute("DELETE FROM todos WHERE id = %s", (todo_id,))
    return redirect("/")


@app.get("/health")
def health():
    try:
        with get_db() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok"}
    except Exception:
        return {"status": "error", "detail": "cannot connect to database"}, 500

-- Tạo bảng cho app todo.
-- Lưu ý: PostgreSQL chỉ chạy file này MỘT LẦN, khi volume dữ liệu còn trống
-- (lần đầu chạy docker compose up). Sửa file này sau đó sẽ không có tác dụng.
CREATE TABLE IF NOT EXISTS todos (
    id         SERIAL PRIMARY KEY,
    title      TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

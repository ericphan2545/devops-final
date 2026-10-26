"""
Test tự động cho app todo, chạy với PostgreSQL thật.
- Trong GitHub Actions: DB tạm do workflow dựng sẵn (service container).
- Trên máy mình: cần một PostgreSQL đang chạy và các biến DB_* trỏ vào nó.
"""
import uuid
from pathlib import Path

import pytest

from app.app import app, get_db

INIT_SQL = Path(__file__).resolve().parent.parent / "db" / "init.sql"


@pytest.fixture(scope="session", autouse=True)
def create_table():
    # Tạo bảng giống lúc DB khởi tạo lần đầu (bảng có rồi thì bỏ qua)
    with get_db() as conn:
        conn.execute(INIT_SQL.read_text())


@pytest.fixture
def client():
    return app.test_client()


def new_title():
    # Tên ngẫu nhiên để các lần chạy không đụng nhau
    return f"test-{uuid.uuid4().hex[:8]}"


def test_health_ok(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.get_json() == {"status": "ok"}


def test_add_then_read_back(client):
    title = new_title()
    res = client.post("/add", data={"title": title})
    assert res.status_code == 302
    page = client.get("/").get_data(as_text=True)
    assert title in page


def test_empty_title_is_not_saved(client):
    with get_db() as conn:
        before = conn.execute("SELECT count(*) FROM todos").fetchone()[0]
    client.post("/add", data={"title": "   "})
    with get_db() as conn:
        after = conn.execute("SELECT count(*) FROM todos").fetchone()[0]
    assert after == before


def test_delete_removes_todo(client):
    title = new_title()
    client.post("/add", data={"title": title})
    with get_db() as conn:
        todo_id = conn.execute("SELECT id FROM todos WHERE title = %s", (title,)).fetchone()[0]
    res = client.post(f"/delete/{todo_id}")
    assert res.status_code == 302
    page = client.get("/").get_data(as_text=True)
    assert title not in page
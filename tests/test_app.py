"""Integration tests against real PostgreSQL, isolated in a random test schema."""
import os
import uuid

import pytest
from psycopg import sql
from app.app import app, get_db
from app.migrate import apply_schema


@pytest.fixture(scope="session", autouse=True)
def schema():
    name = "test_todo_" + uuid.uuid4().hex
    original = os.environ.get("PGOPTIONS")
    with get_db() as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name)))
    os.environ["PGOPTIONS"] = f"-c search_path={name},public"
    with get_db() as conn:
        apply_schema(conn)
    yield
    with get_db() as conn:
        conn.execute("SET search_path TO public")
        conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(name)))
    if original is None:
        os.environ.pop("PGOPTIONS", None)
    else:
        os.environ["PGOPTIONS"] = original


@pytest.fixture(autouse=True)
def reset(schema):
    with get_db() as conn:
        conn.execute("TRUNCATE todos, todo_operations, todo_tombstones RESTART IDENTITY")


@pytest.fixture
def client():
    app.config["TESTING"] = True
    return app.test_client()


def operation(kind="create", client_id=None, payload=None):
    return {"op_id": str(uuid.uuid4()), "type": kind,
            "client_id": client_id or str(uuid.uuid4()),
            "payload": payload if payload is not None else {"title": "Công việc kiểm thử"}}


def test_health_ok(client):
    assert client.get("/health").get_json() == {"status": "ok"}


def test_add_then_read_back(client):
    response = client.post("/add", data={"title": "Việc qua form"})
    assert response.status_code == 302
    assert "Việc qua form" in client.get("/").get_data(as_text=True)


def test_empty_title_is_not_saved(client):
    client.post("/add", data={"title": "   "})
    assert client.get("/api/tasks").get_json()["tasks"] == []


def test_delete_removes_todo(client):
    client.post("/add", data={"title": "Sẽ xoá"})
    task = client.get("/api/tasks").get_json()["tasks"][0]
    assert client.post(f"/delete/{task['id']}").status_code == 302
    assert client.get("/api/tasks").get_json()["tasks"] == []


def test_metadata_roundtrip_and_form_completion(client):
    response = client.post("/add", data={"title": "Việc có lịch", "due_date": "2026-10-30",
                                         "due_time": "14:00", "priority": "1", "tags": ["devops", "hoc-tap"]})
    assert response.status_code == 302
    task = client.get("/api/tasks").get_json()["tasks"][0]
    assert task["due_date"] == "2026-10-30" and task["due_time"] == "14:00"
    assert task["priority"] == 1 and task["tags"] == ["devops", "hoc-tap"]
    client.post(f"/complete/{task['id']}", data={"completed": "true"})
    assert client.get("/api/tasks").get_json()["tasks"][0]["completed"] is True


def test_replayed_create_does_not_duplicate(client):
    op = operation()
    first = client.post("/api/operations", json=op)
    second = client.post("/api/operations", json=op)
    assert first.status_code == second.status_code == 200
    assert first.get_json() == second.get_json()
    assert len(client.get("/api/tasks").get_json()["tasks"]) == 1


def test_pending_create_update_delete_by_stable_uuid(client):
    create = operation()
    client.post("/api/operations", json=create)
    update = operation("update", create["client_id"], {"completed": True, "due_date": "2026-11-01", "priority": 2})
    response = client.post("/api/operations", json=update)
    assert response.get_json()["task"]["completed"] is True
    assert response.get_json()["task"]["priority"] == 2
    delete = operation("delete", create["client_id"], {})
    assert client.post("/api/operations", json=delete).get_json()["deleted"] is True
    assert client.post("/api/operations", json=delete).get_json()["deleted"] is True
    assert client.get("/api/tasks").get_json()["tasks"] == []


def test_same_operation_id_with_different_payload_is_rejected(client):
    op = operation()
    client.post("/api/operations", json=op)
    op["payload"]["title"] = "Dữ liệu khác"
    assert client.post("/api/operations", json=op).status_code == 409


def test_delete_tombstone_prevents_resurrection(client):
    op = operation()
    delete = operation("delete", op["client_id"], {})
    client.post("/api/operations", json=delete)
    result = client.post("/api/operations", json=op).get_json()
    assert result["deleted"] is True
    assert client.get("/api/tasks").get_json()["tasks"] == []


def test_native_delete_also_blocks_stale_offline_update(client):
    create = operation()
    task = client.post("/api/operations", json=create).get_json()["task"]
    client.post(f"/delete/{task['id']}")
    update = operation("update", create["client_id"], {"completed": True})
    assert client.post("/api/operations", json=update).get_json()["deleted"] is True


@pytest.mark.parametrize("payload", [{"title": " "}, {"title": "x" * 201}, {"title": "A", "due_date": "not-a-date"},
                                      {"title": "A", "due_time": "14:00"}, {"title": "A", "priority": True},
                                      {"title": "A", "tags": ["unknown"]}])
def test_invalid_api_payload_does_not_mutate(client, payload):
    assert client.post("/api/operations", json=operation(payload=payload)).status_code == 400
    assert client.get("/api/tasks").get_json()["tasks"] == []


def test_jinja_escapes_titles_and_exposes_native_forms(client):
    client.post("/add", data={"title": "<script>alert(1)</script>"})
    page = client.get("/").get_data(as_text=True)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert '<script>alert(1)</script>' not in page
    assert 'action="/add" method="post"' in page
    assert '/delete/' in page and '/complete/' in page


def test_service_worker_has_root_scope_and_version(client):
    response = client.get("/service-worker.js")
    assert response.status_code == 200
    assert response.headers["Service-Worker-Allowed"] == "/"
    assert "__APP_VERSION_LITERAL__" not in response.get_data(as_text=True)
    assert response.headers["Cache-Control"] == "no-store"


def test_additive_migration_preserves_legacy_rows():
    name = "test_legacy_" + uuid.uuid4().hex
    with get_db() as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name)))
        conn.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(name)))
        conn.execute("CREATE TABLE todos(id SERIAL PRIMARY KEY,title TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT now())")
        conn.execute("INSERT INTO todos(title) VALUES ('legacy task')")
        apply_schema(conn)
        apply_schema(conn)
        conn.execute("INSERT INTO todos(title) VALUES ('old writer after migration')")
        row = conn.execute("SELECT title,client_id,completed,priority FROM todos ORDER BY id").fetchone()
        assert row[0] == "legacy task" and row[1] is not None and row[2:] == (False, 0)
        conn.execute("SET LOCAL search_path TO public")
        conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(name)))


def test_concurrent_replay_creates_only_one_task(client):
    from concurrent.futures import ThreadPoolExecutor
    op = operation()
    def send(_):
        with app.test_client() as worker:
            return worker.post("/api/operations", json=op).get_json()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(send, range(4)))
    assert all(result == results[0] for result in results)
    assert len(client.get("/api/tasks").get_json()["tasks"]) == 1

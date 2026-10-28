"""Integration tests against real PostgreSQL, isolated in a random test schema."""
import os
import uuid
import json
import re

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
        conn.execute("TRUNCATE todos, todo_operations, todo_tombstones, todo_category_tombstones RESTART IDENTITY")
        conn.execute("DELETE FROM todo_categories WHERE id NOT IN ('ca-nhan','devops','hoc-tap')")
        apply_schema(conn)


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
    assert '/delete/' in page


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


def category_operation(name='Sức khỏe', color='#668dce'):
    return operation('category_create', payload={'name': name, 'color': color})


def test_custom_category_persists_and_can_be_assigned(client):
    op = category_operation()
    response = client.post('/api/operations', json=op)
    assert response.status_code == 200
    category = response.get_json()['category']
    assert category['id'] == op['client_id']
    assert client.post('/api/operations', json=op).get_json() == response.get_json()
    assert len(client.get('/api/categories').get_json()['categories']) == 4
    task = operation(payload={'title': 'Đi bộ', 'tags': [category['id']]})
    assert client.post('/api/operations', json=task).status_code == 200
    data = client.get('/api/tasks').get_json()
    assert data['tasks'][0]['tags'] == [category['id']]
    assert category in data['categories']
    page = client.get('/').get_data(as_text=True)
    bootstrap = json.loads(re.search(r'<script type="application/json" id="clean-bootstrap">(.*?)</script>', page, re.S).group(1))
    assert category in bootstrap['categories']


def test_duplicate_category_name_reuses_canonical_id(client):
    op = category_operation('  HOC   TAP ', '#123456')
    response = client.post('/api/operations', json=op)
    assert response.status_code == 200
    assert response.get_json()['category']['id'] == 'hoc-tap'
    assert len(client.get('/api/categories').get_json()['categories']) == 3


def test_category_form_and_escaped_names(client):
    response = client.post('/categories/add', data={'name': '<b>Công việc</b>', 'color': '#123456'})
    assert response.status_code == 302
    page = client.get('/').get_data(as_text=True)
    assert r'\u003cb\u003e' in page
    assert '<b>Công việc</b>' not in page


@pytest.mark.parametrize('payload', [{'name': ' '}, {'name': 'x' * 41}, {'name': 'A', 'color': 'url(evil)'}, {'name': 'A', 'extra': True}])
def test_invalid_category_does_not_mutate(client, payload):
    assert client.post('/api/operations', json=operation('category_create', payload=payload)).status_code == 400
    assert len(client.get('/api/categories').get_json()['categories']) == 3


def test_concurrent_duplicate_categories_create_one_row(client):
    from concurrent.futures import ThreadPoolExecutor
    def send(_):
        with app.test_client() as worker:
            return worker.post('/api/operations', json=category_operation()).get_json()['category']['id']
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(send, range(4)))
    assert len(set(ids)) == 1
    assert len(client.get('/api/categories').get_json()['categories']) == 4


def test_migration_preserves_custom_categories(client):
    category = client.post('/api/operations', json=category_operation()).get_json()['category']
    with get_db() as conn:
        apply_schema(conn)
    assert category in client.get('/api/categories').get_json()['categories']


def test_category_delete_keeps_tasks_and_other_tags_and_replays(client):
    cat = client.post('/api/operations', json=category_operation()).get_json()['category']
    task_op = operation(payload={'title': 'Giữ nguyên việc', 'tags': [cat['id'], 'devops'], 'priority': 1, 'completed': True})
    original = client.post('/api/operations', json=task_op).get_json()['task']
    deletion = operation('category_delete', cat['id'], {})
    first = client.post('/api/operations', json=deletion)
    assert first.status_code == 200
    assert first.get_json()['category_deleted'] is True
    assert client.post('/api/operations', json=deletion).get_json() == first.get_json()
    data = client.get('/api/tasks').get_json()
    assert cat['id'] not in [c['id'] for c in data['categories']]
    assert cat['id'] in data['deletedCategories']
    assert len(data['tasks']) == 1
    actual = data['tasks'][0]
    for field in ('id', 'title', 'priority', 'completed'):
        assert actual[field] == original[field]
    assert actual['tags'] == ['devops']
    assert client.post('/api/operations', json=operation('category_delete', cat['id'], {})).status_code == 200
    # Lost task response replay must keep its original fingerprint after tag deletion.
    assert client.post('/api/operations', json=task_op).status_code == 200
    assert client.get('/api/tasks').get_json()['tasks'][0]['tags'] == ['devops']


def test_deleted_default_category_stays_deleted_after_migration(client):
    assert client.post('/api/operations', json=operation('category_delete', 'devops', {})).status_code == 200
    with get_db() as conn:
        apply_schema(conn)
        apply_schema(conn)
    assert 'devops' not in [c['id'] for c in client.get('/api/categories').get_json()['categories']]
    # Same visible name may be created again, with a fresh stable ID.
    new = client.post('/api/operations', json=category_operation('DevOps')).get_json()['category']
    assert new['id'] != 'devops'


def test_stale_offline_task_tags_do_not_restore_deleted_category(client):
    client.post('/api/operations', json=operation('category_delete', 'devops', {}))
    stale = operation(payload={'title': 'Việc từ thiết bị cũ', 'tags': ['devops', 'hoc-tap']})
    assert client.post('/api/operations', json=stale).get_json()['task']['tags'] == ['hoc-tap']
    update = operation('update', stale['client_id'], {'tags': ['devops'], 'title': 'Vẫn sửa được'})
    response = client.post('/api/operations', json=update)
    assert response.status_code == 200
    assert response.get_json()['task']['tags'] == []
    unknown = operation(payload={'title': 'Sai nhóm', 'tags': ['unknown-group']})
    assert client.post('/api/operations', json=unknown).status_code == 400


def test_native_category_delete_preserves_task(client):
    client.post('/add', data={'title': 'Qua form', 'tags': ['devops']})
    response = client.post('/categories/delete', data={'category_id': 'devops'})
    assert response.status_code == 302
    assert client.get('/api/tasks').get_json()['tasks'][0]['tags'] == []
    assert client.post('/categories/delete', data={'category_id': 'devops'}).status_code == 302
    assert client.post('/categories/delete', data={'category_id': ''}).status_code == 400


def test_category_create_cannot_resurrect_deleted_id(client):
    create = category_operation()
    client.post('/api/operations', json=create)
    client.post('/api/operations', json=operation('category_delete', create['client_id'], {}))
    stale = {**create, 'op_id': str(uuid.uuid4())}
    assert client.post('/api/operations', json=stale).status_code == 409
    assert create['client_id'] not in [c['id'] for c in client.get('/api/categories').get_json()['categories']]


def test_can_delete_all_categories_without_default_reseed(client):
    for category_id in ('devops', 'ca-nhan', 'hoc-tap'):
        assert client.post('/api/operations', json=operation('category_delete', category_id, {})).status_code == 200
    with get_db() as conn:
        apply_schema(conn)
    assert client.get('/api/categories').get_json()['categories'] == []
    assert client.post('/api/operations', json=operation(payload={'title': 'Không phân loại'})).status_code == 200


def test_concurrent_category_delete_and_task_write_leave_no_dangling_tag(client):
    from concurrent.futures import ThreadPoolExecutor
    def send(op):
        with app.test_client() as worker:
            return worker.post('/api/operations', json=op).status_code
    ops = [operation(payload={'title': f'Việc {n}', 'tags': ['devops']}) for n in range(4)]
    ops.insert(2, operation('category_delete', 'devops', {}))
    with ThreadPoolExecutor(max_workers=5) as pool:
        assert list(pool.map(send, ops)) == [200] * len(ops)
    data = client.get('/api/tasks').get_json()
    assert len(data['tasks']) == 4
    assert all('devops' not in task['tags'] for task in data['tasks'])


def test_clean_template_keeps_native_forms_and_dict_task_ids(client):
    created = client.post('/api/operations', json=operation(payload={'title': '<script>việc dài</script>'})).get_json()['task']
    page = client.get('/').get_data(as_text=True)
    assert 'class="site-header"' in page
    assert 'class="ow-sidebar' not in page
    assert '&lt;script&gt;việc dài&lt;/script&gt;' in page
    assert f'action="/delete/{created["id"]}"' in page
    assert 'id="add-form" action="/add" method="post"' in page
    assert 'id="clean-bootstrap"' in page
    assert '<script>việc dài</script>' not in page


def test_clean_template_does_not_erase_existing_metadata(client):
    create = operation(payload={'title': 'Việc cũ', 'tags': ['devops'], 'priority': 1, 'completed': True, 'due_date': '2026-11-01'})
    before = client.post('/api/operations', json=create).get_json()['task']
    assert client.get('/').status_code == 200
    client.post('/add', data={'title': 'Việc mới đơn giản'})
    after = next(t for t in client.get('/api/tasks').get_json()['tasks'] if t['client_id'] == before['client_id'])
    assert after == before

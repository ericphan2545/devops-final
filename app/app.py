"""Todo workspace: native forms, metadata API and replay-safe offline mutations."""
import hashlib
import json
import os
import uuid
from pathlib import Path
from datetime import date, time

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from flask import Flask, Response, jsonify, redirect, render_template, request
from prometheus_flask_exporter import PrometheusMetrics
try:
    from .categories import all_categories, save_category, validate_category, CategoryConflict
except ImportError:  # Gunicorn imports app.py as a top-level module inside Docker.
    from categories import all_categories, save_category, validate_category, CategoryConflict

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 65536
PrometheusMetrics(app)
APP_VERSION = os.environ.get("APP_VERSION", "dev")
COLUMNS = "id, title, client_id, due_date, due_time, priority, tags, completed, updated_at"


def get_db():
    return psycopg.connect(host=os.environ["DB_HOST"], dbname=os.environ["DB_NAME"],
                          user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"],
                          connect_timeout=3)


def serialize(row):
    item = dict(row)
    item["client_id"] = str(item["client_id"])
    item["due_date"] = item["due_date"].isoformat() if item["due_date"] else None
    item["due_time"] = item["due_time"].strftime("%H:%M") if item["due_time"] else None
    item["updated_at"] = item["updated_at"].isoformat()
    return item


def all_tasks(conn):
    with conn.cursor(row_factory=dict_row) as cur:
        return [serialize(row) for row in cur.execute(f"SELECT {COLUMNS} FROM todos ORDER BY id").fetchall()]


def validate(data, partial=False):
    if not isinstance(data, dict):
        raise ValueError("Dữ liệu công việc không hợp lệ.")
    allowed = {"title", "due_date", "due_time", "priority", "tags", "completed"}
    if set(data) - allowed:
        raise ValueError("Có trường dữ liệu không được hỗ trợ.")
    cleaned = {}
    if "title" in data or not partial:
        value = data.get("title")
        if not isinstance(value, str) or not value.strip() or len(value) > 200:
            raise ValueError("Tên công việc phải có từ 1 đến 200 ký tự.")
        cleaned["title"] = value.strip()
    if "due_date" in data:
        value = data["due_date"]
        try:
            cleaned["due_date"] = date.fromisoformat(value) if value else None
        except (ValueError, TypeError):
            raise ValueError("Ngày thực hiện không hợp lệ.") from None
    if "due_time" in data:
        value = data["due_time"]
        try:
            if value and (not isinstance(value, str) or len(value) != 5):
                raise ValueError()
            cleaned["due_time"] = time.fromisoformat(value) if value else None
        except (ValueError, TypeError):
            raise ValueError("Giờ thực hiện không hợp lệ.") from None
    if "priority" in data:
        value = data["priority"]
        if isinstance(value, bool) or not isinstance(value, int) or value not in (0, 1, 2, 3):
            raise ValueError("Mức ưu tiên không hợp lệ.")
        cleaned["priority"] = value
    if "tags" in data:
        value = data["tags"]
        if not isinstance(value, list) or len(value) > 10 or any(not isinstance(tag, str) or len(tag) > 64 for tag in value):
            raise ValueError("Thẻ phân loại không hợp lệ.")
        with get_db() as category_conn:
            known = {category['id'] for category in all_categories(category_conn)}
        if any(tag not in known for tag in value):
            raise ValueError('Phân loại chưa có trên máy chủ. Hãy đồng bộ phân loại trước.')
        cleaned["tags"] = list(dict.fromkeys(value))
    if "completed" in data:
        if not isinstance(data["completed"], bool):
            raise ValueError("Trạng thái hoàn thành không hợp lệ.")
        cleaned["completed"] = data["completed"]
    if not partial:
        cleaned = {"due_date": None, "due_time": None, "priority": 0, "tags": [], "completed": False, **cleaned}
    if cleaned.get("due_time") and "due_date" in cleaned and not cleaned["due_date"]:
        raise ValueError("Hãy chọn ngày trước khi đặt giờ.")
    return cleaned


def form_values():
    return validate({"title": request.form.get("title", ""),
                     "due_date": request.form.get("due_date") or None,
                     "due_time": request.form.get("due_time") or None,
                     "priority": int(request.form.get("priority", "0")),
                     "tags": request.form.getlist("tags")})


@app.get("/")
def index():
    with get_db() as conn:
        todos = all_tasks(conn)
        categories = all_categories(conn)
    return render_template("index.html", todos=todos, version=APP_VERSION, categories=categories,
                           tag_names={c['id']: c['name'] for c in categories},
                           category_colors={c['id']: c['color'] for c in categories},
                           initial_state={"tasks": todos, "categories": categories, "version": APP_VERSION})


@app.post("/add")
def add():
    # Preserve the original no-JS behavior for blank titles.
    if not request.form.get("title", "").strip():
        return redirect("/")
    try:
        values = form_values()
    except (ValueError, TypeError) as exc:
        return str(exc), 400
    with get_db() as conn:
        conn.execute("""INSERT INTO todos (client_id,title,due_date,due_time,priority,tags)
                        VALUES (%s,%s,%s,%s,%s,%s)""",
                     (uuid.uuid4(), values["title"], values["due_date"], values["due_time"], values["priority"], values["tags"]))
    return redirect("/")


@app.post("/delete/<int:todo_id>")
def delete(todo_id):
    with get_db() as conn:
        row = conn.execute("DELETE FROM todos WHERE id=%s RETURNING client_id", (todo_id,)).fetchone()
        if row:
            conn.execute("INSERT INTO todo_tombstones(client_id) VALUES (%s) ON CONFLICT DO NOTHING", (row[0],))
    return redirect("/")


@app.post("/complete/<int:todo_id>")
def complete(todo_id):
    completed = request.form.get("completed") == "true"
    with get_db() as conn:
        conn.execute("UPDATE todos SET completed=%s,updated_at=now() WHERE id=%s", (completed, todo_id))
    return redirect("/")


@app.get("/api/tasks")
def tasks_api():
    with get_db() as conn:
        return {"tasks": all_tasks(conn), "categories": all_categories(conn)}


@app.get("/api/categories")
def categories_api():
    with get_db() as conn:
        return {"categories": all_categories(conn)}


@app.post("/categories/add")
def add_category():
    try:
        values = validate_category({'name': request.form.get('name'), 'color': request.form.get('color', '#668dce')})
    except ValueError as exc:
        return str(exc), 400
    with get_db() as conn:
        save_category(conn, str(uuid.uuid4()), values)
    return redirect('/')


@app.errorhandler(CategoryConflict)
def category_conflict(exc):
    if request.path.startswith('/api/'):
        return {'error': str(exc), 'code': 'category_conflict'}, 409
    return str(exc), 409


@app.post("/api/operations")
def operation_api():
    raw = request.get_json(silent=True)
    try:
        if not isinstance(raw, dict) or set(raw) - {"op_id", "type", "client_id", "payload"}:
            raise ValueError("Thao tác đồng bộ không hợp lệ.")
        op_id = uuid.UUID(raw.get("op_id", ""))
        client_id = uuid.UUID(raw.get("client_id", ""))
        kind = raw.get("type")
        if kind not in ("create", "update", "delete", "category_create"):
            raise ValueError("Loại thao tác không hợp lệ.")
        values = validate_category(raw.get("payload", {})) if kind == "category_create" else validate(raw.get("payload", {}), partial=kind != "create")
        if kind == "update" and not values:
            raise ValueError("Không có thay đổi để đồng bộ.")
    except (ValueError, TypeError, AttributeError) as exc:
        message = str(exc) if isinstance(exc, ValueError) and str(exc) else "Mã thao tác không hợp lệ."
        return {"error": message, "code": "invalid_operation"}, 400
    fingerprint = hashlib.sha256(json.dumps(raw, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
    with get_db() as conn:
        # Same op_id cannot be applied twice, including after a lost HTTP response.
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (str(op_id),))
        previous = conn.execute("SELECT request_hash,result FROM todo_operations WHERE op_id=%s", (op_id,)).fetchone()
        if previous:
            if previous[0] != fingerprint:
                return {"error": "Mã thao tác đã được dùng cho dữ liệu khác.", "code": "operation_conflict"}, 409
            return jsonify(previous[1])
        if kind == 'category_create':
            category = save_category(conn, str(client_id), values)
            result = {'op_id': str(op_id), 'client_id': str(client_id), 'category': category}
            conn.execute('INSERT INTO todo_operations(op_id,request_hash,result) VALUES (%s,%s,%s)',
                         (op_id, fingerprint, Jsonb(result)))
            return jsonify(result)
        # Serialize create/update/delete for each stable client UUID.
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (str(client_id),))
        tombstone = conn.execute("SELECT 1 FROM todo_tombstones WHERE client_id=%s", (client_id,)).fetchone()
        result = {"op_id": str(op_id), "client_id": str(client_id), "deleted": False}
        if kind == "delete":
            conn.execute("DELETE FROM todos WHERE client_id=%s", (client_id,))
            conn.execute("INSERT INTO todo_tombstones(client_id) VALUES (%s) ON CONFLICT DO NOTHING", (client_id,))
            result["deleted"] = True
        elif tombstone:
            result["deleted"] = True
            result["notice"] = "Công việc đã bị xoá trên máy chủ. Thao tác cũ không tạo lại công việc đó."
        else:
            with conn.cursor(row_factory=dict_row) as cur:
                if kind == "create":
                    cur.execute("""INSERT INTO todos(client_id,title,due_date,due_time,priority,tags,completed)
                        VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(client_id) DO NOTHING""",
                        (client_id, values["title"], values["due_date"], values["due_time"], values["priority"], values["tags"], values["completed"]))
                else:
                    # Whitelisted field names; only changed fields overwrite server values.
                    if values.get("due_time") and "due_date" not in values:
                        row = cur.execute("SELECT due_date FROM todos WHERE client_id=%s", (client_id,)).fetchone()
                        if row and not row["due_date"]:
                            return {"error": "Hãy chọn ngày trước khi đặt giờ.", "code": "invalid_operation"}, 400
                    if "due_date" in values and not values["due_date"]:
                        values["due_time"] = None
                    fields = list(values)
                    assignments = ",".join(f"{field}=%s" for field in fields)
                    cur.execute(f"UPDATE todos SET {assignments},updated_at=now() WHERE client_id=%s",
                                [values[field] for field in fields] + [client_id])
                row = cur.execute(f"SELECT {COLUMNS} FROM todos WHERE client_id=%s", (client_id,)).fetchone()
                if row is None:
                    result["deleted"] = True
                    result["notice"] = "Không tìm thấy công việc trên máy chủ. Có thể dữ liệu đã được tạo lại."
                else:
                    result["task"] = serialize(row)
        conn.execute("INSERT INTO todo_operations(op_id,request_hash,result) VALUES (%s,%s,%s)",
                     (op_id, fingerprint, Jsonb(result)))
    return jsonify(result)


@app.get("/health")
def health():
    try:
        with get_db() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok"}
    except psycopg.Error:
        return {"status": "error", "detail": "cannot connect to database"}, 500


@app.get("/service-worker.js")
def service_worker():
    source = Path(app.static_folder, "service-worker.js").read_text(encoding="utf-8-sig")
    response = Response(source.replace("__APP_VERSION_LITERAL__", json.dumps(APP_VERSION)), mimetype="application/javascript")
    response.headers["Service-Worker-Allowed"] = "/"
    return response


@app.after_request
def no_cache_api(response):
    if request.path.startswith("/api/") or request.path in ("/health", "/service-worker.js"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.errorhandler(psycopg.Error)
def database_error(exc):
    app.logger.error("Database request failed: %s", type(exc).__name__)
    if request.path.startswith("/api/"):
        return {"error": "Máy chủ chưa sẵn sàng. Thay đổi vẫn được giữ trên thiết bị.", "code": "database_unavailable"}, 503
    return "Cơ sở dữ liệu chưa sẵn sàng. Vui lòng thử lại.", 503

"""Persistent task categories; legacy IDs remain valid after migration."""
import re
import unicodedata
from psycopg.rows import dict_row


class CategoryConflict(ValueError):
    pass


def category_key(name):
    value = unicodedata.normalize('NFD', name.casefold()).replace('đ', 'd')
    return ''.join(c for c in value if unicodedata.category(c) != 'Mn')


def validate_category(payload):
    if not isinstance(payload, dict) or set(payload) - {'name', 'color'}:
        raise ValueError('Thông tin phân loại không hợp lệ.')
    name = payload.get('name')
    if not isinstance(name, str):
        raise ValueError('Nhập tên phân loại từ 1 đến 40 ký tự.')
    name = ' '.join(name.split())
    if not name or len(name) > 40:
        raise ValueError('Nhập tên phân loại từ 1 đến 40 ký tự.')
    color = payload.get('color', '#668dce')
    if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
        raise ValueError('Màu phân loại không hợp lệ.')
    return {'name': name, 'color': color.lower()}


def all_categories(conn):
    with conn.cursor(row_factory=dict_row) as cur:
        return [dict(row) for row in cur.execute(
            'SELECT id,name,color FROM todo_categories ORDER BY sort_order,created_at,id').fetchall()]


def save_category(conn, client_id, values):
    name_key = category_key(values['name'])
    with conn.cursor(row_factory=dict_row) as cur:
        previous = cur.execute('SELECT id,name,color,name_key FROM todo_categories WHERE id=%s', (client_id,)).fetchone()
        if previous:
            if previous['name_key'] != name_key:
                raise CategoryConflict('Mã phân loại đã được dùng cho tên khác.')
            return {k: previous[k] for k in ('id', 'name', 'color')}
        cur.execute('''INSERT INTO todo_categories(id,name,name_key,color)
                       VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
                    (client_id, values['name'], name_key, values['color']))
        category = cur.execute('SELECT id,name,color FROM todo_categories WHERE name_key=%s', (name_key,)).fetchone()
        if category is None:
            raise CategoryConflict('Mã phân loại đã được dùng. Vui lòng tạo lại.')
        return dict(category)

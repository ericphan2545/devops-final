-- Non-destructive schema, also applied by app/migrate.py on container startup.
CREATE TABLE IF NOT EXISTS todos (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    client_id UUID,
    due_date DATE,
    due_time TIME,
    priority SMALLINT NOT NULL DEFAULT 0,
    tags TEXT[] NOT NULL DEFAULT '{}',
    completed BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE todos ADD COLUMN IF NOT EXISTS client_id UUID;
ALTER TABLE todos ADD COLUMN IF NOT EXISTS due_date DATE;
ALTER TABLE todos ADD COLUMN IF NOT EXISTS due_time TIME;
ALTER TABLE todos ADD COLUMN IF NOT EXISTS priority SMALLINT NOT NULL DEFAULT 0;
ALTER TABLE todos ADD COLUMN IF NOT EXISTS tags TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE todos ADD COLUMN IF NOT EXISTS completed BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE todos ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE todos ALTER COLUMN client_id SET DEFAULT gen_random_uuid();
CREATE UNIQUE INDEX IF NOT EXISTS todos_client_id_unique ON todos(client_id);
CREATE TABLE IF NOT EXISTS todo_operations (
    op_id UUID PRIMARY KEY,
    request_hash TEXT NOT NULL,
    result JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS todo_tombstones (
    client_id UUID PRIMARY KEY,
    deleted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Additive category migration; keep the three original IDs used by existing tasks.
CREATE TABLE IF NOT EXISTS todo_categories (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 40),
    name_key TEXT NOT NULL UNIQUE,
    color TEXT NOT NULL CHECK (color ~ '^#[0-9a-fA-F]{6}$'),
    sort_order INTEGER NOT NULL DEFAULT 3,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS todo_category_tombstones (
    id TEXT PRIMARY KEY,
    deleted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO todo_categories(id,name,name_key,color,sort_order)
SELECT seed.* FROM (VALUES
    ('ca-nhan','Cá nhân','ca nhan','#f36e77',0),
    ('devops','DevOps','devops','#67c5d3',1),
    ('hoc-tap','Học tập','hoc tap','#ecc64c',2)
) AS seed(id,name,name_key,color,sort_order)
WHERE NOT EXISTS (SELECT 1 FROM todo_category_tombstones WHERE id=seed.id)
ON CONFLICT DO NOTHING;

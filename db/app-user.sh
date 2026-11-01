#!/bin/sh
# Tạo/cập nhật tài khoản PostgreSQL quyền hẹp cho ứng dụng (mặc định: todo_app).
# Chạy lặp lại an toàn (idempotent), không ghi mật khẩu ra log, dùng chung cho:
#   - khởi tạo DB mới (/docker-entrypoint-initdb.d/20-app-user.sh),
#   - bước quản trị khi deploy trên volume cũ (scripts/deploy.sh),
#   - kiểm thử tự động trong CI.
(
  set +x
  set -eu

  ADMIN_USER="${POSTGRES_USER:-${DB_USER:-}}"
  TARGET_DB="${POSTGRES_DB:-${DB_NAME:-}}"
  TARGET_SCHEMA="${APP_DB_SCHEMA:-public}"

  if [ -z "$ADMIN_USER" ] || [ -z "$TARGET_DB" ]; then
    echo "ERROR: POSTGRES_USER and POSTGRES_DB must be set." >&2
    exit 1
  fi
  if [ -z "${APP_DB_USER:-}" ] || [ -z "${APP_DB_PASSWORD:-}" ]; then
    echo "ERROR: APP_DB_USER and APP_DB_PASSWORD must be set." >&2
    exit 1
  fi

  export TARGET_DB TARGET_SCHEMA APP_DB_USER APP_DB_PASSWORD
  if [ -z "${PGHOST:-}" ] && [ -n "${DB_HOST:-}" ]; then
    export PGHOST="$DB_HOST"
  fi
  if [ -z "${PGPASSWORD:-}" ]; then
    if [ -n "${POSTGRES_PASSWORD:-}" ]; then
      export PGPASSWORD="$POSTGRES_PASSWORD"
    elif [ -n "${DB_PASSWORD:-}" ]; then
      export PGPASSWORD="$DB_PASSWORD"
    fi
  fi

  psql -X -q -v ON_ERROR_STOP=1 --username "$ADMIN_USER" --dbname "$TARGET_DB" <<'SQL'
\getenv app_db_user APP_DB_USER
\getenv app_db_password APP_DB_PASSWORD
\getenv target_db TARGET_DB
\getenv target_schema TARGET_SCHEMA

BEGIN;

SELECT 1
WHERE set_config('todo.app_user', :'app_db_user', true) IS NOT NULL
  AND set_config('todo.app_password', :'app_db_password', true) IS NOT NULL
  AND set_config('todo.target_db', :'target_db', true) IS NOT NULL
  AND set_config('todo.target_schema', :'target_schema', true) IS NOT NULL;

DO $$
DECLARE
    v_user text := current_setting('todo.app_user');
    v_pass text := current_setting('todo.app_password');
    v_db text := current_setting('todo.target_db');
    v_schema text := current_setting('todo.target_schema');
    r record;
BEGIN
    IF v_user IS NULL OR btrim(v_user) = '' THEN
        RAISE EXCEPTION 'APP_DB_USER must not be empty';
    END IF;
    IF v_pass IS NULL OR btrim(v_pass) = '' THEN
        RAISE EXCEPTION 'APP_DB_PASSWORD must not be empty';
    END IF;
    IF v_user = current_user OR v_user = session_user THEN
        RAISE EXCEPTION 'APP_DB_USER (%) must be distinct from admin user (%)', v_user, current_user;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = v_user) THEN
        EXECUTE format(
            'CREATE ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L',
            v_user, v_pass
        );
    ELSE
        EXECUTE format(
            'ALTER ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L',
            v_user, v_pass
        );
    END IF;

    -- Thu hồi mọi membership role quản trị nếu từng được cấp.
    FOR r IN
        SELECT role_r.rolname AS granted_role
        FROM pg_catalog.pg_auth_members m
        JOIN pg_catalog.pg_roles member_r ON member_r.oid = m.member
        JOIN pg_catalog.pg_roles role_r ON role_r.oid = m.roleid
        WHERE member_r.rolname = v_user
    LOOP
        EXECUTE format('REVOKE %I FROM %I', r.granted_role, v_user);
    END LOOP;

    -- Bảo đảm database, schema, bảng và sequence không thuộc sở hữu của tài khoản app.
    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_database d
        JOIN pg_catalog.pg_roles ro ON ro.oid = d.datdba
        WHERE d.datname = v_db AND ro.rolname = v_user
    ) THEN
        EXECUTE format('ALTER DATABASE %I OWNER TO %I', v_db, current_user);
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_namespace n
        JOIN pg_catalog.pg_roles ro ON ro.oid = n.nspowner
        WHERE n.nspname = v_schema AND ro.rolname = v_user
    ) THEN
        EXECUTE format('ALTER SCHEMA %I OWNER TO %I', v_schema, current_user);
    END IF;

    -- Chuyển owner bảng/view trước (tự kéo theo sequence gắn cột SERIAL), sau đó tới sequence độc lập.
    FOR r IN
        SELECT c.oid, c.relname, c.relkind
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_catalog.pg_roles ro ON ro.oid = c.relowner
        WHERE n.nspname = v_schema
          AND ro.rolname = v_user
          AND c.relkind IN ('r', 'p', 'v', 'm')
    LOOP
        EXECUTE format('ALTER TABLE %I.%I OWNER TO %I', v_schema, r.relname, current_user);
    END LOOP;

    FOR r IN
        SELECT c.relname
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_catalog.pg_roles ro ON ro.oid = c.relowner
        WHERE n.nspname = v_schema
          AND ro.rolname = v_user
          AND c.relkind = 'S'
          AND NOT EXISTS (
              SELECT 1 FROM pg_catalog.pg_depend d
              WHERE d.objid = c.oid AND d.deptype = 'a'
          )
    LOOP
        EXECUTE format('ALTER SEQUENCE %I.%I OWNER TO %I', v_schema, r.relname, current_user);
    END LOOP;

    -- Kiểm soát quyền kế thừa từ PUBLIC trên database và schema.
    EXECUTE format('REVOKE ALL ON DATABASE %I FROM PUBLIC', v_db);
    EXECUTE format('REVOKE ALL ON DATABASE %I FROM %I', v_db, v_user);
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I', v_db, v_user);

    EXECUTE format('REVOKE CREATE ON SCHEMA %I FROM PUBLIC', v_schema);
    EXECUTE format('REVOKE ALL ON SCHEMA %I FROM %I', v_schema, v_user);
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO %I', v_schema, v_user);

    -- Thu hồi toàn bộ quyền cũ trên các đối tượng trong schema trước khi cấp lại quyền hẹp.
    EXECUTE format('REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA %I FROM PUBLIC, %I', v_schema, v_user);
    EXECUTE format('REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA %I FROM PUBLIC, %I', v_schema, v_user);
    EXECUTE format('REVOKE ALL PRIVILEGES ON ALL ROUTINES IN SCHEMA %I FROM PUBLIC, %I', v_schema, v_user);
    EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I REVOKE ALL ON TABLES FROM PUBLIC, %I', v_schema, v_user);
    EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I REVOKE ALL ON SEQUENCES FROM PUBLIC, %I', v_schema, v_user);

    -- Cấp quyền DML tối thiểu theo đúng bảng/sequence mà ứng dụng sử dụng.
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE %I.todos TO %I', v_schema, v_user);
    EXECUTE format('GRANT USAGE ON SEQUENCE %I.todos_id_seq TO %I', v_schema, v_user);
    EXECUTE format('GRANT SELECT, INSERT ON TABLE %I.todo_operations TO %I', v_schema, v_user);
    EXECUTE format('GRANT SELECT, INSERT ON TABLE %I.todo_tombstones TO %I', v_schema, v_user);
    EXECUTE format('GRANT SELECT, INSERT, DELETE ON TABLE %I.todo_categories TO %I', v_schema, v_user);
    EXECUTE format('GRANT SELECT, INSERT ON TABLE %I.todo_category_tombstones TO %I', v_schema, v_user);
END
$$;

COMMIT;
SQL
  echo "Configured least-privilege role '$APP_DB_USER' on database '$TARGET_DB' (schema '$TARGET_SCHEMA')."
)


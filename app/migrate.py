"""Apply additive migrations under a transaction lock; preserve existing todos."""
import os
import uuid
from pathlib import Path

import psycopg


def apply_schema(conn):
    conn.execute("SELECT pg_advisory_xact_lock(76584391023)")
    conn.execute(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8-sig"))
    missing = conn.execute("SELECT id FROM todos WHERE client_id IS NULL").fetchall()
    for row in missing:
        conn.execute("UPDATE todos SET client_id = %s WHERE id = %s", (uuid.uuid4(), row[0]))
    conn.execute("ALTER TABLE todos ALTER COLUMN client_id SET NOT NULL")


if __name__ == "__main__":
    with psycopg.connect(host=os.environ["DB_HOST"], dbname=os.environ["DB_NAME"],
                         user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"],
                         connect_timeout=5) as conn:
        apply_schema(conn)
    print("Schema ready; existing data preserved.")

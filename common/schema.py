"""Schema apply helpers for app and tests."""
from __future__ import annotations

from pathlib import Path

import psycopg

INIT_SQL = Path(__file__).resolve().parents[1] / "db" / "init.sql"


def apply_schema(dsn: str, *, reset: bool = False) -> None:
    sql = INIT_SQL.read_text(encoding="utf-8")
    with psycopg.connect(dsn, autocommit=True) as conn:
        if reset:
            conn.execute("DROP SCHEMA public CASCADE")
            conn.execute("CREATE SCHEMA public")
        conn.execute(sql)

"""Test harness: isolated DB, fake SMTP. Unit tests never touch Postgres."""
from __future__ import annotations

import os
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import pytest

TEST_DB = "leadgensystem_test"
ADMIN_DSN = os.getenv(
    "TEST_ADMIN_DATABASE_URL",
    "postgresql://leadgensystem:change_me@127.0.0.1:5432/postgres",
)
TEST_DSN = os.getenv(
    "TEST_DATABASE_URL",
    f"postgresql://leadgensystem:change_me@127.0.0.1:5432/{TEST_DB}",
)

# Secrets for code under test (no DB connection yet)
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("BASE_URL", "http://test.local")
os.environ.setdefault("ADMIN_PASSWORD", "test-admin-pass")
os.environ.setdefault("DEFAULT_REGION", "PK")

FIXTURES = Path(__file__).parent / "fixtures"


def _needs_db(request: pytest.FixtureRequest) -> bool:
    marks = {m.name for m in request.node.iter_markers()}
    if marks & {"integration", "e2e", "db"}:
        return True
    # fixture name dependency
    fixturenames = set(request.fixturenames)
    return bool(fixturenames & {"db", "test_dsn", "workspace_id", "verified_sender", "offer_profile_id", "scoring_profile_id", "fake_smtp"})


def pytest_collection_modifyitems(config, items):
    """Unit tests that accidentally pull DB fixtures stay as written; no global DB."""
    pass


def _ensure_test_db() -> None:
    import psycopg

    with psycopg.connect(ADMIN_DSN, autocommit=True, connect_timeout=5) as conn:
        row = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)
        ).fetchone()
        if not row:
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')


@pytest.fixture(scope="session")
def test_dsn() -> Iterator[str]:
    from common.db import close_pool
    from common.schema import apply_schema

    _ensure_test_db()
    os.environ["DATABASE_URL"] = TEST_DSN
    apply_schema(TEST_DSN, reset=True)
    close_pool()
    yield TEST_DSN
    close_pool()


@pytest.fixture
def db(test_dsn: str) -> str:
    from common.auth import hash_password
    from common.db import close_pool, execute
    from common.schema import apply_schema

    os.environ["DATABASE_URL"] = test_dsn
    apply_schema(test_dsn, reset=True)
    close_pool()
    execute(
        "INSERT INTO users (workspace_id, email, password_hash, role) VALUES (1, %s, %s, 'admin') "
        "ON CONFLICT (email) DO NOTHING",
        ("admin@local", hash_password("test-admin-pass")),
    )
    return test_dsn


@pytest.fixture
def workspace_id(db: str) -> int:
    return 1


@pytest.fixture
def offer_profile_id(db: str) -> int:
    from common.db import fetchone

    row = fetchone("SELECT id FROM offer_profiles WHERE workspace_id=1 ORDER BY id LIMIT 1")
    assert row
    return int(row["id"])


@pytest.fixture
def scoring_profile_id(db: str) -> int:
    from common.db import fetchone

    row = fetchone("SELECT id FROM scoring_profiles WHERE workspace_id=1 ORDER BY id LIMIT 1")
    assert row
    return int(row["id"])


class _MailBox:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def clear(self) -> None:
        self.messages.clear()


class _Handler:
    def __init__(self, box: _MailBox) -> None:
        self.box = box
        self.reject = False

    async def handle_DATA(self, server, session, envelope):  # noqa: N802
        if self.reject:
            return "550 rejected by test"
        self.box.messages.append(
            {
                "from": envelope.mail_from,
                "to": list(envelope.rcpt_tos),
                "content": envelope.content.decode("utf-8", errors="replace"),
            }
        )
        return "250 OK"


@pytest.fixture
def fake_smtp() -> Iterator[tuple[_MailBox, int, _Handler]]:
    from aiosmtpd.controller import Controller

    box = _MailBox()
    handler = _Handler(box)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    controller = Controller(handler, hostname="127.0.0.1", port=port)
    controller.start()
    time.sleep(0.05)
    yield box, port, handler
    controller.stop()


@pytest.fixture
def verified_sender(db: str, fake_smtp: tuple[_MailBox, int, _Handler]) -> dict[str, Any]:
    from common.db import fetchone

    _box, port, _handler = fake_smtp
    row = fetchone(
        """
        INSERT INTO sender_profiles (
          workspace_id, sender_name, company, from_email, reply_to, domain,
          physical_address, smtp_host, smtp_port, daily_limit,
          send_window_start, send_window_end, timezone, smtp_verified_at
        ) VALUES (
          1, 'QA Sender', 'QA Co', 'qa@test.local', 'qa@test.local', 'test.local',
          '1 Test St, Lahore', '127.0.0.1', %s, 20, 0, 23, 'UTC', %s
        ) RETURNING *
        """,
        (port, datetime.now(timezone.utc)),
    )
    assert row
    return dict(row)


@pytest.fixture
def fixture_html() -> Path:
    return FIXTURES

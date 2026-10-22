"""Unsubscribe token helpers and FastAPI endpoint."""
from __future__ import annotations

from itsdangerous import BadSignature, URLSafeSerializer

from common.config import get_settings
from common.db import execute, fetchone


def _ser() -> URLSafeSerializer:
    return URLSafeSerializer(get_settings().secret_key, salt="unsub")


def make_token(workspace_id: int, email: str) -> str:
    return _ser().dumps({"w": workspace_id, "e": email})


def parse_token(token: str) -> tuple[int, str] | None:
    try:
        data = _ser().loads(token)
        return int(data["w"]), str(data["e"])
    except (BadSignature, KeyError, TypeError, ValueError):
        return None


def suppress(workspace_id: int, email: str, reason: str = "unsubscribe") -> None:
    execute(
        """
        INSERT INTO suppression (workspace_id, email, reason)
        VALUES (%s, %s, %s)
        ON CONFLICT (workspace_id, email) DO UPDATE SET reason = EXCLUDED.reason
        """,
        (workspace_id, email.lower().strip(), reason),
    )


def is_suppressed(workspace_id: int, email: str) -> bool:
    row = fetchone(
        "SELECT 1 AS ok FROM suppression WHERE workspace_id = %s AND email = %s",
        (workspace_id, email.lower().strip()),
    )
    return bool(row)


def create_app():
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse

    app = FastAPI(title="Leadgensystem unsubscribe")

    @app.get("/unsubscribe", response_class=HTMLResponse)
    def unsubscribe(token: str = ""):
        parsed = parse_token(token)
        if not parsed:
            raise HTTPException(400, "Invalid token")
        workspace_id, email = parsed
        suppress(workspace_id, email, "unsubscribe")
        return "<h1>Unsubscribed</h1><p>You will not receive further emails.</p>"

    return app

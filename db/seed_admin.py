"""Seed admin user from ADMIN_PASSWORD env. Idempotent."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, "/app")

from common.auth import hash_password  # noqa: E402
from common.db import execute, fetchone  # noqa: E402


def main() -> None:
    email = os.getenv("ADMIN_EMAIL", "admin@local")
    password = os.getenv("ADMIN_PASSWORD", "change_me")
    existing = fetchone("SELECT id FROM users WHERE email = %s", (email,))
    if existing:
        print(f"admin exists: {email}")
        return
    pw_hash = hash_password(password)
    execute(
        "INSERT INTO users (workspace_id, email, password_hash, role) VALUES (1, %s, %s, 'admin')",
        (email, pw_hash),
    )
    print(f"seeded admin: {email}")


if __name__ == "__main__":
    main()

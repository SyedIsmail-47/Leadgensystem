"""Environment-backed settings. Secrets/infra only; business config lives in DB."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str
    postgres_db: str
    postgres_user: str
    postgres_password: str
    admin_email: str
    admin_password: str
    secret_key: str
    base_url: str
    default_region: str


def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql://leadgensystem:change_me@localhost:5432/leadgensystem",
        ),
        postgres_db=os.getenv("POSTGRES_DB", "leadgensystem"),
        postgres_user=os.getenv("POSTGRES_USER", "leadgensystem"),
        postgres_password=os.getenv("POSTGRES_PASSWORD", "change_me"),
        admin_email=os.getenv("ADMIN_EMAIL", "admin@local"),
        admin_password=os.getenv("ADMIN_PASSWORD", "change_me"),
        secret_key=os.getenv("SECRET_KEY", "dev-secret-change-me"),
        base_url=os.getenv("BASE_URL", "http://localhost:8501").rstrip("/"),
        default_region=os.getenv("DEFAULT_REGION", "PK"),
    )

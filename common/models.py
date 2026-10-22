"""Shared dataclasses."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class LeadDraft:
    name: str
    category: str | None = None
    address: str | None = None
    city: str | None = None
    phone: str | None = None
    website: str | None = None
    email: str | None = None
    gmaps_url: str | None = None
    rating: float | None = None
    review_count: int | None = None
    source: str = "gmaps"
    facebook_url: str | None = None
    instagram_url: str | None = None
    linkedin_url: str | None = None
    whatsapp_link: str | None = None


@dataclass
class ScoreResult:
    score: int
    tier: str
    confidence: float
    breakdown: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RunContext:
    run_id: int
    workspace_id: int
    campaign_id: int | None = None
    started_at: datetime | None = None

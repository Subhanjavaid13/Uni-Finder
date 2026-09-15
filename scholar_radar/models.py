"""Core data structures shared across the agent."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field, fields
from typing import Any


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def make_id(url: str, title: str) -> str:
    """Stable id for an opportunity: same page + same title = same opportunity."""
    normalized_url = re.sub(r"^https?://(www\.)?", "", (url or "").strip().lower()).rstrip("/")
    raw = f"{normalized_url}|{slugify(title)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class Candidate:
    """A web page that *might* describe a scholarship; not yet analysed."""

    url: str
    title: str = ""
    snippet: str = ""
    source: str = ""  # "official" | "rss" | "search"
    source_name: str = ""
    country_hint: str | None = None
    seed_key: str | None = None
    priority: int = 0  # higher = analysed first when the per-run budget is limited
    text: str | None = None  # full page text, filled in by the fetcher


@dataclass
class Opportunity:
    """A scholarship / funded program, as extracted from a page or the seed database."""

    title: str
    url: str
    source: str = "unknown"  # "seed" | "official" | "rss" | "search"
    id: str = ""
    seed_key: str | None = None  # links official-page findings back to a seed entry
    provider: str | None = None
    country: str | None = None
    university: str | None = None
    degree_level: str | None = None  # "masters" | "phd" | "bachelors" | "any"
    fields: list[str] = field(default_factory=list)

    # Funding
    funding_level: str = "unknown"  # "full" | "partial" | "tuition_only" | "unknown"
    covers_tuition: bool | None = None
    stipend: bool | None = None
    stipend_amount: str | None = None
    housing: bool | None = None
    travel: bool | None = None
    insurance: bool | None = None

    # Application
    application_fee: str = "unknown"  # "none" | "required" | "varies" | "unknown"
    application_fee_amount: str | None = None
    opens: str | None = None
    deadline: str | None = None  # ISO date YYYY-MM-DD
    deadline_is_estimate: bool = False
    typical_window: str | None = None  # e.g. "Opens Oct, closes Jan" for recurring programs
    intake: str | None = None

    # Eligibility
    ielts_required: bool | None = None
    moi_accepted: bool | None = None
    english_notes: str | None = None
    min_gpa: str | None = None
    work_experience_years: float | None = None
    pakistan_eligible: bool | None = None
    eligibility_notes: str | None = None

    required_documents: list[str] = field(default_factory=list)
    summary: str = ""
    evidence: str | None = None  # short quote from the page backing deadline/fee claims
    verified: bool = False

    # Bookkeeping
    first_seen: str | None = None
    last_seen: str | None = None
    last_changed: str | None = None

    def __post_init__(self) -> None:
        if not self.id:
            self.id = make_id(self.url, self.title)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Opportunity":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class MatchResult:
    opportunity: Opportunity
    verdict: str  # "strong" | "possible" | "excluded"
    score: int
    english_track: str  # "no_ielts" | "ielts" | "unknown"
    reasons: list[str] = field(default_factory=list)
    to_verify: list[str] = field(default_factory=list)
    exclusions: list[str] = field(default_factory=list)

"""Persistent agent memory (data/state.json): what it has seen, found and reminded."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .models import Opportunity

# A change in any of these fields counts as an "update" worth telling you about.
TRACKED_FIELDS = (
    "deadline", "opens", "funding_level", "application_fee", "ielts_required",
    "moi_accepted", "stipend", "housing", "pakistan_eligible", "work_experience_years",
)

# Fields an official page is allowed to overwrite on a seed entry.
SEED_OVERRIDABLE = (
    "deadline", "opens", "application_fee", "application_fee_amount", "ielts_required",
    "moi_accepted", "english_notes", "stipend_amount", "required_documents", "evidence",
    "intake", "min_gpa",
)

MAX_RUN_HISTORY = 30


def content_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", (text or "").lower()).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


def _empty_state() -> dict[str, Any]:
    return {
        "version": 1,
        "opportunities": {},
        "pages": {},
        "seen_urls": {},
        "seed_overrides": {},
        "reminders_sent": {},
        "runs": [],
    }


class State:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = _empty_state()
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self.data.update(loaded)

    # ---- page change detection -------------------------------------------------
    def page_changed(self, url: str, text_hash: str, today: date) -> bool:
        record = self.data["pages"].get(url)
        self.data["pages"][url] = {"hash": text_hash, "last_checked": today.isoformat(),
                                   "last_changed": record.get("last_changed") if record else None}
        if record and record.get("hash") == text_hash:
            return False
        self.data["pages"][url]["last_changed"] = today.isoformat()
        return True

    # ---- seen URLs (RSS/search results) -----------------------------------------
    def is_seen(self, url: str, today: date, recheck_days: int = 120) -> bool:
        seen = self.data["seen_urls"].get(url)
        if not seen:
            return False
        return date.fromisoformat(seen) > today - timedelta(days=recheck_days)

    def mark_seen(self, url: str, today: date) -> None:
        self.data["seen_urls"][url] = today.isoformat()

    def prune_seen(self, today: date, keep_days: int = 365) -> None:
        cutoff = today - timedelta(days=keep_days)
        self.data["seen_urls"] = {
            u: d for u, d in self.data["seen_urls"].items() if date.fromisoformat(d) >= cutoff
        }

    # ---- opportunities -----------------------------------------------------------
    def get(self, opp_id: str) -> Opportunity | None:
        raw = self.data["opportunities"].get(opp_id)
        return Opportunity.from_dict(raw) if raw else None

    def all_opportunities(self) -> list[Opportunity]:
        return [Opportunity.from_dict(o) for o in self.data["opportunities"].values()]

    def upsert(self, opp: Opportunity, today: date) -> str:
        """Insert or merge an opportunity. Returns "new", "updated" or "unchanged"."""
        stamp = today.isoformat()
        existing = self.get(opp.id)
        if existing is None:
            opp.first_seen = opp.last_seen = opp.last_changed = stamp
            self.data["opportunities"][opp.id] = opp.to_dict()
            return "new"

        merged = existing.to_dict()
        for key, value in opp.to_dict().items():
            if key in ("first_seen", "last_seen", "last_changed", "id"):
                continue
            if opp.source == "seed":
                merged[key] = value  # seed file is the base truth; overrides applied before
            elif value not in (None, "", [], "unknown"):
                merged[key] = value
        changed = any(merged.get(f) != existing.to_dict().get(f) for f in TRACKED_FIELDS)
        merged["last_seen"] = stamp
        if changed:
            merged["last_changed"] = stamp
        self.data["opportunities"][opp.id] = merged
        return "updated" if changed else "unchanged"

    def apply_seed_overrides(self, opp: Opportunity) -> Opportunity:
        overrides = self.data["seed_overrides"].get(opp.seed_key or "", {})
        if not overrides:
            return opp
        data = opp.to_dict()
        data.update(overrides)
        return Opportunity.from_dict(data)

    def record_seed_findings(self, seed_key: str, found: Opportunity, today: date) -> bool:
        """Store facts read from an official page so they replace seed estimates.

        Returns True if anything new was learned.
        """
        overrides = dict(self.data["seed_overrides"].get(seed_key, {}))
        before = dict(overrides)
        for key in SEED_OVERRIDABLE:
            value = getattr(found, key)
            if value in (None, "", [], "unknown"):
                continue
            if key == "deadline":
                try:
                    if date.fromisoformat(value) < today:
                        continue  # the page still shows last year's deadline
                except ValueError:
                    continue
                overrides["deadline_is_estimate"] = False
            overrides[key] = value
        if overrides != before:
            overrides["verified"] = True
            self.data["seed_overrides"][seed_key] = overrides
            return True
        return False

    def remove_expired(self, today: date, grace_days: int = 60) -> None:
        """Drop non-seed opportunities whose deadline passed long ago."""
        cutoff = today - timedelta(days=grace_days)
        keep = {}
        for opp_id, raw in self.data["opportunities"].items():
            deadline = raw.get("deadline")
            if raw.get("source") != "seed" and deadline:
                try:
                    if date.fromisoformat(deadline) < cutoff:
                        continue
                except ValueError:
                    pass
            keep[opp_id] = raw
        self.data["opportunities"] = keep

    # ---- deadline reminders ------------------------------------------------------
    def reminder_due(self, opp_id: str, days_left: int, thresholds: list[int]) -> int | None:
        """Return the reminder threshold to send now (e.g. 14), or None."""
        if days_left < 0:
            return None
        sent = set(self.data["reminders_sent"].get(opp_id, []))
        crossed = [t for t in sorted(thresholds) if days_left <= t]
        if not crossed:
            return None
        threshold = crossed[0]
        return None if threshold in sent else threshold

    def mark_reminder(self, opp_id: str, threshold: int, thresholds: list[int]) -> None:
        # Mark this and all larger thresholds as done so we never send an older reminder later.
        sent = set(self.data["reminders_sent"].get(opp_id, []))
        sent.update(t for t in thresholds if t >= threshold)
        self.data["reminders_sent"][opp_id] = sorted(sent)

    # ---- runs & persistence ------------------------------------------------------
    def record_run(self, stats: dict[str, Any]) -> None:
        self.data["runs"] = (self.data["runs"] + [stats])[-MAX_RUN_HISTORY:]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1, ensure_ascii=False, sort_keys=True),
                       encoding="utf-8")
        tmp.replace(self.path)

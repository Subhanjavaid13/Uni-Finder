"""Watches official scholarship pages and reports the ones whose content changed."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from ..fetch import Fetcher
from ..models import Candidate
from ..store import State, content_hash
from .filters import is_blocked_url

log = logging.getLogger(__name__)

MAX_FOLLOW_PER_PAGE = 10


def discover_official(pages: list[dict[str, Any]], fetcher: Fetcher, state: State,
                      today: date) -> tuple[list[Candidate], list[str]]:
    """Returns (candidates, errors). Unchanged pages produce no candidates."""
    candidates: list[Candidate] = []
    errors: list[str] = []
    for cfg in pages:
        url, name = cfg["url"], cfg.get("name", cfg["url"])
        page = fetcher.fetch_page(url)
        if page is None:
            errors.append(f"{name}: could not fetch {url}")
            continue

        if state.page_changed(url, content_hash(page.text), today):
            log.info("Official page changed: %s", name)
            candidates.append(Candidate(
                url=url, title=page.title or name, source="official", source_name=name,
                country_hint=cfg.get("country"), seed_key=cfg.get("seed_key"),
                priority=10, text=page.text,
            ))

        follow_words = [w.lower() for w in cfg.get("follow_links", [])]
        if not follow_words:
            continue
        followed = 0
        for link_text, href in page.links:
            if followed >= MAX_FOLLOW_PER_PAGE:
                break
            if href == url or is_blocked_url(href) or state.is_seen(href, today):
                continue
            if any(word in link_text.lower() for word in follow_words):
                candidates.append(Candidate(
                    url=href, title=link_text, source="official", source_name=name,
                    country_hint=cfg.get("country"), priority=8,
                ))
                followed += 1
    return candidates, errors

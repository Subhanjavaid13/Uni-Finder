"""Reads scholarship news RSS feeds for newly announced opportunities."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

import feedparser
from bs4 import BeautifulSoup

from ..fetch import Fetcher
from ..models import Candidate
from ..store import State
from .filters import is_blocked_url, is_relevant, relevance_priority

log = logging.getLogger(__name__)


def _entry_date(entry: Any) -> date | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime(*parsed[:6]).date()


def parse_feed(content: bytes | str, feed_name: str, state: State, today: date,
               keywords: dict[str, list[str]] | None, max_age_days: int = 60) -> list[Candidate]:
    parsed = feedparser.parse(content)
    candidates = []
    for entry in parsed.entries:
        link = entry.get("link", "")
        if not link or is_blocked_url(link) or state.is_seen(link, today):
            continue
        published = _entry_date(entry)
        if published and published < today - timedelta(days=max_age_days):
            continue
        title = entry.get("title", "")
        summary = BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(" ", strip=True)
        blob = f"{title} {summary}"
        if not is_relevant(blob, keywords):
            state.mark_seen(link, today)  # irrelevant now, no need to re-check next week
            continue
        candidates.append(Candidate(
            url=link, title=title, snippet=summary[:500], source="rss", source_name=feed_name,
            priority=relevance_priority(blob),
        ))
    return candidates


def discover_rss(feeds: list[dict[str, Any]], fetcher: Fetcher, state: State, today: date,
                 keywords: dict[str, list[str]] | None) -> tuple[list[Candidate], list[str]]:
    candidates: list[Candidate] = []
    errors: list[str] = []
    for feed in feeds:
        resp = fetcher.get(feed["url"])
        if resp is None:
            errors.append(f"{feed.get('name', feed['url'])}: feed unavailable")
            continue
        found = parse_feed(resp.content, feed.get("name", ""), state, today, keywords)
        log.info("RSS %s: %d relevant new entries", feed.get("name"), len(found))
        candidates.extend(found)
    return candidates, errors

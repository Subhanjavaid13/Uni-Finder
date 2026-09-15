"""Web search discovery: finds universities and scholarships beyond the curated lists.

Uses Tavily when TAVILY_API_KEY is set, otherwise the free `ddgs` metasearch library.
"""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

import requests

from ..config import Profile, env
from ..models import Candidate
from ..store import State
from .filters import is_blocked_url, relevance_priority

log = logging.getLogger(__name__)


def _rotate(items: list[Any], count: int, offset: int) -> list[Any]:
    if not items or count <= 0:
        return []
    count = min(count, len(items))
    start = offset % len(items)
    return [items[(start + i) % len(items)] for i in range(count)]


def build_queries(cfg: dict[str, Any], profile: Profile, today: date) -> list[str]:
    """Builds this week's queries. Fields and countries rotate week by week."""
    week = today.isocalendar().week
    years = [y for y in profile.intake_years if y >= today.year] or [today.year + 1]
    year = years[0]
    fields = profile.fields or ["Computer Science"]
    countries = cfg.get("countries", [])

    queries: list[str] = []
    for i, template in enumerate(cfg.get("queries", [])):
        field = fields[(week + i) % len(fields)]
        queries.append(template.format(field=field, year=year, country=""))

    per_run = int(cfg.get("countries_per_run", 5))
    country_templates = cfg.get("country_queries", [])
    for j, country in enumerate(_rotate(countries, per_run, week * per_run)):
        for template in country_templates:
            field = fields[(week + j) % len(fields)]
            queries.append(template.format(field=field, year=year, country=country))

    limit = int(cfg.get("queries_per_run", len(queries)))
    return [" ".join(q.split()) for q in queries][:limit]


def _search_tavily(query: str, max_results: int, api_key: str) -> list[dict[str, str]]:
    resp = requests.post(
        "https://api.tavily.com/search",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"query": query, "max_results": max_results, "search_depth": "basic"},
        timeout=30,
    )
    resp.raise_for_status()
    return [
        {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
        for r in resp.json().get("results", [])
    ]


def _search_ddgs(query: str, max_results: int) -> list[dict[str, str]]:
    from ddgs import DDGS

    results = DDGS().text(query, max_results=max_results)
    return [
        {"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")}
        for r in results or []
    ]


def search_web(query: str, max_results: int = 8) -> list[dict[str, str]]:
    api_key = env("TAVILY_API_KEY")
    if api_key:
        return _search_tavily(query, max_results, api_key)
    return _search_ddgs(query, max_results)


def discover_search(cfg: dict[str, Any], profile: Profile, state: State,
                    today: date) -> tuple[list[Candidate], list[str]]:
    if not cfg.get("enabled", True):
        return [], []
    max_results = int(cfg.get("max_results_per_query", 8))
    candidates: dict[str, Candidate] = {}
    errors: list[str] = []
    for query in build_queries(cfg, profile, today):
        try:
            results = search_web(query, max_results)
        except Exception as exc:  # search backends fail in many ways; never crash the run
            errors.append(f"search failed for '{query}': {exc}")
            continue
        for r in results:
            url = r["url"]
            if not url or url in candidates or is_blocked_url(url) or state.is_seen(url, today):
                continue
            blob = f"{r['title']} {r['snippet']}"
            candidates[url] = Candidate(
                url=url, title=r["title"], snippet=r["snippet"][:500], source="search",
                source_name=query, priority=relevance_priority(blob),
            )
        time.sleep(1.0)  # be gentle with free search backends
    log.info("Search: %d new candidate pages", len(candidates))
    return list(candidates.values()), errors

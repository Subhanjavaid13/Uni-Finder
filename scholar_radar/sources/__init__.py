"""Discovery sources: official pages, RSS feeds and web search."""

from .filters import is_relevant, relevance_priority
from .official import discover_official
from .rss import discover_rss
from .search import build_queries, discover_search

__all__ = [
    "build_queries",
    "discover_official",
    "discover_rss",
    "discover_search",
    "is_relevant",
    "relevance_priority",
]

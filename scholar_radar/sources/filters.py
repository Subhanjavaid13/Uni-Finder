"""Cheap keyword checks run before spending AI calls on a page."""

from __future__ import annotations

DEFAULT_RELEVANCE = {
    "funding": ["scholarship", "fully funded", "fully-funded", "stipend", "fellowship"],
    "level": ["master", "msc", "postgraduate", "graduate"],
}

FIELD_HINTS = [
    "computer", "artificial intelligence", " ai ", "machine learning", "data science",
    "informatics", "software", "cyber", "computing", "all fields", "any field", "all subjects",
]

BLOCKED_DOMAINS = (
    "youtube.com", "facebook.com", "instagram.com", "tiktok.com", "linkedin.com", "x.com",
    "twitter.com", "pinterest.", "quora.com", "reddit.com", "telegram.", "whatsapp.com",
)


def is_relevant(text: str, keywords: dict[str, list[str]] | None = None) -> bool:
    """True if the text mentions at least one word from every keyword group."""
    blob = f" {(text or '').lower()} "
    groups = keywords or DEFAULT_RELEVANCE
    return all(any(word.lower() in blob for word in words) for words in groups.values())


def relevance_priority(text: str) -> int:
    blob = f" {(text or '').lower()} "
    score = 0
    if "fully funded" in blob or "fully-funded" in blob:
        score += 3
    if any(h in blob for h in FIELD_HINTS):
        score += 2
    if "stipend" in blob or "monthly allowance" in blob:
        score += 1
    if "no application fee" in blob or "application fee waiver" in blob:
        score += 1
    if "ielts" in blob and ("without" in blob or "not required" in blob or "no ielts" in blob):
        score += 1
    if "pakistan" in blob:
        score += 1
    return score


def is_blocked_url(url: str) -> bool:
    lowered = (url or "").lower()
    return any(domain in lowered for domain in BLOCKED_DOMAINS)

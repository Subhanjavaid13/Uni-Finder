"""Turns a web page into structured scholarship records (AI, with a keyword fallback)."""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from typing import Any

from dateutil import parser as dateparser

from .llm import BaseLLM, LLMError
from .models import Candidate, Opportunity

log = logging.getLogger(__name__)

MAX_PAGE_CHARS = 24000
MAX_OPPORTUNITIES_PER_PAGE = 6

FUNDING_LEVELS = {"full", "partial", "tuition_only", "unknown"}
FEE_VALUES = {"none", "required", "varies", "unknown"}
DEGREE_LEVELS = {"masters", "phd", "bachelors", "any"}

SYSTEM_PROMPT = """You are a careful research assistant that extracts facts about \
scholarships and funded university programmes from web pages.
Rules:
- Only use information written on the page. Never guess or use outside knowledge.
- Use null when the page does not clearly state something.
- Dates must be ISO format YYYY-MM-DD and only if the page states the full date.
- "full" funding means tuition AND living costs (stipend) are covered.
- application_fee: "none" only if the page says there is no fee / it is free;
  "required" if a fee is mentioned; otherwise "unknown".
- ielts_required: false only if the page says IELTS/English test is not required or that
  an English-medium degree / Medium of Instruction letter is accepted.
- Return JSON only."""

SCHEMA_HINT = {
    "is_scholarship_page": "boolean - does the page describe one or more specific scholarships or funded programmes?",
    "opportunities": [{
        "title": "string",
        "provider": "string|null",
        "country": "string|null - where you study",
        "university": "string|null",
        "degree_level": "masters|phd|bachelors|any|null",
        "fields": ["string - subjects covered, or 'all fields'"],
        "funding_level": "full|partial|tuition_only|unknown",
        "covers_tuition": "boolean|null",
        "stipend": "boolean|null",
        "stipend_amount": "string|null",
        "housing": "boolean|null",
        "travel": "boolean|null",
        "insurance": "boolean|null",
        "application_fee": "none|required|varies|unknown",
        "application_fee_amount": "string|null",
        "opens": "YYYY-MM-DD|null",
        "deadline": "YYYY-MM-DD|null",
        "intake": "string|null",
        "ielts_required": "boolean|null",
        "moi_accepted": "boolean|null",
        "english_notes": "string|null",
        "min_gpa": "string|null",
        "work_experience_years": "number|null",
        "pakistan_eligible": "boolean|null - true if open to all nationalities or Pakistan is listed",
        "eligibility_notes": "string|null",
        "required_documents": ["string"],
        "apply_url": "string|null",
        "summary": "string - 1-2 sentences",
        "evidence": "string|null - short exact quote about the deadline or funding",
    }],
}


def build_prompt(candidate: Candidate, text: str, today: date) -> str:
    return (
        f"Today is {today.isoformat()}.\n"
        f"Page URL: {candidate.url}\n"
        f"Page title: {candidate.title}\n"
        f"Found via: {candidate.source} ({candidate.source_name})\n"
        f"Country hint: {candidate.country_hint or 'unknown'}\n\n"
        f"Return JSON matching this shape:\n{json.dumps(SCHEMA_HINT, indent=1)}\n\n"
        f"If the page is a list of many programmes, include at most {MAX_OPPORTUNITIES_PER_PAGE} "
        f"that are master's level and related to computing/AI/data or open to all fields.\n\n"
        f"--- PAGE TEXT ---\n{text[:MAX_PAGE_CHARS]}"
    )


# ---- normalisation helpers ------------------------------------------------------

def to_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "yes", "y"):
            return True
        if v in ("false", "no", "n"):
            return False
    return None


def to_float(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        match = re.search(r"\d+(\.\d+)?", value)
        return float(match.group(0)) if match else None
    return None


DAY_OF_MONTH_RE = re.compile(
    r"\d{4}-\d{1,2}-\d{1,2}"                      # 2027-01-15
    r"|\d{1,2}[./-]\d{1,2}[./-]\d{2,4}"           # 15/01/2027
    r"|\b\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,}"  # 15 January
    r"|[A-Za-z]{3,}\s+\d{1,2}\b",                 # January 15
    re.IGNORECASE,
)


def parse_date(value: Any) -> str | None:
    """Parse a date only if it contains an explicit 4-digit year."""
    return parse_date_precise(value)[0]


def parse_date_precise(value: Any) -> tuple[str | None, bool]:
    """Returns (ISO date, is_estimate). "January 2027" -> ("2027-01-01", True)."""
    if not value or not isinstance(value, str) or not re.search(r"\b(19|20)\d{2}\b", value):
        return None, False
    try:
        parsed = dateparser.parse(value, dayfirst=False, default=datetime(2000, 1, 1)).date()
    except (ValueError, OverflowError):
        return None, False
    # Without a day of month, dateutil invents the 1st - don't present that as exact.
    return parsed.isoformat(), not bool(DAY_OF_MONTH_RE.search(value))


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _str_list(value: Any, limit: int = 15) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()][:limit]


def normalize_item(item: dict[str, Any], candidate: Candidate) -> Opportunity:
    funding = str(item.get("funding_level") or "unknown").lower()
    fee = str(item.get("application_fee") or "unknown").lower()
    level = str(item.get("degree_level") or "").lower() or None
    apply_url = _clean_str(item.get("apply_url"))
    url = candidate.url
    if apply_url and apply_url.startswith("http") and candidate.source != "official":
        url = apply_url
    deadline, deadline_is_estimate = parse_date_precise(item.get("deadline"))

    return Opportunity(
        title=_clean_str(item.get("title")) or candidate.title or candidate.url,
        url=url,
        source=candidate.source,
        seed_key=candidate.seed_key,
        provider=_clean_str(item.get("provider")),
        country=_clean_str(item.get("country")) or candidate.country_hint,
        university=_clean_str(item.get("university")),
        degree_level=level if level in DEGREE_LEVELS else None,
        fields=_str_list(item.get("fields")),
        funding_level=funding if funding in FUNDING_LEVELS else "unknown",
        covers_tuition=to_bool(item.get("covers_tuition")),
        stipend=to_bool(item.get("stipend")),
        stipend_amount=_clean_str(item.get("stipend_amount")),
        housing=to_bool(item.get("housing")),
        travel=to_bool(item.get("travel")),
        insurance=to_bool(item.get("insurance")),
        application_fee=fee if fee in FEE_VALUES else "unknown",
        application_fee_amount=_clean_str(item.get("application_fee_amount")),
        opens=parse_date(item.get("opens")),
        deadline=deadline,
        deadline_is_estimate=deadline_is_estimate,
        intake=_clean_str(item.get("intake")),
        ielts_required=to_bool(item.get("ielts_required")),
        moi_accepted=to_bool(item.get("moi_accepted")),
        english_notes=_clean_str(item.get("english_notes")),
        min_gpa=_clean_str(item.get("min_gpa")),
        work_experience_years=to_float(item.get("work_experience_years")),
        pakistan_eligible=to_bool(item.get("pakistan_eligible")),
        eligibility_notes=_clean_str(item.get("eligibility_notes")),
        required_documents=_str_list(item.get("required_documents")),
        summary=_clean_str(item.get("summary")) or "",
        evidence=_clean_str(item.get("evidence")),
    )


# ---- keyword fallback ------------------------------------------------------------

DEADLINE_RE = re.compile(
    r"deadline[^.\n]{0,40}?((?:\d{1,2}(?:st|nd|rd|th)?\s+)?[A-Z][a-z]{2,8}\.?\s+(?:\d{1,2}(?:st|nd|rd|th)?,?\s+)?(?:19|20)\d{2})",
    re.IGNORECASE,
)
HOUSING_RE = re.compile(
    r"(free|provided|covered|included)\s+(accommodation|housing|dormitory)"
    r"|(accommodation|housing|dormitory)\s+(is\s+|are\s+)?(provided|covered|included|free)"
)
TUITION_RE = re.compile(
    r"tuition(\s+fees?)?\s+(waiver|waived|covered|exemption)|full\s+tuition|free\s+tuition"
)
FIELD_WORDS = {
    "Artificial Intelligence": ["artificial intelligence"],
    "Computer Science": ["computer science", "computing"],
    "Machine Learning": ["machine learning"],
    "Data Science": ["data science"],
    "all fields": ["all fields", "any field", "all subjects", "all disciplines"],
}


def heuristic_extract(candidate: Candidate) -> list[Opportunity]:
    """Rough keyword-based extraction used when no AI key is configured."""
    text = f"{candidate.title}\n{candidate.snippet}\n{candidate.text or ''}"
    low = text.lower()
    if "scholarship" not in low and "fellowship" not in low and "stipend" not in low:
        return []

    fully_funded = "fully funded" in low or "fully-funded" in low
    deadline = None
    match = DEADLINE_RE.search(text)
    if match:
        deadline = parse_date(re.sub(r"(st|nd|rd|th)\b", "", match.group(1)))

    fee = "unknown"
    if re.search(r"no application fee|application fee (is )?waived|free of charge to apply|no fee", low):
        fee = "none"

    ielts_required = None
    moi = None
    if re.search(r"(no|without) ielts|ielts (is )?not required|medium of instruction|english.medium", low):
        ielts_required, moi = False, True

    return [Opportunity(
        title=candidate.title or candidate.url,
        url=candidate.url,
        source=candidate.source,
        seed_key=candidate.seed_key,
        country=candidate.country_hint,
        degree_level="masters" if re.search(r"\bmaster|\bmsc\b|\bm\.sc", low) else None,
        fields=[name for name, words in FIELD_WORDS.items() if any(w in low for w in words)],
        funding_level="full" if fully_funded else "unknown",
        covers_tuition=True if fully_funded or TUITION_RE.search(low) else None,
        stipend=True if ("stipend" in low or "monthly allowance" in low) else None,
        housing=True if HOUSING_RE.search(low) else None,
        application_fee=fee,
        deadline=deadline,
        ielts_required=ielts_required,
        moi_accepted=moi,
        pakistan_eligible=True if ("pakistan" in low or "all nationalities" in low) else None,
        summary=(candidate.snippet or "")[:300],
    )]


def extract_opportunities(candidate: Candidate, llm: BaseLLM | None, today: date) -> list[Opportunity]:
    text = candidate.text or candidate.snippet
    if llm is None:
        return heuristic_extract(candidate)
    try:
        data = llm.complete_json(SYSTEM_PROMPT, build_prompt(candidate, text, today))
    except (LLMError, ValueError) as exc:
        llm.note_failure()
        log.warning("AI extraction failed for %s (%s) - using keyword fallback", candidate.url, exc)
        return heuristic_extract(candidate)
    llm.note_success()

    if not to_bool(data.get("is_scholarship_page")):
        return []
    items = data.get("opportunities") or []
    if not isinstance(items, list):
        return []
    return [normalize_item(i, candidate) for i in items[:MAX_OPPORTUNITIES_PER_PAGE]
            if isinstance(i, dict)]

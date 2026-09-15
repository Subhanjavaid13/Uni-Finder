"""Scores every opportunity against your profile and explains why."""

from __future__ import annotations

import re
from datetime import date

from .config import Profile
from .models import MatchResult, Opportunity

EUROPE = {
    "european union", "europe", "germany", "netherlands", "belgium", "france", "italy", "spain",
    "portugal", "austria", "switzerland", "sweden", "finland", "norway", "denmark", "ireland",
    "poland", "czech", "hungary", "estonia", "latvia", "lithuania", "slovakia", "slovenia",
    "croatia", "romania", "bulgaria", "greece", "luxembourg", "malta", "cyprus", "iceland",
    "united kingdom", "uk", "england", "scotland",
}
REGIONS = {"europe": EUROPE}

ALL_FIELDS = ("all fields", "any field", "all subjects", "all disciplines", "all")
FIELD_SYNONYMS = {
    "computer science": ["computer", "computing", "informatics", "information technology", "ict", "software"],
    "artificial intelligence": ["artificial intelligence", "ai", "machine learning", "robotics",
                                "computer vision", "natural language", "intelligent systems"],
    "machine learning": ["machine learning", "deep learning", "ai"],
    "data science": ["data science", "data", "analytics", "big data"],
    "software engineering": ["software"],
    "informatics": ["informatics", "information"],
}

VERDICT_ORDER = {"strong": 0, "possible": 1, "excluded": 2}


def days_until(iso_date: str | None, today: date) -> int | None:
    if not iso_date:
        return None
    try:
        return (date.fromisoformat(iso_date) - today).days
    except ValueError:
        return None


def english_track(opp: Opportunity) -> str:
    if opp.ielts_required is False or opp.moi_accepted is True:
        return "no_ielts"
    if opp.ielts_required is True:
        return "ielts"
    return "unknown"


def _field_keywords(profile: Profile) -> set[str]:
    words: set[str] = set()
    for f in profile.fields:
        low = f.lower()
        words.add(low)
        words.update(FIELD_SYNONYMS.get(low, []))
    return words


def fields_match(opp: Opportunity, profile: Profile) -> bool | None:
    """True/False if the opportunity lists fields, None if it doesn't say."""
    if not opp.fields:
        return None
    keywords = _field_keywords(profile)
    for raw in opp.fields:
        low = raw.lower().strip()
        if low == "all" or any(low.startswith(a) for a in ALL_FIELDS if a != "all"):
            return True
        tokens = set(re.findall(r"[a-z]+", low))
        for kw in keywords:
            if (" " in kw and kw in low) or (" " not in kw and kw in tokens):
                return True
    return False


def parse_gpa_on_4(text: str | None) -> float | None:
    """Extract a minimum GPA on a 4.0 scale from text like '3.0/4.0' or 'CGPA 2.5'."""
    if not text:
        return None
    match = re.search(r"(\d(?:\.\d{1,2})?)\s*(?:/|out of)\s*4(?:\.0+)?\b", text)
    if not match:
        match = re.search(r"\b(?:gpa|cgpa)\D{0,10}([1-3]\.\d{1,2}|4\.0)\b", text, re.IGNORECASE)
    return float(match.group(1)) if match else None


def in_preferred_region(opp: Opportunity, profile: Profile) -> bool:
    country = (opp.country or "").lower()
    for region in profile.preferred_regions:
        members = REGIONS.get(region.lower(), {region.lower()})
        if any(m in country for m in members):
            return True
    return False


def match(opp: Opportunity, profile: Profile, today: date) -> MatchResult:
    reasons: list[str] = []
    verify: list[str] = []
    exclusions: list[str] = []
    score = 40
    req = profile.requirements
    english = profile.english
    track = english_track(opp)

    # ---- hard requirements -------------------------------------------------------
    country = (opp.country or "").lower()
    if country and any(c in country for c in profile.excluded_countries):
        exclusions.append(f"{opp.country} is in your excluded countries")

    if opp.degree_level in ("phd", "bachelors") and profile.degree_level == "masters":
        exclusions.append(f"This is for {opp.degree_level}, not master's")

    if req.get("funding", "full") == "full":
        if opp.funding_level in ("partial", "tuition_only"):
            exclusions.append("Not fully funded")
        if opp.covers_tuition is False:
            exclusions.append("Does not cover tuition")
    if req.get("require_stipend", True) and opp.stipend is False:
        exclusions.append("No living stipend")

    if req.get("application_fee") == "none":
        if opp.application_fee == "required":
            amount = f" ({opp.application_fee_amount})" if opp.application_fee_amount else ""
            exclusions.append(f"Charges an application fee{amount}")
        elif opp.application_fee in ("unknown", "varies") and not req.get("include_unknown_fee", True):
            exclusions.append("Application fee not confirmed as free")

    if opp.pakistan_eligible is False:
        exclusions.append(f"Not open to {profile.nationality or 'your'} nationals")

    if opp.work_experience_years and opp.work_experience_years > profile.work_experience_years:
        exclusions.append(
            f"Needs {opp.work_experience_years:g} years work experience "
            f"(you have {profile.work_experience_years:g})"
        )

    left = days_until(opp.deadline, today)
    if left is not None and left < 0:
        label = "Estimated deadline" if opp.deadline_is_estimate else "Deadline"
        exclusions.append(f"{label} {opp.deadline} has passed")

    field_ok = fields_match(opp, profile)
    if field_ok is False:
        exclusions.append("Not in your fields (" + ", ".join(opp.fields[:3]) + ")")

    if track == "ielts" and not english.get("ielts_score") and not english.get("plan_to_take_ielts"):
        exclusions.append("Requires IELTS/TOEFL and you don't plan to take it")

    # ---- scoring -----------------------------------------------------------------
    if opp.funding_level == "full":
        score += 20
        reasons.append("Fully funded")
    elif opp.funding_level == "unknown":
        score -= 3
        verify.append("Funding coverage (tuition + stipend)")

    if opp.covers_tuition:
        score += 5
    if opp.stipend:
        score += 10
        reasons.append("Monthly stipend" + (f" ({opp.stipend_amount})" if opp.stipend_amount else ""))
    elif opp.stipend is None:
        verify.append("Living stipend")
    if opp.housing:
        score += 8
        reasons.append("Housing included")
    elif opp.housing is None and req.get("prefer_housing"):
        verify.append("Housing / accommodation")
    if opp.travel:
        score += 3
        reasons.append("Travel covered")
    if opp.insurance:
        score += 2

    if opp.application_fee == "none":
        score += 10
        reasons.append("No application fee")
    elif opp.application_fee in ("unknown", "varies"):
        score -= 3
        verify.append("Application fee" + (f": {opp.application_fee_amount}" if opp.application_fee_amount else ""))

    if track == "no_ielts":
        score += 10 if english.get("prefer_no_ielts") else 5
        reasons.append("No IELTS needed (MOI letter accepted)")
    elif track == "unknown":
        score -= 2
        verify.append("English requirement (IELTS or MOI?)")

    if opp.pakistan_eligible:
        score += 3
    elif opp.pakistan_eligible is None:
        verify.append("Eligibility for Pakistani nationals")

    if field_ok is None:
        verify.append("Whether AI/CS programmes are included")

    if in_preferred_region(opp, profile):
        score += 5
        reasons.append("In your preferred region")

    if left is not None and left >= 0:
        score += 3
    elif opp.deadline is None:
        verify.append("Application deadline")
    if opp.deadline_is_estimate and opp.deadline:
        verify.append("Deadline is an estimate from past years")

    min_gpa = parse_gpa_on_4(opp.min_gpa)
    if min_gpa and profile.cgpa and profile.cgpa_scale == 4.0 and min_gpa > profile.cgpa:
        score -= 10
        verify.append(f"Minimum GPA {min_gpa} is above your {profile.cgpa}")

    if opp.verified:
        score += 2

    score = max(0, min(100, score))
    if exclusions:
        verdict = "excluded"
    elif score >= 75 and opp.funding_level == "full":
        verdict = "strong"
    else:
        verdict = "possible"

    return MatchResult(opportunity=opp, verdict=verdict, score=score, english_track=track,
                       reasons=reasons, to_verify=verify, exclusions=exclusions)


def match_all(opps: list[Opportunity], profile: Profile, today: date) -> list[MatchResult]:
    results = [match(o, profile, today) for o in opps]

    def sort_key(r: MatchResult):
        left = days_until(r.opportunity.deadline, today)
        return (VERDICT_ORDER[r.verdict], -r.score, left if left is not None else 10_000)

    return sorted(results, key=sort_key)


def only_work_experience_blocks(result: MatchResult) -> bool:
    """True if the only reason for exclusion is missing work experience (good 'for later')."""
    return bool(result.exclusions) and all("work experience" in e for e in result.exclusions)

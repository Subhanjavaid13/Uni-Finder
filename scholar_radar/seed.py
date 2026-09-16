"""Loads the curated seed database of recurring fully funded scholarships."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from .config import load_yaml
from .models import Opportunity
from .store import as_date


def _add_years(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:  # 29 February
        return day.replace(year=day.year + years, month=2, day=28)


def roll_estimated_dates(opp: Opportunity, today: date) -> Opportunity:
    """Move a passed *estimated* seed date to the next yearly cycle.

    These scholarships repeat every year, so an estimate from the 2027 cycle
    becomes the 2028 estimate instead of dropping out of the report forever.
    """
    if not opp.deadline_is_estimate:
        return opp
    deadline = as_date(opp.deadline)
    years = 0
    if deadline is not None and deadline < today:
        while _add_years(deadline, years) < today:
            years += 1
        opp.deadline = _add_years(deadline, years).isoformat()

    opens = as_date(opp.opens)
    if opens is not None:
        if years:
            opp.opens = _add_years(opens, years).isoformat()
        elif deadline is None and opens < today:
            shift = 0
            while _add_years(opens, shift) < today:
                shift += 1
            opp.opens = _add_years(opens, shift).isoformat()
    return opp


def load_seed(path: Path) -> list[Opportunity]:
    if not path.exists():
        return []
    opportunities = []
    for entry in load_yaml(path).get("scholarships", []):
        data = {k: v for k, v in entry.items() if v is not None}
        opportunities.append(Opportunity.from_dict({**data, "source": "seed"}))
    return opportunities

from datetime import date

from scholar_radar.config import load_settings
from scholar_radar.matcher import match_all
from scholar_radar.models import Opportunity
from scholar_radar.seed import load_seed, roll_estimated_dates

VALID_FUNDING = {"full", "partial", "tuition_only", "unknown"}
VALID_FEE = {"none", "required", "varies", "unknown"}


def test_seed_entries_are_valid():
    opps = load_seed(load_settings().seed_path)
    assert len(opps) >= 10
    ids = set()
    for opp in opps:
        assert opp.title and opp.url.startswith("https://"), opp.title
        assert opp.source == "seed"
        assert opp.seed_key, f"{opp.title} needs a seed_key"
        assert opp.funding_level in VALID_FUNDING, opp.title
        assert opp.application_fee in VALID_FEE, opp.title
        if opp.deadline:
            date.fromisoformat(opp.deadline)
            assert opp.deadline_is_estimate, "seed dates must be marked as estimates"
        ids.add(opp.id)
    assert len(ids) == len(opps), "duplicate seed ids"


def test_estimated_dates_roll_to_the_next_cycle():
    opp = Opportunity(title="X", url="https://x.org", deadline="2027-01-15",
                      opens="2026-10-15", deadline_is_estimate=True)
    roll_estimated_dates(opp, date(2027, 6, 1))
    assert opp.deadline == "2028-01-15" and opp.opens == "2027-10-15"
    # On 1 Feb 2030 the 2030 deadline is already gone, so the next cycle is 2031
    roll_estimated_dates(opp, date(2030, 2, 1))
    assert opp.deadline == "2031-01-15" and opp.opens == "2030-10-15"


def test_future_and_verified_dates_are_left_alone():
    future = Opportunity(title="X", url="https://x.org", deadline="2027-01-15",
                         deadline_is_estimate=True)
    roll_estimated_dates(future, date(2026, 9, 16))
    assert future.deadline == "2027-01-15"
    verified = Opportunity(title="X", url="https://x.org", deadline="2026-01-15",
                           deadline_is_estimate=False)
    roll_estimated_dates(verified, date(2027, 6, 1))
    assert verified.deadline == "2026-01-15"


def test_seed_still_matches_after_the_student_graduates():
    """Without rollover the whole report would empty out in mid-2027."""
    settings = load_settings()
    later = date(2028, 4, 1)
    seeds = [roll_estimated_dates(o, later) for o in load_seed(settings.seed_path)]
    results = match_all(seeds, settings.profile, later)
    assert not any("has passed" in e for r in results for e in r.exclusions)
    assert sum(r.verdict != "excluded" for r in results) >= 10

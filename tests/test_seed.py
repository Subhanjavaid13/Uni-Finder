from datetime import date

from scholar_radar.config import load_settings
from scholar_radar.seed import load_seed

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

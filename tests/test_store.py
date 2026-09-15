from datetime import date

from scholar_radar.models import Opportunity
from scholar_radar.store import State, content_hash

TODAY = date(2026, 9, 15)


def make_opp(**kw):
    base = dict(title="MSc AI Scholarship", url="https://uni.example/ai", source="search")
    base.update(kw)
    return Opportunity(**base)


def test_page_change_detection(tmp_path):
    state = State(tmp_path / "state.json")
    h = content_hash("Applications   CLOSED")
    assert state.page_changed("https://a.org", h, TODAY) is True
    assert state.page_changed("https://a.org", content_hash("applications closed"), TODAY) is False
    assert state.page_changed("https://a.org", content_hash("applications open"), TODAY) is True


def test_upsert_new_updated_unchanged_and_persistence(tmp_path):
    path = tmp_path / "state.json"
    state = State(path)
    assert state.upsert(make_opp(deadline="2027-01-15"), TODAY) == "new"
    assert state.upsert(make_opp(deadline="2027-01-15"), TODAY) == "unchanged"
    # Unknown values from a weaker page must not erase known facts
    assert state.upsert(make_opp(deadline=None, application_fee="unknown"), TODAY) == "unchanged"
    assert state.upsert(make_opp(deadline="2027-02-01"), TODAY) == "updated"
    state.save()
    reloaded = State(path)
    assert reloaded.all_opportunities()[0].deadline == "2027-02-01"


def test_seed_overrides_ignore_past_deadlines(tmp_path):
    state = State(tmp_path / "state.json")
    seed = make_opp(source="seed", seed_key="gks", deadline="2027-03-15", deadline_is_estimate=True)
    old_page = make_opp(deadline="2026-03-10", application_fee="none")
    assert state.record_seed_findings("gks", old_page, TODAY) is True
    applied = state.apply_seed_overrides(seed)
    assert applied.deadline == "2027-03-15" and applied.deadline_is_estimate is True
    assert applied.application_fee == "none" and applied.verified is True

    new_page = make_opp(deadline="2027-03-01")
    state.record_seed_findings("gks", new_page, TODAY)
    applied = state.apply_seed_overrides(seed)
    assert applied.deadline == "2027-03-01" and applied.deadline_is_estimate is False


def test_reminders_fire_once_per_threshold(tmp_path):
    state = State(tmp_path / "state.json")
    thresholds = [30, 14, 7, 3]
    assert state.reminder_due("x", 40, thresholds) is None
    assert state.reminder_due("x", 20, thresholds) == 30
    state.mark_reminder("x", 30, thresholds)
    assert state.reminder_due("x", 20, thresholds) is None
    # Jumping straight to 5 days left sends the 7-day reminder, not the stale 14-day one
    assert state.reminder_due("x", 5, thresholds) == 7
    state.mark_reminder("x", 7, thresholds)
    assert state.reminder_due("x", 10, thresholds) is None
    assert state.reminder_due("x", -1, thresholds) is None


def test_seen_urls_and_expiry(tmp_path):
    state = State(tmp_path / "state.json")
    state.mark_seen("https://s.org", date(2026, 1, 1))
    assert state.is_seen("https://s.org", TODAY, recheck_days=365) is True
    assert state.is_seen("https://s.org", TODAY, recheck_days=30) is False
    state.upsert(make_opp(title="Old", deadline="2026-01-01"), TODAY)
    state.upsert(make_opp(title="Seed old", source="seed", deadline="2026-01-01"), TODAY)
    state.remove_expired(TODAY)
    titles = {o.title for o in state.all_opportunities()}
    assert titles == {"Seed old"}

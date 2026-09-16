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
    applied = state.apply_seed_overrides(seed, TODAY)
    assert applied.deadline == "2027-03-15" and applied.deadline_is_estimate is True
    assert applied.application_fee == "none" and applied.verified is True

    new_page = make_opp(deadline="2027-03-01")
    state.record_seed_findings("gks", new_page, TODAY)
    applied = state.apply_seed_overrides(seed, TODAY)
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


def test_reminders_restart_for_the_next_years_deadline(tmp_path):
    """Recurring scholarships must alert again every cycle, not only the first year."""
    state = State(tmp_path / "state.json")
    thresholds = [30, 14, 7, 3]
    assert state.reminder_due("x", 20, thresholds, "2027-01-15") == 30
    state.mark_reminder("x", 30, thresholds, "2027-01-15")
    assert state.reminder_due("x", 20, thresholds, "2027-01-15") is None
    # Next cycle: same scholarship, new deadline -> reminders start again
    assert state.reminder_due("x", 26, thresholds, "2028-01-15") == 30
    state.mark_reminder("x", 30, thresholds, "2028-01-15")
    assert state.reminder_due("x", 12, thresholds, "2028-01-15") == 14


def test_reminders_read_legacy_state_format(tmp_path):
    state = State(tmp_path / "state.json")
    state.data["reminders_sent"]["x"] = [7, 14, 30]  # written by an older version
    assert state.reminder_due("x", 20, [30, 14, 7], "2027-01-15") is None


def test_stale_verified_deadline_does_not_override_fresh_estimate(tmp_path):
    state = State(tmp_path / "state.json")
    seed = make_opp(source="seed", seed_key="gks", deadline="2028-03-15", deadline_is_estimate=True)
    state.record_seed_findings("gks", make_opp(deadline="2027-03-01", application_fee="none"), TODAY)
    # A year later that verified date is history; the seed estimate must win again.
    applied = state.apply_seed_overrides(seed, date(2027, 9, 15))
    assert applied.deadline == "2028-03-15" and applied.deadline_is_estimate is True
    assert applied.application_fee == "none"  # non-date facts are still applied


def test_prune_drops_reminders_for_forgotten_opportunities(tmp_path):
    state = State(tmp_path / "state.json")
    opp = make_opp(deadline="2027-01-15")
    state.upsert(opp, TODAY)
    state.mark_reminder(opp.id, 30, [30], "2027-01-15")
    state.mark_reminder("gone-long-ago", 30, [30], "2020-01-15")
    state.prune_seen(TODAY)
    assert list(state.data["reminders_sent"]) == [opp.id]


def test_pending_news_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    state = State(path)
    assert state.pending_news() == {}
    state.set_pending_news({"a": "new"})
    state.save()
    assert State(path).pending_news() == {"a": "new"}
    state.clear_pending_news()
    assert state.pending_news() == {}


def test_corrupt_dates_do_not_crash(tmp_path):
    state = State(tmp_path / "state.json")
    state.data["seen_urls"]["https://bad.example"] = "not-a-date"
    assert state.is_seen("https://bad.example", TODAY) is False
    state.prune_seen(TODAY)
    state.upsert(make_opp(deadline="soon"), TODAY)
    state.remove_expired(TODAY)
    assert len(state.all_opportunities()) == 1


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

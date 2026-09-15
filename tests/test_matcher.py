from datetime import date

from scholar_radar.config import Profile, load_settings
from scholar_radar.matcher import (
    english_track,
    fields_match,
    match,
    match_all,
    only_work_experience_blocks,
    parse_gpa_on_4,
)
from scholar_radar.models import Opportunity
from scholar_radar.seed import load_seed

TODAY = date(2026, 9, 15)


def profile(**overrides):
    raw = {
        "nationality": "Pakistan",
        "education": {"cgpa": 3.1, "cgpa_scale": 4.0},
        "target": {"degree_level": "masters",
                   "fields": ["Computer Science", "Artificial Intelligence"],
                   "preferred_regions": ["Europe"], "excluded_countries": []},
        "english": {"has_moi_letter": True, "ielts_score": None,
                    "plan_to_take_ielts": True, "prefer_no_ielts": True},
        "work_experience_years": 0,
        "requirements": {"funding": "full", "require_stipend": True, "prefer_housing": True,
                         "application_fee": "none", "include_unknown_fee": True},
    }
    for key, value in overrides.items():
        raw[key] = {**raw[key], **value} if isinstance(value, dict) else value
    return Profile(raw)


def ideal(**kw):
    base = dict(
        title="MSc AI Excellence Scholarship", url="https://uni.example/ai", source="search",
        country="Germany", degree_level="masters", fields=["Artificial Intelligence"],
        funding_level="full", covers_tuition=True, stipend=True, housing=True,
        application_fee="none", ielts_required=False, moi_accepted=True,
        pakistan_eligible=True, deadline="2027-01-15",
    )
    base.update(kw)
    return Opportunity(**base)


def test_ideal_opportunity_is_strong_no_ielts():
    result = match(ideal(), profile(), TODAY)
    assert result.verdict == "strong"
    assert result.english_track == "no_ielts"
    assert "No application fee" in result.reasons
    assert "In your preferred region" in result.reasons
    assert result.exclusions == []


def test_hard_exclusions():
    p = profile()
    cases = {
        "Charges an application fee": ideal(application_fee="required"),
        "Not fully funded": ideal(funding_level="partial"),
        "No living stipend": ideal(stipend=False),
        "Not open to Pakistan": ideal(pakistan_eligible=False),
        "Needs 2 years": ideal(work_experience_years=2),
        "has passed": ideal(deadline="2026-09-01"),
        "not master's": ideal(degree_level="phd"),
        "Not in your fields": ideal(fields=["Nursing", "Law"]),
    }
    for expected, opp in cases.items():
        result = match(opp, p, TODAY)
        assert result.verdict == "excluded", expected
        assert any(expected in e for e in result.exclusions), (expected, result.exclusions)


def test_ielts_track_depends_on_plans():
    opp = ideal(ielts_required=True, moi_accepted=None)
    assert english_track(opp) == "ielts"
    assert match(opp, profile(), TODAY).verdict != "excluded"
    no_ielts_plans = profile(english={"plan_to_take_ielts": False})
    assert match(opp, no_ielts_plans, TODAY).verdict == "excluded"


def test_unknowns_become_verify_items_not_exclusions():
    opp = Opportunity(title="Scholarship news", url="https://n.example/x", funding_level="full")
    result = match(opp, profile(), TODAY)
    assert result.verdict == "possible"
    assert any("Application fee" in v for v in result.to_verify)
    assert any("English" in v for v in result.to_verify)
    assert any("deadline" in v.lower() for v in result.to_verify)


def test_field_matching_and_gpa_parsing():
    p = profile()
    assert fields_match(ideal(fields=["all fields"]), p) is True
    assert fields_match(ideal(fields=["Informatics and Computing"]), p) is True
    assert fields_match(ideal(fields=["Agriculture"]), p) is False
    assert fields_match(ideal(fields=[]), p) is None
    assert fields_match(ideal(fields=["Aid and humanitarian work"]), p) is False
    assert fields_match(ideal(fields=["Allied health sciences"]), p) is False
    assert fields_match(ideal(fields=["all fields (development-focused)"]), p) is True
    assert parse_gpa_on_4("minimum 3.3/4.0") == 3.3
    assert parse_gpa_on_4("CGPA of 2.5") == 2.5
    assert parse_gpa_on_4("80%") is None
    low_gpa = match(ideal(min_gpa="3.5/4.0"), p, TODAY)
    assert any("Minimum GPA" in v for v in low_gpa.to_verify)


def test_seed_database_against_real_profile():
    settings = load_settings()
    results = {r.opportunity.seed_key: r for r in
               match_all(load_seed(settings.seed_path), settings.profile, TODAY)}
    assert results["turkiye_burslari"].verdict == "strong"
    assert results["turkiye_burslari"].english_track == "no_ielts"
    assert results["chevening"].verdict == "excluded"
    assert only_work_experience_blocks(results["daad_epos"])
    assert results["swedish_institute"].verdict == "excluded"  # paid application
    ordered = match_all(load_seed(settings.seed_path), settings.profile, TODAY)
    verdicts = [r.verdict for r in ordered]
    assert verdicts == sorted(verdicts, key=["strong", "possible", "excluded"].index)

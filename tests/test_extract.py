from datetime import date

from scholar_radar.extract import (
    extract_opportunities,
    heuristic_extract,
    normalize_item,
    parse_date,
    parse_date_precise,
)
from scholar_radar.llm import BaseLLM, LLMError, parse_json_text
from scholar_radar.models import Candidate

TODAY = date(2026, 9, 15)


class FakeLLM(BaseLLM):
    def __init__(self, response=None, error=None):
        super().__init__("fake", 0)
        self.response, self.error = response, error

    def complete_json(self, system, prompt):
        if self.error:
            raise self.error
        return self.response


def cand(**kw):
    base = dict(url="https://uni.example/msc-ai", title="MSc AI", source="search",
                text="Fully funded master scholarship in Artificial Intelligence. "
                     "Monthly stipend and free accommodation. No application fee. "
                     "IELTS not required. Application deadline: 15 January 2027.")
    base.update(kw)
    return Candidate(**base)


def test_parse_json_text_handles_fences_and_prose():
    assert parse_json_text('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_text('Sure! {"a": {"b": 2}} hope it helps') == {"a": {"b": 2}}


def test_parse_date_requires_year():
    assert parse_date("2027-01-15") == "2027-01-15"
    assert parse_date("15 January 2027") == "2027-01-15"
    assert parse_date("January 15") is None
    assert parse_date(None) is None


def test_parse_date_marks_month_only_dates_as_estimates():
    assert parse_date_precise("2027-01-15") == ("2027-01-15", False)
    assert parse_date_precise("15 January 2027") == ("2027-01-15", False)
    assert parse_date_precise("March 1, 2027") == ("2027-03-01", False)
    # dateutil invents the 1st here - it must not look like a confirmed date
    assert parse_date_precise("January 2027") == ("2027-01-01", True)
    assert parse_date_precise("2027") == ("2027-01-01", True)
    assert parse_date_precise("Fall 2027") == (None, False)  # unparseable stays empty


def test_repeated_ai_failures_disable_the_client():
    """Free-tier exhaustion must stop the run using AI instead of retrying every page."""
    broken = FakeLLM(error=LLMError("gemini HTTP 429: quota"))
    for _ in range(3):
        extract_opportunities(cand(), broken, TODAY)
    assert broken.disabled is True
    working = FakeLLM({"is_scholarship_page": True, "opportunities": [{"title": "A"}]})
    extract_opportunities(cand(), working, TODAY)
    assert working.disabled is False


def test_normalize_item_coerces_and_validates():
    opp = normalize_item({
        "title": "  AI Scholarship ", "funding_level": "FULL", "application_fee": "free?",
        "stipend": "yes", "housing": "no", "deadline": "March 1, 2027",
        "work_experience_years": "2 years", "degree_level": "Masters",
        "fields": ["AI", ""], "apply_url": "https://apply.example/ai",
    }, cand())
    assert opp.title == "AI Scholarship"
    assert opp.funding_level == "full"
    assert opp.application_fee == "unknown"
    assert opp.stipend is True and opp.housing is False
    assert opp.deadline == "2027-03-01"
    assert opp.work_experience_years == 2.0
    assert opp.degree_level == "masters"
    assert opp.fields == ["AI"]
    assert opp.url == "https://apply.example/ai"


def test_extract_with_llm_and_fallback_on_error():
    llm = FakeLLM({"is_scholarship_page": True, "opportunities": [
        {"title": "A", "funding_level": "full"}, {"title": "B"}, "junk"]})
    assert [o.title for o in extract_opportunities(cand(), llm, TODAY)] == ["A", "B"]

    not_page = FakeLLM({"is_scholarship_page": False, "opportunities": []})
    assert extract_opportunities(cand(), not_page, TODAY) == []

    broken = FakeLLM(error=LLMError("rate limited"))
    fallback = extract_opportunities(cand(), broken, TODAY)
    assert len(fallback) == 1 and fallback[0].funding_level == "full"


def test_heuristic_extract():
    [opp] = heuristic_extract(cand())
    assert opp.funding_level == "full"
    assert opp.stipend is True and opp.housing is True
    assert opp.application_fee == "none"
    assert opp.ielts_required is False and opp.moi_accepted is True
    assert opp.deadline == "2027-01-15"
    assert opp.degree_level == "masters"
    assert "Artificial Intelligence" in opp.fields
    assert heuristic_extract(cand(title="Cooking class", text="Learn to bake bread")) == []
    [vague] = heuristic_extract(cand(text="Scholarship info. Housing is not included. Tuition fees apply."))
    assert vague.housing is None and vague.covers_tuition is None

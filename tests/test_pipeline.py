from dataclasses import replace
from datetime import date

import pytest

from scholar_radar.config import load_settings
from scholar_radar.emailer import EmailError
from scholar_radar.fetch import Page
from scholar_radar.llm import BaseLLM
from scholar_radar.models import Candidate
from scholar_radar.pipeline import RunOptions, run
from scholar_radar.store import State

TODAY = date(2026, 9, 15)
TB_PAGE = "Turkiye Scholarships applications 2027. " * 10


class FakeFetcher:
    """Serves one official page; everything else is unreachable."""

    def __init__(self, pages):
        self.pages = pages

    def fetch_page(self, url, verify=True):
        text = self.pages.get(url)
        return Page(url=url, title="Official", text=text) if text else None

    def get(self, url):
        return None


class FakeLLM(BaseLLM):
    def __init__(self, response):
        super().__init__("fake", 0)
        self.response = response

    def complete_json(self, system, prompt):
        self.calls += 1
        return self.response


@pytest.fixture
def settings(tmp_path, monkeypatch):
    base = load_settings()
    monkeypatch.delenv("SMTP_HOST", raising=False)
    sources = replace(base.sources, official_pages=[
        {"name": "Turkiye", "url": "https://tb.example", "country": "Turkey", "seed_key": "turkiye_burslari"},
    ], rss_feeds=[])
    return replace(base, sources=sources, state_path=tmp_path / "state.json", output_dir=tmp_path / "out")


def test_seed_only_run_builds_report_and_remembers(settings):
    options = RunOptions(dry_run=True, save_state=True, use_official=False, use_rss=False,
                         use_search=False, use_ai=False)
    first = run(settings, options, today=TODAY, fetcher=FakeFetcher({}))
    assert first.report_path.exists()
    assert first.stats["new_or_updated"] > 0
    assert "Turkiye Burslari" in first.report_path.read_text(encoding="utf-8")

    second = run(settings, options, today=TODAY, fetcher=FakeFetcher({}))
    assert second.stats["new_or_updated"] == 0, "second run must not repeat old news"


def test_official_page_verifies_seed_deadline(settings):
    llm = FakeLLM({"is_scholarship_page": True, "opportunities": [
        {"title": "Turkiye Scholarships", "deadline": "2027-02-18", "application_fee": "none",
         "evidence": "Applications close 18 February 2027"}]})
    options = RunOptions(dry_run=True, save_state=True, use_rss=False, use_search=False)
    summary = run(settings, options, today=TODAY, llm=llm,
                  fetcher=FakeFetcher({"https://tb.example": TB_PAGE}))
    assert llm.calls == 1
    state = State(settings.state_path)
    tb = next(o for o in state.all_opportunities() if o.seed_key == "turkiye_burslari")
    assert tb.deadline == "2027-02-18" and tb.deadline_is_estimate is False and tb.verified
    assert summary.stats["official_pages_changed"] == 1

    # Unchanged page next week -> no AI call
    run(settings, options, today=date(2026, 9, 22), llm=llm,
        fetcher=FakeFetcher({"https://tb.example": TB_PAGE}))
    assert llm.calls == 1


def test_keyword_mode_never_overwrites_seed_facts(settings):
    page = ("Turkiye Scholarships fully funded master scholarship. No fee. "
            "Deadline: 1 October 2026. " + "More details about the programme. " * 10)
    options = RunOptions(dry_run=True, save_state=True, use_rss=False, use_search=False, use_ai=False)
    run(settings, options, today=TODAY, fetcher=FakeFetcher({"https://tb.example": page}))
    tb = next(o for o in State(settings.state_path).all_opportunities() if o.seed_key == "turkiye_burslari")
    assert tb.deadline_is_estimate is True and not tb.verified


def test_near_empty_official_page_is_reported_not_analysed(settings):
    llm = FakeLLM({"is_scholarship_page": False})
    options = RunOptions(dry_run=True, use_rss=False, use_search=False)
    summary = run(settings, options, today=TODAY, llm=llm,
                  fetcher=FakeFetcher({"https://tb.example": "Loading..."}))
    assert llm.calls == 0
    assert any("almost no text" in e for e in summary.errors)


def test_real_run_without_email_config_fails_and_keeps_state_unsaved(settings):
    options = RunOptions(use_official=False, use_rss=False, use_search=False, use_ai=False)
    with pytest.raises(EmailError):
        run(settings, options, today=TODAY, fetcher=FakeFetcher({}))
    assert not settings.state_path.exists()

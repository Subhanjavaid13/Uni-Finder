from datetime import date

from scholar_radar.config import Profile
from scholar_radar.sources import build_queries, is_relevant, relevance_priority
from scholar_radar.sources.filters import is_blocked_url
from scholar_radar.sources.rss import parse_feed
from scholar_radar.store import State

TODAY = date(2026, 9, 15)

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>Scholarships</title>
<item><title>Fully Funded MSc Artificial Intelligence Scholarship 2027 in Hungary</title>
  <link>https://news.example/hungary-ai</link>
  <description>&lt;p&gt;Master's scholarship with monthly stipend&lt;/p&gt;</description>
  <pubDate>Mon, 14 Sep 2026 10:00:00 GMT</pubDate></item>
<item><title>Photography contest for teenagers</title>
  <link>https://news.example/photo</link>
  <description>Win a camera</description>
  <pubDate>Mon, 14 Sep 2026 10:00:00 GMT</pubDate></item>
<item><title>Old fully funded master scholarship</title>
  <link>https://news.example/old</link>
  <description>scholarship for masters</description>
  <pubDate>Mon, 05 Jan 2026 10:00:00 GMT</pubDate></item>
</channel></rss>"""


def test_relevance_filters():
    assert is_relevant("Fully funded Master's scholarship in Germany")
    assert not is_relevant("Undergraduate sports camp")
    assert relevance_priority("fully funded MSc Computer Science with stipend") >= 6
    assert is_blocked_url("https://www.youtube.com/watch?v=1")
    assert not is_blocked_url("https://www.daad.de/en/")


def test_parse_feed_keeps_only_new_relevant_recent_entries(tmp_path):
    state = State(tmp_path / "s.json")
    found = parse_feed(RSS, "Test feed", state, TODAY, keywords=None)
    assert [c.url for c in found] == ["https://news.example/hungary-ai"]
    assert found[0].source == "rss" and "stipend" in found[0].snippet
    assert state.is_seen("https://news.example/photo", TODAY)  # irrelevant marked seen


def test_build_queries_rotates_countries_weekly():
    profile = Profile({"target": {"fields": ["Artificial Intelligence", "Computer Science"],
                                  "intake_years": [2027]}})
    cfg = {
        "queries": ["fully funded masters {field} scholarship {year}"],
        "country_queries": ["masters scholarship {country} {year} {field}"],
        "countries": ["A", "B", "C", "D", "E"],
        "countries_per_run": 2,
        "queries_per_run": 10,
    }
    week1 = build_queries(cfg, profile, TODAY)
    week2 = build_queries(cfg, profile, date(2026, 9, 22))
    assert len(week1) == 3
    assert all("2027" in q and "{" not in q for q in week1)
    assert week1[1:] != week2[1:], "countries should rotate between weeks"

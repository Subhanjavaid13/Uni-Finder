import json
import re
from dataclasses import replace
from datetime import date

from scholar_radar.config import load_settings
from scholar_radar.dashboard import build_dashboard, collect_data

TODAY = date(2026, 9, 16)

PROGRAM = {
    "country": "Italy", "region": "Sicily", "city": "Palermo",
    "university": "Università degli Studi di Palermo", "university_type": "public",
    "program_name": "MSc Computer Science and Artificial Intelligence",
    "field": "Artificial Intelligence", "program_url": "https://www.unipa.it/ai",
    "language": "English", "application_fee_free": True, "moi_accepted": True,
    "ielts_required": False, "fully_funded_possible": "yes", "confidence": "high",
    "scholarships": [{"name": "ERSU Palermo", "covers": "tuition + housing + meals",
                      "need_based": True, "type": "regional"}],
    "documents": ["Transcripts"], "sources": ["https://www.unipa.it/ai"],
    "notes": "</script><script>alert(1)</script>",  # must not break the page
}


def settings_for(tmp_path):
    base = load_settings()
    return replace(base, state_path=tmp_path / "state.json", output_dir=tmp_path / "out")


def embedded_data(html: str) -> dict:
    payload = re.search(r"const DATA = (\{.*?\});\n", html, re.DOTALL).group(1)
    return json.loads(payload.replace("<\\/", "</"))


def test_dashboard_builds_from_research_and_seed(tmp_path):
    research = tmp_path / "raw"
    research.mkdir()
    (research / "italy.json").write_text(json.dumps({"programs": [PROGRAM]}), encoding="utf-8")
    out = tmp_path / "dashboard.html"

    stats = build_dashboard(settings_for(tmp_path), out, TODAY, research_dir=research)
    assert stats["programmes"] == 1
    assert stats["weekly_finds"] >= 10  # seed scholarships when there is no saved state
    assert stats["countries_with_visa_info"] >= 30

    html = out.read_text(encoding="utf-8")
    assert "__DATA__" not in html
    assert "</script><script>alert(1)" not in html  # escaped inside the JSON payload
    data = embedded_data(html)
    assert data["programs"][0]["university"] == "Università degli Studi di Palermo"
    assert data["programs"][0]["fit"] in ("Top match", "Good", "Check")
    # filters rely on real booleans, not the "Yes"/"No" text used in Excel
    assert data["programs"][0]["application_fee_free"] is True
    assert data["programs"][0]["moi_accepted"] is True
    assert data["programs"][0]["ielts_required"] is False
    assert any(f["english_track"] == "no_ielts" for f in data["finds"])
    assert any(v["country"] == "Italy" and v["bank_statement"] for v in data["visa"])
    assert any(d["name"].startswith("Bank statement") for d in data["documents"])
    # every tab has something to show
    for tab in ("Universities", "Weekly finds", "Visa &amp; money", "Documents"):
        assert tab in html


def test_dashboard_without_research_still_works(tmp_path):
    out = tmp_path / "d.html"
    stats = build_dashboard(settings_for(tmp_path), out, TODAY, research_dir=tmp_path / "missing")
    assert stats["programmes"] == 0
    assert out.exists()


def test_collect_data_marks_visa_countries_you_match(tmp_path):
    data = collect_data(settings_for(tmp_path), TODAY, research_dir=tmp_path / "missing")
    hungary = next(v for v in data["visa"] if v["country"] == "Hungary")
    assert hungary["matches"] >= 1

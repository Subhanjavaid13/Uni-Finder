import os

from scholar_radar.config import load_dotenv, load_settings
from scholar_radar.models import Opportunity, make_id


def test_settings_load_from_repo_config():
    settings = load_settings()
    assert settings.profile.degree_level == "masters"
    assert "Artificial Intelligence" in settings.profile.fields
    assert settings.sources.official_pages, "expected official pages"
    assert settings.sources.rss_feeds, "expected rss feeds"
    assert all("url" in p for p in settings.sources.official_pages)


def test_dotenv_does_not_override_real_env(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("SR_TEST_A=from_file\nSR_TEST_B='quoted'\n# comment\n", encoding="utf-8")
    monkeypatch.setenv("SR_TEST_A", "from_env")
    monkeypatch.delenv("SR_TEST_B", raising=False)
    load_dotenv(env_file)
    assert os.environ["SR_TEST_A"] == "from_env"
    assert os.environ["SR_TEST_B"] == "quoted"
    monkeypatch.delenv("SR_TEST_B")


def test_opportunity_id_is_stable_and_roundtrips():
    a = make_id("https://www.example.org/prog/", "MSc AI Scholarship")
    b = make_id("http://example.org/prog", "msc ai scholarship")
    assert a == b
    opp = Opportunity(title="MSc AI", url="https://x.org", fields=["AI"])
    data = opp.to_dict()
    data["unknown_key"] = 1
    assert Opportunity.from_dict(data) == opp

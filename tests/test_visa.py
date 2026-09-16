from scholar_radar.config import load_settings
from scholar_radar.visa import load_visa_money, lookup, summary_line

VALID_FLAGS = {"yes", "maybe", "unknown"}


def table():
    return load_visa_money(load_settings().visa_path)


def test_visa_money_config_is_usable():
    data = table()
    assert len(data) >= 30
    for info in data.values():
        assert info.country and info.proof_of_funds and info.bank_statement
        assert info.scholarship_letter_accepted in VALID_FLAGS


def test_lookup_handles_the_way_countries_are_written():
    data = table()
    assert lookup("Italy", data).country == "Italy"
    assert lookup("italy", data).country == "Italy"
    assert lookup("UK", data).country == "United Kingdom"
    assert lookup("Türkiye", data).country == "Turkey"
    assert lookup("European Union (study in 2-3 countries)", data).country == "European Union" \
        if "european union" in data else True
    assert lookup("Germany (Bavaria)", data).country == "Germany"
    assert lookup(None, data) is None
    assert lookup("Atlantis", data) is None


def test_key_countries_answer_the_bank_statement_question():
    data = table()
    germany = lookup("Germany", data)
    assert "blocked account" in germany.bank_statement.lower()
    assert germany.scholarship_letter_accepted == "yes"
    uk = lookup("United Kingdom", data)
    assert "sponsor" in uk.bank_statement.lower()
    italy = lookup("Italy", data)
    assert "10,179" in italy.proof_of_funds
    assert "Show" in summary_line(italy) and "Bank statement" in summary_line(italy)

from scholar_radar.checklist import BASE_CHECKLIST, classify_document, document_demand
from scholar_radar.models import MatchResult, Opportunity


def result(title, docs):
    opp = Opportunity(title=title, url=f"https://x.org/{title}", required_documents=docs)
    return MatchResult(opportunity=opp, verdict="strong", score=90, english_track="no_ielts")


def test_classify_document():
    assert classify_document("2 Recommendation letters").key == "recommendations"
    assert classify_document("English proof (IELTS/TOEFL or MOI letter)").key in ("moi", "english_test")
    assert classify_document("Notarized degree and transcripts").key == "transcripts"
    assert classify_document("Europass CV").key == "cv"
    assert classify_document("Something unusual") is None


def test_document_demand_counts_each_scholarship_once():
    demand, other = document_demand([
        result("A", ["Motivation letter", "Study plan", "Passport", "Portrait photo"]),
        result("B", ["Statement of purpose", "Passport copy"]),
    ])
    by_key = {d.item.key: d for d in demand}
    assert by_key["sop"].needed_by == ["A", "B"]
    assert by_key["passport"].needed_by == ["A", "B"]
    assert other == {"Portrait photo": ["A"]}
    assert [d.item.key for d in demand] == [i.key for i in BASE_CHECKLIST]

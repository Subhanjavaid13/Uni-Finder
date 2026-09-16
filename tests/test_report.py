from datetime import date

from scholar_radar.checklist import document_demand
from scholar_radar.config import Profile, load_settings
from scholar_radar.matcher import match
from scholar_radar.models import Opportunity
from scholar_radar.report import Reminder, ReportData, build_report
from scholar_radar.visa import load_visa_money

TODAY = date(2026, 9, 15)
PROFILE = Profile({
    "target": {"fields": ["Artificial Intelligence"], "preferred_regions": ["Europe"]},
    "english": {"plan_to_take_ielts": True, "prefer_no_ielts": True},
    "requirements": {"funding": "full", "application_fee": "none", "include_unknown_fee": True},
})


def test_report_renders_sections_and_escapes_html():
    no_ielts = match(Opportunity(
        title="MSc AI <script>alert(1)</script>", url="https://uni.example/ai?a=1&b=2",
        country="Hungary", funding_level="full", stipend=True, covers_tuition=True,
        application_fee="none", moi_accepted=True, deadline="2026-09-25",
        required_documents=["Motivation letter", "Passport"], fields=["Artificial Intelligence"],
    ), PROFILE, TODAY)
    ielts = match(Opportunity(
        title="KAUST MS", url="https://kaust.example", funding_level="full", ielts_required=True,
        deadline="2027-01-15", deadline_is_estimate=True, fields=["Computer Science", "AI"],
    ), PROFILE, TODAY)
    active = [no_ielts, ielts]
    demand, other = document_demand(active)
    data = ReportData(
        today=TODAY, new_results=active, statuses={no_ielts.opportunity.id: "new"},
        reminders=[Reminder(no_ielts, 10, 14)], opening_soon=[], active=active, later=[],
        demand=demand, other_docs=other, stats={"pages_analysed": 3}, errors=["x failed"],
        visa_money=load_visa_money(load_settings().visa_path),
    )
    subject, html, text = build_report(data)

    assert "Money for your visa" in html and "Bank statement?" in html
    assert "Hungary" in html
    assert "MONEY FOR YOUR VISA" in text

    assert "2 new/updated matches" in subject and "1 deadline alert" in subject
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "a=1&amp;b=2" in html
    assert "No IELTS needed (MOI letter accepted)" in html
    assert "IELTS / TOEFL required" in html
    assert "(estimate - confirm)" in html
    assert "Deadline alerts" in html and "Documents you need" in html
    assert "10 days left" in text
    assert "Motivation letter" in text

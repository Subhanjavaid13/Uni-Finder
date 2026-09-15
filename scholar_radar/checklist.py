"""The documents you need, why, where to get them, and which matches ask for them."""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import MatchResult


@dataclass
class ChecklistItem:
    key: str
    name: str
    why: str
    how: str
    when: str
    cost: str
    keywords: list[str]
    track: str = "all"  # "all" | "ielts"


@dataclass
class DocumentDemand:
    item: ChecklistItem
    needed_by: list[str] = field(default_factory=list)


BASE_CHECKLIST: list[ChecklistItem] = [
    ChecklistItem(
        "passport", "Valid passport",
        "Needed for almost every application and for the visa.",
        "Apply at a passport office (DGIP). Keep it valid for your whole study period.",
        "Now - it can take several weeks.", "Government fee (normal / urgent)",
        ["passport"],
    ),
    ChecklistItem(
        "transcripts", "Transcripts (HEC attested)",
        "Proves your grades and CGPA. Embassies check HEC attestation.",
        "Get transcripts from VU, then attest them on HEC's online system (HEDAS).",
        "Now for semesters so far; final transcript after graduation.", "HEC per-document fee",
        ["transcript", "mark sheet", "marksheet", "academic record", "grades", "notarized degree"],
    ),
    ChecklistItem(
        "degree", "Degree certificate / expected graduation letter",
        "Shows you have (or will soon have) a 4-year bachelor's degree.",
        "Before graduation ask VU for a provisional/expected-completion letter; attest the degree later.",
        "Letter now; degree after graduation.", "Small university fee",
        ["degree", "diploma", "graduation", "bachelor"],
    ),
    ChecklistItem(
        "moi", "English Medium of Instruction (MOI) letter",
        "Many scholarships accept it INSTEAD of IELTS.",
        "Request from VU's registrar/examinations office stating your degree was taught in English.",
        "Now.", "Free or small fee",
        ["medium of instruction", "moi", "english-medium", "english medium"],
    ),
    ChecklistItem(
        "english_test", "IELTS Academic / TOEFL / Duolingo English Test",
        "Required by scholarships in your IELTS track; boosts others.",
        "IELTS via British Council or IDP; Duolingo English Test online. Target 6.5+ overall.",
        "2-3 months before the first IELTS-track deadline.",
        "IELTS roughly PKR 60-75k; Duolingo about USD 70 (check current prices)",
        ["ielts", "toefl", "english proficiency", "english language", "duolingo", "language certificate",
         "english proof"],
        track="ielts",
    ),
    ChecklistItem(
        "cv", "CV (Europass format for Europe)",
        "Summarises your education, projects and skills.",
        "Create free at europass.europa.eu. Add your AI/automation projects with GitHub links.",
        "Now - update as you build projects.", "Free",
        ["cv", "resume", "curriculum vitae", "europass"],
    ),
    ChecklistItem(
        "sop", "Statement of purpose / motivation letter / study plan",
        "The most important part of competitive applications.",
        "Write it yourself and tailor it to each programme: why this field, why this programme, your goals.",
        "Start a master draft now; tailor 3-4 weeks before each deadline.", "Free",
        ["motivation", "statement of purpose", "personal statement", "study plan", "essay",
         "research proposal", "research plan", "study objectives"],
    ),
    ChecklistItem(
        "recommendations", "2-3 recommendation letters",
        "Professors vouch for your ability. Required by nearly all funded programmes.",
        "Ask your final-year-project supervisor and instructors who know your work. Give them 4-6 weeks.",
        "Ask by October-November.", "Free",
        ["recommendation", "reference", "referee"],
    ),
    ChecklistItem(
        "portfolio", "Portfolio (GitHub projects)",
        "Shows real skills - your agents and automations stand out in AI/CS applications.",
        "Publish projects on GitHub with clear READMEs; link them in your CV and SOP.",
        "Ongoing.", "Free",
        ["portfolio", "publication", "github"],
    ),
    ChecklistItem(
        "police", "Police character certificate",
        "Asked by some scholarships (e.g. China) and many visas.",
        "Apply through your provincial police service (e.g. Police Khidmat Markaz in Punjab).",
        "After selection or when the application asks.", "Small fee",
        ["police", "criminal", "character certificate", "non-criminal"],
    ),
    ChecklistItem(
        "medical", "Medical certificate / health form",
        "Some programmes (Hungary, Korea, China, Japan) require a doctor-signed form.",
        "Use the programme's own form; get it signed by a registered doctor/hospital.",
        "When the application asks.", "Doctor/lab fees",
        ["medical", "health", "physical examination"],
    ),
    ChecklistItem(
        "family_docs", "Family Registration Certificate & income documents",
        "Needed for need-based scholarships (e.g. Italy's regional DSU scholarships).",
        "FRC from NADRA; income/property documents legalised as the programme requires.",
        "Start early for Italy (legalisation takes time).", "NADRA and attestation fees",
        ["family", "income", "isee", "financial", "frc"],
    ),
    ChecklistItem(
        "nomination", "Nomination (HEC / embassy)",
        "Some government scholarships (Stipendium Hungaricum, Commonwealth) need HEC nomination.",
        "Follow the HEC scholarships page and apply for nomination alongside the main application.",
        "Same window as the scholarship.", "Usually free",
        ["nomination", "nominat"],
    ),
]


def classify_document(text: str) -> ChecklistItem | None:
    low = text.lower()
    for item in BASE_CHECKLIST:
        if any(k in low for k in item.keywords):
            return item
    return None


def document_demand(matches: list[MatchResult]) -> tuple[list[DocumentDemand], dict[str, list[str]]]:
    """For your active matches: which checklist documents are needed and by whom.

    Returns (demand per checklist item in checklist order, other documents -> titles).
    """
    demand = {item.key: DocumentDemand(item) for item in BASE_CHECKLIST}
    other: dict[str, list[str]] = {}
    for result in matches:
        opp = result.opportunity
        for doc in opp.required_documents:
            item = classify_document(doc)
            if item is None:
                other.setdefault(doc, []).append(opp.title)
            elif opp.title not in demand[item.key].needed_by:
                demand[item.key].needed_by.append(opp.title)
    return list(demand.values()), other

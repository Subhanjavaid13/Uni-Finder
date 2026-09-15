"""Builds the weekly email (HTML + plain text)."""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .checklist import DocumentDemand
from .matcher import days_until
from .models import MatchResult, Opportunity

COLORS = {"strong": "#16a34a", "possible": "#d97706", "excluded": "#9ca3af"}
TRACK_TITLES = {
    "no_ielts": "No IELTS needed (MOI letter accepted)",
    "ielts": "IELTS / TOEFL required",
    "unknown": "English requirement not stated yet",
}


@dataclass
class Reminder:
    result: MatchResult
    days_left: int
    threshold: int


@dataclass
class ReportData:
    today: date
    new_results: list[MatchResult]
    statuses: dict[str, str]
    reminders: list[Reminder]
    opening_soon: list[MatchResult]
    active: list[MatchResult]
    later: list[MatchResult]
    demand: list[DocumentDemand]
    other_docs: dict[str, list[str]]
    stats: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    max_items: int = 15


def _e(value: Any) -> str:
    return html.escape(str(value), quote=True)


def fmt_date(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        return date.fromisoformat(iso).strftime("%d %b %Y")
    except ValueError:
        return iso


def deadline_text(opp: Opportunity, today: date) -> str:
    if opp.deadline:
        left = days_until(opp.deadline, today)
        text = fmt_date(opp.deadline)
        if opp.deadline_is_estimate:
            text += " (estimate - confirm)"
        if left is not None and left >= 0:
            text += f" - {left} days left"
        return text
    if opp.typical_window:
        return f"Not announced yet. Usually: {opp.typical_window}"
    return "Not stated - check the website"


def fee_text(opp: Opportunity) -> str:
    amount = f" ({opp.application_fee_amount})" if opp.application_fee_amount else ""
    return {
        "none": "Free to apply",
        "required": f"Application fee required{amount}",
        "varies": f"Varies{amount}",
    }.get(opp.application_fee, "Not stated - check")


def english_text(result: MatchResult) -> str:
    opp = result.opportunity
    base = TRACK_TITLES[result.english_track]
    return f"{base}. {opp.english_notes}" if opp.english_notes else base


def funding_badges(opp: Opportunity) -> list[tuple[str, bool | None]]:
    return [("Tuition", opp.covers_tuition), ("Stipend", opp.stipend), ("Housing", opp.housing),
            ("Travel", opp.travel), ("Insurance", opp.insurance)]


def build_subject(data: ReportData) -> str:
    parts = []
    if data.new_results:
        parts.append(f"{len(data.new_results)} new/updated match{'es' if len(data.new_results) != 1 else ''}")
    if data.reminders:
        parts.append(f"{len(data.reminders)} deadline alert{'s' if len(data.reminders) != 1 else ''}")
    summary = ", ".join(parts) if parts else "no new matches this week"
    return f"ScholarRadar: {summary} ({data.today.strftime('%d %b %Y')})"


# ---- HTML ------------------------------------------------------------------------

def _badge_html(label: str, value: bool | None) -> str:
    if value is True:
        style, mark = "background:#dcfce7;color:#166534", "&#10003;"
    elif value is False:
        style, mark = "background:#fee2e2;color:#991b1b", "&#10007;"
    else:
        style, mark = "background:#f3f4f6;color:#4b5563", "?"
    return (f'<span style="{style};border-radius:10px;padding:2px 8px;margin-right:4px;'
            f'font-size:12px;display:inline-block">{mark} {_e(label)}</span>')


def _card_html(result: MatchResult, today: date, status: str | None = None) -> str:
    opp = result.opportunity
    color = COLORS[result.verdict]
    tag = ""
    if status in ("new", "updated"):
        tag = (f' <span style="background:#2563eb;color:#fff;border-radius:4px;padding:1px 6px;'
               f'font-size:11px">{status.upper()}</span>')
    where = " &middot; ".join(_e(x) for x in (opp.country, opp.university or opp.provider) if x)
    rows = [
        ("Deadline", deadline_text(opp, today)),
        ("Application fee", fee_text(opp)),
        ("English", english_text(result)),
        ("Work experience", f"{opp.work_experience_years:g} years" if opp.work_experience_years else "Not required / not stated"),
    ]
    if opp.intake:
        rows.append(("Intake", opp.intake))
    if opp.min_gpa:
        rows.append(("Minimum GPA", opp.min_gpa))
    table = "".join(
        f'<tr><td style="color:#6b7280;padding:2px 10px 2px 0;vertical-align:top;white-space:nowrap">{_e(k)}</td>'
        f'<td style="padding:2px 0">{_e(v)}</td></tr>' for k, v in rows
    )
    parts = [
        f'<div style="border:1px solid #e5e7eb;border-left:5px solid {color};border-radius:8px;'
        f'padding:14px 16px;margin:12px 0;background:#fff">',
        f'<div style="font-size:16px;font-weight:600"><a href="{_e(opp.url)}" style="color:#111827;'
        f'text-decoration:none">{_e(opp.title)}</a>{tag}</div>',
        f'<div style="color:#6b7280;font-size:13px;margin:2px 0 8px">{where} &middot; '
        f'match score {result.score}/100 &middot; <b style="color:{color}">{result.verdict.upper()}</b></div>',
        '<div style="margin-bottom:8px">' + "".join(_badge_html(l, v) for l, v in funding_badges(opp)) + "</div>",
        f'<table style="font-size:13px;border-collapse:collapse">{table}</table>',
    ]
    if opp.summary:
        parts.append(f'<p style="font-size:13px;color:#374151;margin:8px 0">{_e(opp.summary)}</p>')
    if result.reasons:
        parts.append('<div style="font-size:13px;margin:6px 0"><b>Why it fits you:</b> '
                     + " &middot; ".join(_e(r) for r in result.reasons) + "</div>")
    if result.to_verify:
        parts.append('<div style="font-size:13px;margin:6px 0;color:#92400e"><b>Verify on the website:</b> '
                     + "; ".join(_e(v) for v in result.to_verify) + "</div>")
    if opp.required_documents:
        docs = "".join(f"<li>{_e(d)}</li>" for d in opp.required_documents[:12])
        parts.append(f'<div style="font-size:13px;margin:6px 0"><b>Documents needed:</b>'
                     f'<ul style="margin:4px 0 0 18px;padding:0">{docs}</ul></div>')
    if opp.evidence:
        parts.append(f'<div style="font-size:12px;color:#6b7280;margin:6px 0">Source quote: '
                     f'&ldquo;{_e(opp.evidence)}&rdquo;</div>')
    parts.append(f'<a href="{_e(opp.url)}" style="display:inline-block;margin-top:6px;background:#111827;'
                 f'color:#fff;padding:6px 12px;border-radius:6px;font-size:13px;text-decoration:none">'
                 f'Open official page</a></div>')
    return "".join(parts)


def _section_html(title: str, body: str, subtitle: str = "") -> str:
    sub = f'<div style="color:#6b7280;font-size:13px">{_e(subtitle)}</div>' if subtitle else ""
    return (f'<h2 style="font-size:18px;margin:28px 0 4px;border-bottom:2px solid #e5e7eb;'
            f'padding-bottom:6px">{_e(title)}</h2>{sub}{body}')


def build_html(data: ReportData) -> str:
    today, limit = data.today, data.max_items
    out: list[str] = []

    strong = sum(r.verdict == "strong" for r in data.active)
    out.append(
        f'<p style="font-size:15px">This week: <b>{len(data.new_results)}</b> new or updated matches, '
        f'<b>{len(data.reminders)}</b> deadline alerts. You are tracking <b>{len(data.active)}</b> '
        f'scholarships ({strong} strong matches).</p>'
    )

    if data.reminders:
        body = ""
        for rem in data.reminders[:limit]:
            opp = rem.result.opportunity
            est = " (estimated)" if opp.deadline_is_estimate else ""
            body += (f'<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:10px 14px;'
                     f'margin:8px 0"><b>{rem.days_left} days left</b>{est} &middot; '
                     f'<a href="{_e(opp.url)}">{_e(opp.title)}</a> &middot; deadline {_e(fmt_date(opp.deadline))}</div>')
        out.append(_section_html("Deadline alerts", body))

    for track in ("no_ielts", "ielts", "unknown"):
        items = [r for r in data.new_results if r.english_track == track]
        if items:
            body = "".join(_card_html(r, today, data.statuses.get(r.opportunity.id)) for r in items[:limit])
            more = f"<p>...and {len(items) - limit} more.</p>" if len(items) > limit else ""
            out.append(_section_html(f"New & updated: {TRACK_TITLES[track]}", body + more))

    if data.opening_soon:
        body = "".join(
            f'<li><a href="{_e(r.opportunity.url)}">{_e(r.opportunity.title)}</a> - usually opens around '
            f'{_e(fmt_date(r.opportunity.opens))}. Start preparing documents now.</li>'
            for r in data.opening_soon[:limit]
        )
        out.append(_section_html("Opening soon (next 45 days)", f"<ul>{body}</ul>"))

    if data.active:
        rows = "".join(
            f'<tr style="border-top:1px solid #e5e7eb"><td style="padding:6px"><a href="{_e(r.opportunity.url)}">'
            f'{_e(r.opportunity.title)}</a></td><td style="padding:6px">{_e(r.opportunity.country or "")}</td>'
            f'<td style="padding:6px">{_e(fmt_date(r.opportunity.deadline) or "TBA")}'
            f'{" *" if r.opportunity.deadline_is_estimate and r.opportunity.deadline else ""}</td>'
            f'<td style="padding:6px">{_e({"no_ielts": "No IELTS", "ielts": "IELTS", "unknown": "?"}[r.english_track])}</td>'
            f'<td style="padding:6px;color:{COLORS[r.verdict]}"><b>{r.score}</b></td></tr>'
            for r in data.active[:40]
        )
        table = (f'<table style="font-size:13px;border-collapse:collapse;width:100%"><tr style="text-align:left;'
                 f'color:#6b7280"><th style="padding:6px">Scholarship</th><th style="padding:6px">Country</th>'
                 f'<th style="padding:6px">Deadline</th><th style="padding:6px">English</th>'
                 f'<th style="padding:6px">Score</th></tr>{rows}</table>'
                 f'<div style="font-size:12px;color:#6b7280">* estimated from previous years</div>')
        out.append(_section_html("All your current matches", table))

    rows = ""
    for d in data.demand:
        count = len(d.needed_by)
        track = " (IELTS track)" if d.item.track == "ielts" else ""
        needed = f"{count} of your matches" if count else "recommended"
        rows += (f'<tr style="border-top:1px solid #e5e7eb;vertical-align:top"><td style="padding:6px">'
                 f'<b>{_e(d.item.name)}</b>{_e(track)}<br><span style="color:#6b7280">{_e(d.item.why)}</span></td>'
                 f'<td style="padding:6px;white-space:nowrap">{_e(needed)}</td>'
                 f'<td style="padding:6px">{_e(d.item.how)}<br><span style="color:#6b7280">When: {_e(d.item.when)} '
                 f'&middot; Cost: {_e(d.item.cost)}</span></td></tr>')
    other = ""
    if data.other_docs:
        other = "<p style='font-size:13px'><b>Other documents mentioned:</b> " + "; ".join(
            f"{_e(doc)} ({len(titles)})" for doc, titles in list(data.other_docs.items())[:15]) + "</p>"
    out.append(_section_html(
        "Documents you need",
        f'<table style="font-size:13px;border-collapse:collapse;width:100%">{rows}</table>{other}',
        "Prepare these once and reuse them for every application.",
    ))

    if data.later:
        body = "".join(f'<li><a href="{_e(r.opportunity.url)}">{_e(r.opportunity.title)}</a> - '
                       f'{_e("; ".join(r.exclusions))}</li>' for r in data.later[:limit])
        out.append(_section_html("For later (after you gain work experience)", f"<ul>{body}</ul>"))

    stats = " &middot; ".join(f"{_e(k.replace('_', ' '))}: {_e(v)}" for k, v in data.stats.items())
    errors = ""
    if data.errors:
        errors = ("<details><summary>Sources with problems</summary><ul>"
                  + "".join(f"<li>{_e(e)}</li>" for e in data.errors[:20]) + "</ul></details>")
    out.append(_section_html("Run details", f'<p style="font-size:12px;color:#6b7280">{stats}</p>{errors}'))

    return (
        '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        f'<title>{_e(build_subject(data))}</title></head>'
        '<body style="margin:0;background:#f9fafb;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#111827">'
        '<div style="max-width:720px;margin:0 auto;padding:16px">'
        '<h1 style="font-size:22px;margin:8px 0">ScholarRadar weekly report</h1>'
        f'<div style="color:#6b7280;font-size:13px">{_e(data.today.strftime("%A, %d %B %Y"))}</div>'
        + "".join(out) +
        '<p style="font-size:12px;color:#6b7280;margin-top:28px;border-top:1px solid #e5e7eb;padding-top:10px">'
        'Details are extracted automatically and can be wrong or out of date. Always confirm deadlines, '
        'fees and eligibility on the official website before applying. Never pay an agent for a '
        '"guaranteed" scholarship.</p></div></body></html>'
    )


# ---- plain text ------------------------------------------------------------------

def _card_text(result: MatchResult, today: date, status: str | None) -> str:
    opp = result.opportunity
    tag = f" [{status.upper()}]" if status in ("new", "updated") else ""
    badges = ", ".join(f"{l}: {'yes' if v else 'no' if v is False else '?'}" for l, v in funding_badges(opp))
    lines = [
        f"* {opp.title}{tag}",
        f"  {opp.country or ''} | score {result.score}/100 | {result.verdict.upper()}",
        f"  {badges}",
        f"  Deadline: {deadline_text(opp, today)}",
        f"  Application fee: {fee_text(opp)}",
        f"  English: {english_text(result)}",
    ]
    if result.reasons:
        lines.append("  Why it fits: " + "; ".join(result.reasons))
    if result.to_verify:
        lines.append("  Verify: " + "; ".join(result.to_verify))
    if opp.required_documents:
        lines.append("  Documents: " + "; ".join(opp.required_documents[:12]))
    lines.append(f"  Link: {opp.url}")
    return "\n".join(lines)


def build_text(data: ReportData) -> str:
    today, limit = data.today, data.max_items
    out = [f"ScholarRadar weekly report - {today.strftime('%d %B %Y')}", ""]
    out.append(f"{len(data.new_results)} new/updated matches, {len(data.reminders)} deadline alerts, "
               f"{len(data.active)} scholarships tracked.")
    if data.reminders:
        out += ["", "== DEADLINE ALERTS =="]
        for rem in data.reminders[:limit]:
            opp = rem.result.opportunity
            out.append(f"- {rem.days_left} days left: {opp.title} ({fmt_date(opp.deadline)}) {opp.url}")
    for track in ("no_ielts", "ielts", "unknown"):
        items = [r for r in data.new_results if r.english_track == track]
        if items:
            out += ["", f"== NEW & UPDATED: {TRACK_TITLES[track].upper()} =="]
            out += [_card_text(r, today, data.statuses.get(r.opportunity.id)) for r in items[:limit]]
    if data.opening_soon:
        out += ["", "== OPENING SOON =="]
        out += [f"- {r.opportunity.title}: around {fmt_date(r.opportunity.opens)}" for r in data.opening_soon[:limit]]
    out += ["", "== DOCUMENTS YOU NEED =="]
    for d in data.demand:
        out.append(f"- {d.item.name} ({len(d.needed_by)} matches): {d.item.how}")
    if data.later:
        out += ["", "== FOR LATER =="]
        out += [f"- {r.opportunity.title}: {'; '.join(r.exclusions)}" for r in data.later[:limit]]
    out += ["", "Always confirm details on the official website before applying."]
    return "\n".join(out)


def build_report(data: ReportData) -> tuple[str, str, str]:
    return build_subject(data), build_html(data), build_text(data)

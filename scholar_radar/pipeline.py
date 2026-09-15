"""The weekly agent run: discover -> analyse -> remember -> match -> report -> email."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .checklist import document_demand
from .config import Settings
from .emailer import send_email
from .extract import extract_opportunities
from .fetch import Fetcher
from .llm import BaseLLM, get_llm
from .matcher import days_until, match_all, only_work_experience_blocks
from .models import Candidate, Opportunity
from .report import Reminder, ReportData, build_report
from .seed import load_seed
from .sources import discover_official, discover_rss, discover_search, is_relevant
from .store import State

log = logging.getLogger(__name__)

OPENING_SOON_DAYS = 45


@dataclass
class RunOptions:
    dry_run: bool = False  # build the report but don't email
    use_official: bool = True
    use_rss: bool = True
    use_search: bool = True
    use_ai: bool = True
    max_pages: int = 40  # AI budget per run
    save_state: bool | None = None  # default: save unless dry run


@dataclass
class RunSummary:
    subject: str
    report_path: Path
    email_sent: bool
    stats: dict[str, Any]
    errors: list[str]


def _dedupe(candidates: list[Candidate]) -> list[Candidate]:
    best: dict[str, Candidate] = {}
    for cand in candidates:
        current = best.get(cand.url)
        if current is None or cand.priority > current.priority:
            best[cand.url] = cand
    return sorted(best.values(), key=lambda c: -c.priority)


def run(settings: Settings, options: RunOptions, today: date | None = None,
        fetcher: Fetcher | None = None, llm: BaseLLM | None = None) -> RunSummary:
    today = today or date.today()
    profile = settings.profile
    state = State(settings.state_path)
    fetcher = fetcher or Fetcher()
    if not options.use_ai:
        llm = None
    elif llm is None:
        llm = get_llm()
    log.info("AI extraction: %s", llm.name if llm else "off (keyword mode)")

    statuses: dict[str, str] = {}
    errors: list[str] = []
    stats: dict[str, Any] = {"date": today.isoformat(), "ai": llm.name if llm else "keywords"}

    def remember(opp: Opportunity) -> None:
        status = state.upsert(opp, today)
        if status != "unchanged" and statuses.get(opp.id) != "new":
            statuses[opp.id] = status

    # 1. Seed database (with any facts verified from official pages applied)
    seeds = load_seed(settings.seed_path)
    seed_by_key = {s.seed_key: s for s in seeds if s.seed_key}
    for seed in seeds:
        remember(state.apply_seed_overrides(seed))
    stats["seed_scholarships"] = len(seeds)

    # 2. Discovery
    candidates: list[Candidate] = []
    if options.use_official:
        found, errs = discover_official(settings.sources.official_pages, fetcher, state, today)
        candidates += found
        errors += errs
        stats["official_pages_changed"] = sum(c.priority == 10 for c in found)
    if options.use_rss:
        found, errs = discover_rss(settings.sources.rss_feeds, fetcher, state, today,
                                   settings.sources.relevance_keywords or None)
        candidates += found
        errors += errs
        stats["rss_new_posts"] = len(found)
    if options.use_search:
        found, errs = discover_search(settings.sources.search, profile, state, today)
        candidates += found
        errors += errs
        stats["search_new_pages"] = len(found)

    queue = _dedupe(candidates)
    selected = queue[: options.max_pages]
    stats["deferred_to_next_run"] = len(queue) - len(selected)

    # 3. Analyse pages
    analysed = skipped = 0
    for cand in selected:
        if cand.text is None:
            page = fetcher.fetch_page(cand.url)
            if page is not None:
                cand.text = page.text
                cand.title = cand.title or page.title
        blob = f"{cand.title} {cand.snippet} {(cand.text or '')[:8000]}"
        if cand.source != "official" and not is_relevant(blob, settings.sources.relevance_keywords or None):
            state.mark_seen(cand.url, today)
            skipped += 1
            continue

        found_opps = extract_opportunities(cand, llm, today)
        analysed += 1
        if cand.seed_key in seed_by_key and len(found_opps) == 1:
            if state.record_seed_findings(cand.seed_key, found_opps[0], today):
                remember(state.apply_seed_overrides(seed_by_key[cand.seed_key]))
        else:
            for opp in found_opps:
                opp.seed_key = None  # a separate programme found on the page
                remember(opp)
        state.mark_seen(cand.url, today)
    stats["pages_analysed"] = analysed
    stats["pages_skipped_irrelevant"] = skipped

    # 4. Match everything we know against the profile
    state.remove_expired(today)
    results = match_all(state.all_opportunities(), profile, today)
    active = [r for r in results if r.verdict != "excluded"]
    later = [r for r in results if only_work_experience_blocks(r)]

    thresholds = [int(t) for t in profile.email.get("reminder_days", [30, 14, 7, 3])]
    reminders = []
    for r in active:
        left = days_until(r.opportunity.deadline, today)
        if left is None:
            continue
        threshold = state.reminder_due(r.opportunity.id, left, thresholds)
        if threshold is not None:
            reminders.append(Reminder(r, left, threshold))
    reminders.sort(key=lambda rem: rem.days_left)

    opening_soon = [r for r in active
                    if (d := days_until(r.opportunity.opens, today)) is not None and 0 <= d <= OPENING_SOON_DAYS]
    new_results = [r for r in active if r.opportunity.id in statuses]
    demand, other_docs = document_demand(active)
    stats["new_or_updated"] = len(new_results)
    stats["active_matches"] = len(active)
    stats["ai_calls"] = llm.calls if llm else 0

    # 5. Report
    data = ReportData(
        today=today, new_results=new_results, statuses=statuses, reminders=reminders,
        opening_soon=opening_soon, active=active, later=later, demand=demand,
        other_docs=other_docs, stats=stats, errors=errors,
        max_items=int(profile.email.get("max_items_per_section", 15)),
    )
    subject, html_body, text_body = build_report(data)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = settings.output_dir / "latest_report.html"
    report_path.write_text(html_body, encoding="utf-8")
    (settings.output_dir / "latest_report.txt").write_text(text_body, encoding="utf-8")

    # 6. Email (if sending fails, state is NOT saved so nothing is lost next run)
    email_sent = False
    has_news = bool(new_results or reminders)
    if not options.dry_run and (has_news or profile.email.get("send_when_empty", True)):
        send_email(subject, html_body, text_body)
        email_sent = True
        for rem in reminders:
            state.mark_reminder(rem.result.opportunity.id, rem.threshold, thresholds)

    save = options.save_state if options.save_state is not None else not options.dry_run
    if save:
        state.prune_seen(today)
        state.record_run({**stats, "email_sent": email_sent, "errors": len(errors)})
        state.save()

    return RunSummary(subject=subject, report_path=report_path, email_sent=email_sent,
                      stats=stats, errors=errors)

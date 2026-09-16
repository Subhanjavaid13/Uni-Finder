"""Command line interface: `python -m scholar_radar <command>`."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from . import __version__
from .checklist import BASE_CHECKLIST
from .config import load_settings
from .emailer import EmailError, send_email
from .fetch import Fetcher
from .llm import LLMError
from .matcher import match_all
from .pipeline import RunOptions, run
from .seed import load_seed
from .sources.search import build_queries
from .store import State


def cmd_run(args: argparse.Namespace) -> int:
    settings = load_settings()
    options = RunOptions(
        dry_run=args.dry_run, use_official=not args.no_official, use_rss=not args.no_rss,
        use_search=not args.no_search, use_ai=not args.no_ai, max_pages=args.max_pages,
        save_state=True if args.save_state else None,
    )
    try:
        summary = run(settings, options)
    except (EmailError, LLMError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(summary.subject)
    for key, value in summary.stats.items():
        print(f"  {key}: {value}")
    if summary.errors:
        print(f"  {len(summary.errors)} source problems (see report 'Run details')")
    print(f"Report: {summary.report_path}")
    print("Email sent." if summary.email_sent else "Email not sent (dry run or nothing to send).")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    settings = load_settings()
    state = State(settings.state_path)
    opps = state.all_opportunities() or load_seed(settings.seed_path)
    results = match_all(opps, settings.profile, date.today())
    if not args.all:
        results = [r for r in results if r.verdict != "excluded"]
    track = {"no_ielts": "No IELTS", "ielts": "IELTS", "unknown": "?"}
    print(f"{'VERDICT':9} {'SCORE':5} {'DEADLINE':11} {'ENGLISH':8} {'COUNTRY':20} TITLE")
    for r in results:
        o = r.opportunity
        deadline = (o.deadline or "TBA") + ("*" if o.deadline_is_estimate and o.deadline else "")
        print(f"{r.verdict:9} {r.score:<5} {deadline:11} {track[r.english_track]:8} "
              f"{(o.country or '')[:20]:20} {o.title[:60]}")
        if args.all and r.exclusions:
            print(f"{'':36}excluded: {'; '.join(r.exclusions)}")
    print("\n* = estimated from previous years")
    return 0


def cmd_check_sources(_: argparse.Namespace) -> int:
    import feedparser

    settings = load_settings()
    fetcher = Fetcher(per_host_delay=0.5)
    failures = 0
    print("Official pages:")
    for cfg in settings.sources.official_pages:
        page = fetcher.fetch_page(cfg["url"], verify=cfg.get("verify_ssl", True))
        ok = page is not None and len(page.text) > 200
        failures += not ok
        detail = f"{len(page.text)} chars" if page else "unreachable / blocked"
        print(f"  [{'OK' if ok else 'FAIL'}] {cfg['name']}: {detail}")
    print("RSS feeds:")
    for feed in settings.sources.rss_feeds:
        resp = fetcher.get(feed["url"])
        entries = len(feedparser.parse(resp.content).entries) if resp is not None else 0
        ok = entries > 0
        failures += not ok
        print(f"  [{'OK' if ok else 'FAIL'}] {feed['name']}: {entries} entries")
    print(f"\n{failures} source(s) failed. Failed sources are skipped during runs; "
          "edit config/sources.yaml to fix or remove them.")
    return 0


def cmd_test_email(_: argparse.Namespace) -> int:
    load_settings()
    try:
        send_email("ScholarRadar test email",
                   "<p>Your ScholarRadar email settings work.</p>",
                   "Your ScholarRadar email settings work.")
    except EmailError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("Test email sent.")
    return 0


def cmd_checklist(_: argparse.Namespace) -> int:
    for i, item in enumerate(BASE_CHECKLIST, 1):
        track = " [only for IELTS-track scholarships]" if item.track == "ielts" else ""
        print(f"{i:2}. {item.name}{track}")
        print(f"    Why:  {item.why}")
        print(f"    How:  {item.how}")
        print(f"    When: {item.when}   Cost: {item.cost}\n")
    return 0


def cmd_queries(_: argparse.Namespace) -> int:
    settings = load_settings()
    for q in build_queries(settings.sources.search, settings.profile, date.today()):
        print(q)
    return 0


def cmd_dashboard(args: argparse.Namespace) -> int:
    import webbrowser
    from pathlib import Path

    from .dashboard import build_dashboard

    settings = load_settings()
    out = Path(args.output) if args.output else settings.output_dir / "dashboard.html"
    stats = build_dashboard(settings, out)
    print(f"Dashboard: {out}")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


def cmd_visa(args: argparse.Namespace) -> int:
    from .visa import load_visa_money, lookup

    settings = load_settings()
    table = load_visa_money(settings.visa_path) if settings.visa_path else {}
    if not table:
        print("No config/visa_money.yaml found.", file=sys.stderr)
        return 1
    if args.country:
        info = lookup(args.country, table)
        if info is None:
            print(f"No visa money info for '{args.country}'.", file=sys.stderr)
            return 1
        entries = [info]
    else:
        entries = sorted(table.values(), key=lambda i: i.country)

    for info in entries:
        print(f"\n== {info.country}")
        print(f"   Visa:              {info.visa_type or '?'}")
        print(f"   Money to show:     {info.proof_of_funds or '?'}")
        print(f"   Bank statement:    {info.bank_statement or '?'}")
        print(f"   Scholarship letter accepted: {info.scholarship_letter_accepted}")
        if info.visa_fee:
            print(f"   Visa fee:          {info.visa_fee}")
        if info.notes:
            print(f"   How to apply:      {info.notes}")
        if info.source:
            print(f"   Source:            {info.source}")
    print("\nAlways confirm on the embassy checklist - amounts change every year.")
    return 0


def cmd_excel(args: argparse.Namespace) -> int:
    from pathlib import Path

    from .config import ROOT
    from .research_excel import build_workbook

    raw_dir = ROOT / "research" / "raw"
    if not any(raw_dir.glob("*.json")):
        print(f"No research files found in {raw_dir}", file=sys.stderr)
        return 1
    out = Path(args.output) if args.output else ROOT / "Europe_CS_AI_Masters_Scholarships.xlsx"
    stats = build_workbook(raw_dir, out)
    print(f"Excel file: {out}")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(prog="scholar_radar",
                                     description="Find fully funded AI/CS master's scholarships.")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("-v", "--verbose", action="store_true", help="show detailed logs")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="run the weekly research and email the report")
    p_run.add_argument("--dry-run", action="store_true", help="don't send email or save memory")
    p_run.add_argument("--save-state", action="store_true", help="save memory even in a dry run")
    p_run.add_argument("--no-official", action="store_true", help="skip official pages")
    p_run.add_argument("--no-rss", action="store_true", help="skip RSS feeds")
    p_run.add_argument("--no-search", action="store_true", help="skip web search")
    p_run.add_argument("--no-ai", action="store_true", help="keyword extraction only")
    p_run.add_argument("--max-pages", type=int, default=40, help="max pages to analyse (default 40)")
    p_run.set_defaults(func=cmd_run)

    p_list = sub.add_parser("list", help="show your current matches")
    p_list.add_argument("--all", action="store_true", help="include excluded scholarships and why")
    p_list.set_defaults(func=cmd_list)

    sub.add_parser("check-sources", help="test that every source URL works").set_defaults(func=cmd_check_sources)
    sub.add_parser("test-email", help="send a test email").set_defaults(func=cmd_test_email)
    sub.add_parser("checklist", help="print the documents you need").set_defaults(func=cmd_checklist)
    sub.add_parser("queries", help="show this week's search queries").set_defaults(func=cmd_queries)

    p_dash = sub.add_parser("dashboard", help="build the HTML dashboard to browse everything")
    p_dash.add_argument("--open", action="store_true", help="open it in your browser")
    p_dash.add_argument("--output", help="output .html path")
    p_dash.set_defaults(func=cmd_dashboard)

    p_visa = sub.add_parser("visa", help="bank statement / proof of funds rules per country")
    p_visa.add_argument("country", nargs="?", help="e.g. Italy, Germany, UK")
    p_visa.set_defaults(func=cmd_visa)

    p_excel = sub.add_parser("excel", help="build the Excel file from research/raw/*.json")
    p_excel.add_argument("--output", help="output .xlsx path")
    p_excel.set_defaults(func=cmd_excel)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

"""Builds a single self-contained HTML dashboard for browsing everything by hand."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

from .checklist import BASE_CHECKLIST
from .config import Settings
from .matcher import days_until, match_all
from .models import MatchResult
from .report import deadline_text, english_text, fee_text, money_text
from .research_excel import dedupe, load_research, prepare_program, to_bool
from .seed import load_seed
from .store import State
from .visa import load_visa_money, lookup

log = logging.getLogger(__name__)

PROGRAM_FIELDS = (
    "country", "region", "city", "university", "university_type", "university_url",
    "program_name", "field", "program_url", "language", "duration", "intake",
    "application_window", "deadline", "deadline_status", "application_portal",
    "application_fee", "application_fee_free", "tuition_non_eu", "academic_requirements",
    "min_gpa", "english_requirement", "ielts_required", "moi_accepted", "entrance_test",
    "other_requirements", "documents_text", "scholarships_text", "fully_funded_possible",
    "housing_support", "visa_support", "sources_text", "confidence", "notes", "fit", "score",
)


def _find_row(result: MatchResult, today: date, visa_table: dict) -> dict[str, Any]:
    opp = result.opportunity
    left = days_until(opp.deadline, today)
    return {
        "title": opp.title,
        "url": opp.url,
        "country": opp.country or "",
        "provider": opp.provider or opp.university or "",
        "verdict": result.verdict,
        "score": result.score,
        "english_track": result.english_track,
        "english": english_text(result),
        "deadline": opp.deadline or "",
        "deadline_text": deadline_text(opp, today),
        "days_left": left if left is not None else "",
        "fee": fee_text(opp),
        "fee_free": opp.application_fee == "none",
        "funding": opp.funding_level,
        "stipend": opp.stipend,
        "housing": opp.housing,
        "money": money_text(result, visa_table),
        "reasons": result.reasons,
        "verify": result.to_verify,
        "exclusions": result.exclusions,
        "documents": opp.required_documents,
        "summary": opp.summary,
        "source": opp.source,
    }


def collect_data(settings: Settings, today: date | None = None,
                 research_dir: Path | None = None) -> dict[str, Any]:
    today = today or date.today()
    visa_table = load_visa_money(settings.visa_path) if settings.visa_path else {}

    research_dir = research_dir if research_dir is not None else settings.seed_path.parent.parent / "research" / "raw"
    programs: list[dict[str, Any]] = []
    if research_dir.exists():
        raw, _, _, _ = load_research(research_dir)
        for source in dedupe(raw, ("university", "program_name")):
            prepared = prepare_program(source)
            row = {k: prepared.get(k) for k in PROGRAM_FIELDS}
            # prepare_program renders these as "Yes"/"No" for Excel; the filters need booleans
            for flag in ("application_fee_free", "moi_accepted", "ielts_required"):
                row[flag] = to_bool(source.get(flag))
            programs.append(row)
    programs.sort(key=lambda r: (-(r.get("score") or 0), str(r.get("country")), str(r.get("city"))))

    state = State(settings.state_path)
    opportunities = state.all_opportunities() or load_seed(settings.seed_path)
    results = match_all(opportunities, settings.profile, today)
    finds = [_find_row(r, today, visa_table) for r in results]

    visa = [
        {"country": i.country, "visa_type": i.visa_type, "proof_of_funds": i.proof_of_funds,
         "bank_statement": i.bank_statement, "scholarship_letter": i.scholarship_letter_accepted,
         "visa_fee": i.visa_fee, "notes": i.notes, "source": i.source}
        for i in sorted(visa_table.values(), key=lambda i: i.country)
    ]
    # Which of your matches sit in each country, so the visa tab is personal
    for entry in visa:
        entry["matches"] = sum(
            1 for r in results if r.verdict != "excluded"
            and (info := lookup(r.opportunity.country, visa_table)) and info.country == entry["country"]
        )

    documents = [
        {"name": i.name, "why": i.why, "how": i.how, "when": i.when, "cost": i.cost,
         "track": i.track}
        for i in BASE_CHECKLIST
    ]
    profile = settings.profile
    return {
        "generated": today.isoformat(),
        "profile": {
            "cgpa": profile.cgpa, "fields": profile.fields,
            "work_experience_years": profile.work_experience_years,
            "ielts": profile.english.get("ielts_score"),
        },
        "programs": programs,
        "finds": finds,
        "visa": visa,
        "documents": documents,
    }


def build_dashboard(settings: Settings, out_path: Path, today: date | None = None,
                    research_dir: Path | None = None) -> dict[str, int]:
    data = collect_data(settings, today, research_dir)
    # "</script>" inside the data would close the tag early
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.replace("__DATA__", payload)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return {"programmes": len(data["programs"]), "weekly_finds": len(data["finds"]),
            "countries_with_visa_info": len(data["visa"])}


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ScholarRadar - master's, scholarships and visas</title>
<style>
/* Light, print-inspired palette: warm paper, deep navy ink, emerald + copper accents. */
:root{
  color-scheme: light;
  --paper:#faf7f2; --surface:#ffffff; --surface-2:#f3efe8; --zebra:#fcfaf6;
  --ink:#17243b; --ink-2:#3d4a60; --muted:#6c7787;
  --line:#e6dfd3; --line-2:#efe9de;
  --primary:#0f5c4e; --primary-2:#0b463c; --primary-soft:#e4f0eb;
  --copper:#a9632f; --copper-soft:#fbeee1;
  --rose:#9a3b3b; --rose-soft:#f9e9e7;
  --shadow:0 1px 2px rgba(23,36,59,.05), 0 10px 26px -18px rgba(23,36,59,.45);
  --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,"Times New Roman",serif;
  --sans:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 var(--sans);
  background-image:radial-gradient(1200px 400px at 50% -220px, #fff 0%, rgba(255,255,255,0) 70%)}
.wrap{max-width:1200px;margin:0 auto;padding:22px 16px 56px}
a{color:var(--primary)}
a:hover{color:var(--primary-2)}
:focus-visible{outline:2px solid var(--primary);outline-offset:2px;border-radius:6px}

/* Masthead */
.masthead{display:flex;align-items:flex-start;gap:14px;border-bottom:2px solid var(--ink);
  padding-bottom:14px;margin-bottom:16px}
.mark{flex:none;width:42px;height:42px;border-radius:12px;background:var(--primary);color:#fff;
  display:grid;place-items:center;font:600 19px/1 var(--serif);letter-spacing:.5px;
  box-shadow:var(--shadow)}
h1{font:600 25px/1.15 var(--serif);margin:2px 0 4px;letter-spacing:.2px}
.tagline{color:var(--muted);font-size:13px}
.stats{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
.stat{font-size:12.5px;color:var(--ink-2);background:var(--surface);border:1px solid var(--line);
  border-radius:999px;padding:4px 11px}
.stat b{font:600 13px var(--sans);color:var(--primary)}
.stat.updated{background:transparent;border-style:dashed;color:var(--muted)}

/* Tabs */
.tabs{display:flex;gap:2px;flex-wrap:wrap;border-bottom:1px solid var(--line);margin:18px 0 14px}
.tab{appearance:none;border:0;background:none;padding:10px 14px;cursor:pointer;color:var(--muted);
  font:500 14px var(--sans);border-bottom:2px solid transparent;margin-bottom:-1px}
.tab:hover{color:var(--ink)}
.tab[aria-selected="true"]{color:var(--primary);border-bottom-color:var(--primary);font-weight:650}

/* Filters */
.filters{display:flex;gap:9px;flex-wrap:wrap;align-items:center;background:var(--surface);
  border:1px solid var(--line);border-radius:14px;padding:11px 12px;margin-bottom:14px;
  box-shadow:var(--shadow);position:sticky;top:10px;z-index:5}
input,select{font:14px var(--sans);color:var(--ink);background:var(--surface);
  border:1px solid var(--line);border-radius:9px;padding:8px 10px}
input:hover,select:hover{border-color:#d8cfbe}
input[type=search]{flex:1 1 250px;min-width:170px}
select{cursor:pointer}
label.check{display:flex;align-items:center;gap:7px;font-size:13.5px;color:var(--ink-2);cursor:pointer;
  background:var(--surface-2);border-radius:9px;padding:7px 11px}
input[type=checkbox]{accent-color:var(--primary);width:15px;height:15px;padding:0}
.count{color:var(--muted);font-size:12.5px;margin:2px 2px 12px;text-transform:uppercase;
  letter-spacing:.07em}

/* Cards */
.grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));
  align-items:start}
.card{background:var(--surface);border:1px solid var(--line);border-left:4px solid var(--line-2);
  border-radius:14px;padding:15px 16px;box-shadow:var(--shadow);transition:transform .12s ease,
  box-shadow .12s ease}
.card:hover{transform:translateY(-2px);box-shadow:0 2px 4px rgba(23,36,59,.06),0 18px 36px -22px rgba(23,36,59,.5)}
.card.top{border-left-color:var(--primary)}
.card.good{border-left-color:var(--copper)}
.card.check{border-left-color:var(--line)}
.card.excluded{border-left-color:var(--rose);background:#fdfbf9}
.card h3{font:600 16.5px/1.3 var(--serif);margin:0 0 3px}
.card h3 a{color:var(--ink);text-decoration:none}
.card h3 a:hover{color:var(--primary);text-decoration:underline;text-underline-offset:3px}
.where{color:var(--muted);font-size:12.8px;margin-bottom:10px}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}
.chip{font:500 11.5px var(--sans);padding:3px 9px;border-radius:7px;background:var(--surface-2);
  color:var(--ink-2);border:1px solid transparent}
.chip.ok{background:var(--primary-soft);color:var(--primary-2);border-color:#cfe3db}
.chip.mid{background:var(--copper-soft);color:var(--copper);border-color:#f0dcc6}
.chip.no{background:var(--rose-soft);color:var(--rose);border-color:#f0d4d1}
.kv{font-size:13.2px;margin:5px 0;color:var(--ink-2)}
.kv b{color:var(--muted);font-weight:600;font-size:11.5px;text-transform:uppercase;
  letter-spacing:.06em}
details{margin-top:10px;border-top:1px dashed var(--line);padding-top:8px}
summary{cursor:pointer;color:var(--primary);font:500 13px var(--sans);list-style:none}
summary::-webkit-details-marker{display:none}
summary::before{content:"+ ";font-weight:700}
details[open] summary::before{content:"- "}

/* Tables */
table{width:100%;border-collapse:separate;border-spacing:0;background:var(--surface);
  border:1px solid var(--line);border-radius:14px;overflow:hidden;font-size:13.4px;
  box-shadow:var(--shadow)}
th,td{text-align:left;padding:11px 12px;border-top:1px solid var(--line-2);vertical-align:top}
th{background:var(--surface-2);color:var(--ink);border-top:none;position:sticky;top:0;
  font:600 11.5px var(--sans);text-transform:uppercase;letter-spacing:.07em}
tr:nth-child(even) td{background:var(--zebra)}
td .sub{color:var(--muted);font-size:12px;margin-top:2px}

.empty{color:var(--muted);padding:34px;text-align:center;background:var(--surface);
  border:1px dashed var(--line);border-radius:14px}
.note{background:var(--copper-soft);color:#7d4a22;border-left:3px solid var(--copper);
  border-radius:0 10px 10px 0;padding:11px 14px;font-size:13px;margin:0 0 14px}
@media (max-width:620px){
  .wrap{padding:18px 16px 40px}
  .grid{grid-template-columns:1fr}
  .filters{position:static}
  h1{font-size:22px}
}
</style>
</head>
<body>
<div class="wrap">
  <header class="masthead">
    <div class="mark" aria-hidden="true">SR</div>
    <div>
      <h1>ScholarRadar</h1>
      <div class="tagline">Fully funded AI &amp; Computer Science master's &mdash; programmes, scholarships, visas</div>
      <div class="stats" id="head"></div>
    </div>
  </header>

  <div class="tabs" role="tablist">
    <button class="tab" data-tab="programs" role="tab">Universities</button>
    <button class="tab" data-tab="finds" role="tab">Weekly finds</button>
    <button class="tab" data-tab="visa" role="tab">Visa &amp; money</button>
    <button class="tab" data-tab="docs" role="tab">Documents</button>
  </div>

  <section id="panel-programs" hidden>
    <div class="filters">
      <input type="search" id="q" placeholder="Search university, city, programme...">
      <select id="country"></select>
      <select id="field"></select>
      <select id="funding">
        <option value="">Any funding</option>
        <option value="yes">Fully funded possible</option>
        <option value="competitive">Competitive award only</option>
        <option value="partial">Partial</option>
      </select>
      <select id="english">
        <option value="">Any English rule</option>
        <option value="moi">MOI accepted</option>
        <option value="noielts">No IELTS needed</option>
        <option value="ielts">IELTS required</option>
      </select>
      <label class="check"><input type="checkbox" id="freefee"> Free to apply</label>
      <select id="sort">
        <option value="score">Best fit first</option>
        <option value="country">Country</option>
        <option value="city">City</option>
        <option value="deadline">Deadline</option>
      </select>
    </div>
    <div class="count" id="count-programs"></div>
    <div class="grid" id="list-programs"></div>
  </section>

  <section id="panel-finds" hidden>
    <div class="filters">
      <input type="search" id="fq" placeholder="Search scholarships...">
      <select id="ftrack">
        <option value="">Any English rule</option>
        <option value="no_ielts">No IELTS (MOI)</option>
        <option value="ielts">IELTS required</option>
        <option value="unknown">Not stated</option>
      </select>
      <label class="check"><input type="checkbox" id="fopen" checked> Hide excluded</label>
    </div>
    <div class="count" id="count-finds"></div>
    <div class="grid" id="list-finds"></div>
  </section>

  <section id="panel-visa" hidden>
    <div class="note">A scholarship award letter replaces the bank statement in most countries.
      Amounts change every year - always confirm on the embassy checklist.</div>
    <div class="filters">
      <input type="search" id="vq" placeholder="Search country...">
      <label class="check"><input type="checkbox" id="vmine" checked> Only countries I have matches in</label>
    </div>
    <div class="count" id="count-visa"></div>
    <div id="list-visa"></div>
  </section>

  <section id="panel-docs" hidden>
    <div class="count">Prepare these once and reuse them for every application.</div>
    <div class="grid" id="list-docs"></div>
  </section>
</div>

<script>
const DATA = __DATA__;
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const yn = (v) => v === true ? "Yes" : v === false ? "No" : "?";

function chip(text, kind){ return `<span class="chip ${kind||""}">${esc(text)}</span>`; }
function kv(label, value){ return value ? `<div class="kv"><b>${esc(label)}:</b> ${esc(value)}</div>` : ""; }

/* ---------- Universities ---------- */
function fillSelect(el, values, allLabel){
  el.innerHTML = `<option value="">${allLabel}</option>` +
    [...new Set(values.filter(Boolean))].sort().map(v => `<option>${esc(v)}</option>`).join("");
}
function programCard(p){
  const cls = (p.fit || "").toLowerCase().replace(" ", "");
  const fundChip = {yes:["Fully funded possible","ok"], competitive:["Competitive award only","mid"],
                    partial:["Partial funding","mid"], no:["No funding found","no"]}[p.fully_funded_possible]
                   || ["Funding unknown",""];
  return `<div class="card ${cls === "topmatch" ? "top" : cls}">
    <h3><a href="${esc(p.program_url || p.university_url || "#")}" target="_blank" rel="noopener">${esc(p.program_name)}</a></h3>
    <div class="where">${esc(p.university)} &middot; ${esc(p.city || "")}${p.city ? ", " : ""}${esc(p.country)}</div>
    <div class="chips">
      ${chip(p.fit + " " + (p.score ?? "") , cls === "topmatch" ? "ok" : cls === "good" ? "mid" : "")}
      ${chip(fundChip[0], fundChip[1])}
      ${chip(p.application_fee_free === true ? "Free to apply" : "Fee: " + (p.application_fee || "?"), p.application_fee_free === true ? "ok" : "")}
      ${chip(p.moi_accepted === true ? "MOI accepted" : p.ielts_required === true ? "IELTS required" : "English: ?", p.moi_accepted === true ? "ok" : p.ielts_required === true ? "mid" : "")}
    </div>
    ${kv("Deadline", (p.deadline || p.application_window || "not stated") + (p.deadline_status === "last_year" ? "  (last year's cycle)" : ""))}
    ${kv("Scholarships", p.scholarships_text)}
    <details><summary>More details</summary>
      ${kv("Tuition (non-EU)", p.tuition_non_eu)}
      ${kv("Entry requirements", p.academic_requirements)}
      ${kv("Minimum GPA", p.min_gpa)}
      ${kv("English requirement", p.english_requirement)}
      ${kv("Entrance test", p.entrance_test)}
      ${kv("Other requirements", p.other_requirements)}
      ${kv("Documents", p.documents_text)}
      ${kv("Apply on", p.application_portal)}
      ${kv("Intake", p.intake)}
      ${kv("Language / duration", [p.language, p.duration].filter(Boolean).join(" / "))}
      ${kv("Housing", p.housing_support)}
      ${kv("Visa support", p.visa_support)}
      ${kv("Notes", p.notes)}
      ${kv("Confidence", p.confidence)}
      ${p.university_url ? `<div class="kv"><a href="${esc(p.university_url)}" target="_blank" rel="noopener">University site</a></div>` : ""}
      ${kv("Sources", p.sources_text)}
    </details>
  </div>`;
}
function renderPrograms(){
  const q = $("q").value.toLowerCase().trim();
  const country = $("country").value, field = $("field").value;
  const funding = $("funding").value, english = $("english").value;
  const freefee = $("freefee").checked, sort = $("sort").value;
  let rows = DATA.programs.filter(p => {
    if (country && p.country !== country) return false;
    if (field && p.field !== field) return false;
    if (funding && p.fully_funded_possible !== funding) return false;
    if (freefee && p.application_fee_free !== true) return false;
    if (english === "moi" && p.moi_accepted !== true) return false;
    if (english === "noielts" && !(p.moi_accepted === true || p.ielts_required === false)) return false;
    if (english === "ielts" && p.ielts_required !== true) return false;
    if (q){
      const hay = [p.program_name, p.university, p.city, p.country, p.field, p.scholarships_text]
        .join(" ").toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  const by = {
    score: (a,b) => (b.score||0) - (a.score||0),
    country: (a,b) => String(a.country).localeCompare(String(b.country)) || String(a.city).localeCompare(String(b.city)),
    city: (a,b) => String(a.city).localeCompare(String(b.city)),
    deadline: (a,b) => String(a.deadline || "9999").localeCompare(String(b.deadline || "9999")),
  }[sort];
  rows.sort(by);
  $("count-programs").textContent = `${rows.length} of ${DATA.programs.length} programmes`;
  $("list-programs").innerHTML = rows.length
    ? rows.map(programCard).join("")
    : `<div class="empty">Nothing matches these filters.</div>`;
}

/* ---------- Weekly finds ---------- */
function findCard(f){
  const cls = f.verdict === "strong" ? "top" : f.verdict === "possible" ? "good" : "excluded";
  const track = {no_ielts:["No IELTS (MOI)","ok"], ielts:["IELTS required","mid"], unknown:["English: ?",""]}[f.english_track];
  return `<div class="card ${cls}">
    <h3><a href="${esc(f.url)}" target="_blank" rel="noopener">${esc(f.title)}</a></h3>
    <div class="where">${esc(f.country || "")}${f.provider ? " &middot; " + esc(f.provider) : ""} &middot; score ${f.score}/100</div>
    <div class="chips">
      ${chip(f.verdict, cls === "top" ? "ok" : cls === "good" ? "mid" : "no")}
      ${chip(track[0], track[1])}
      ${chip(f.fee_free ? "Free to apply" : f.fee, f.fee_free ? "ok" : "")}
      ${f.days_left !== "" ? chip(f.days_left + " days left", f.days_left < 30 ? "mid" : "") : ""}
    </div>
    ${kv("Deadline", f.deadline_text)}
    ${kv("Money for visa", f.money)}
    ${f.reasons.length ? kv("Why it fits", f.reasons.join(" | ")) : ""}
    ${f.verify.length ? kv("Verify", f.verify.join("; ")) : ""}
    ${f.exclusions.length ? kv("Not eligible", f.exclusions.join("; ")) : ""}
    <details><summary>More details</summary>
      ${kv("Summary", f.summary)}
      ${kv("Documents", (f.documents || []).join("; "))}
      ${kv("English", f.english)}
      ${kv("Found via", f.source)}
    </details>
  </div>`;
}
function renderFinds(){
  const q = $("fq").value.toLowerCase().trim(), track = $("ftrack").value, hide = $("fopen").checked;
  const rows = DATA.finds.filter(f => {
    if (hide && f.verdict === "excluded") return false;
    if (track && f.english_track !== track) return false;
    if (q && !(f.title + " " + f.country + " " + f.provider).toLowerCase().includes(q)) return false;
    return true;
  });
  $("count-finds").textContent = `${rows.length} of ${DATA.finds.length} scholarships tracked by the weekly agent`;
  $("list-finds").innerHTML = rows.length ? rows.map(findCard).join("")
    : `<div class="empty">Nothing matches these filters.</div>`;
}

/* ---------- Visa & money ---------- */
function renderVisa(){
  const q = $("vq").value.toLowerCase().trim(), mine = $("vmine").checked;
  const rows = DATA.visa
    .filter(v => (!q || v.country.toLowerCase().includes(q)) && (!mine || v.matches > 0))
    .sort((a,b) => (b.matches||0) - (a.matches||0) || a.country.localeCompare(b.country));
  $("count-visa").textContent = `${rows.length} of ${DATA.visa.length} countries`;
  const flag = {yes:["Yes","ok"], maybe:["Maybe","mid"], unknown:["Not confirmed",""]};
  $("list-visa").innerHTML = `<table><tr><th>Country</th><th>Money to show</th>
    <th>Bank statement?</th><th>Scholarship letter</th><th>Visa fee</th></tr>` +
    rows.map(v => {
      const f = flag[v.scholarship_letter] || flag.unknown;
      return `<tr><td><b>${esc(v.country)}</b>${v.matches ? `<div class="sub">${v.matches} of your matches</div>` : ""}</td>
        <td>${esc(v.proof_of_funds)}</td><td>${esc(v.bank_statement)}</td>
        <td>${chip(f[0], f[1])}</td><td>${esc(v.visa_fee || "?")}</td></tr>`;
    }).join("") + `</table>`;
}

/* ---------- Documents ---------- */
function renderDocs(){
  $("list-docs").innerHTML = DATA.documents.map(d => `<div class="card">
    <h3>${esc(d.name)}</h3>
    ${d.track === "ielts" ? `<div class="chips">${chip("IELTS track only","mid")}</div>` : ""}
    ${kv("Why", d.why)}${kv("How", d.how)}${kv("When", d.when)}${kv("Cost", d.cost)}
  </div>`).join("");
}

/* ---------- wiring ---------- */
function showTab(name){
  document.querySelectorAll(".tab").forEach(b => b.setAttribute("aria-selected", String(b.dataset.tab === name)));
  ["programs","finds","visa","docs"].forEach(t => $("panel-" + t).hidden = (t !== name));
  try { localStorage.setItem("sr-tab", name); } catch (e) {}
}
document.querySelectorAll(".tab").forEach(b => b.onclick = () => showTab(b.dataset.tab));
["q","country","field","funding","english","freefee","sort"].forEach(id => {
  $(id).addEventListener("input", renderPrograms);
});
["fq","ftrack","fopen"].forEach(id => $(id).addEventListener("input", renderFinds));
["vq","vmine"].forEach(id => $(id).addEventListener("input", renderVisa));

fillSelect($("country"), DATA.programs.map(p => p.country), "All countries");
fillSelect($("field"), DATA.programs.map(p => p.field), "All fields");
const strong = DATA.finds.filter(f => f.verdict !== "excluded").length;
const freeFee = DATA.programs.filter(p => p.application_fee_free === true).length;
const noIelts = DATA.programs.filter(p => p.moi_accepted === true || p.ielts_required === false).length;
$("head").innerHTML = [
  [DATA.programs.length, "programmes researched"],
  [strong, "scholarships match you"],
  [freeFee, "free to apply"],
  [noIelts, "no IELTS needed"],
  [DATA.visa.length, "countries with visa rules"],
].map(([n, label]) => `<span class="stat"><b>${n}</b> ${esc(label)}</span>`).join("")
  + `<span class="stat updated">updated ${esc(DATA.generated)}</span>`;
renderPrograms(); renderFinds(); renderVisa(); renderDocs();
let saved = new URLSearchParams(location.search).get("tab") || location.hash.slice(1);
if (!saved) { try { saved = localStorage.getItem("sr-tab"); } catch (e) {} }
showTab(["programs","finds","visa","docs"].includes(saved) ? saved : "programs");
</script>
</body>
</html>
"""

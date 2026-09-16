# ScholarRadar

**An AI agent that searches the world every week for fully funded AI / Computer Science
master's scholarships and emails you the ones that fit your profile.**

It looks for scholarships that cover **tuition + monthly stipend (+ housing when possible)**,
have **no application fee**, and splits the results into **"No IELTS needed (MOI accepted)"**
and **"IELTS/TOEFL required"**. Every email also tells you **which documents you need**, the
deadline, and what to double-check on the official website.

Everything runs on **free tiers**: Gemini API, DuckDuckGo/Bing metasearch, GitHub Actions and Gmail.

---

## What the weekly email contains

| Section | What it shows |
|---|---|
| Deadline alerts | Scholarships closing in 30 / 14 / 7 / 3 days (each alert sent once) |
| New & updated: No IELTS needed | New matches that accept an MOI letter |
| New & updated: IELTS/TOEFL required | New matches that need an English test |
| New & updated: English not stated | Matches where you must check the English rule |
| Opening soon | Recurring scholarships expected to open in the next 45 days |
| All your current matches | One table with deadline, English track and match score |
| Money for your visa | Per country: how much money you must show, whether you need a bank statement, and whether a scholarship letter replaces it |
| Documents you need | Checklist (why, how, when, cost) + how many of your matches need each document |
| For later | Great scholarships you can't apply for *yet* (e.g. need 2 years of work experience) |

## How it works

```
             every Monday (GitHub Actions, free)
                            |
   +------------------------+------------------------+
   |                        |                        |
Official pages          RSS feeds               Web search
(Erasmus Mundus, GKS,   (scholarship news       (rotating fields and
 Turkiye, CSC, KAUST...) sites)                  35 countries each week)
   |  only if the page     |  only new, relevant   |  only new URLs
   |  content changed      |  posts                |
   +------------------------+------------------------+
                            |
             AI extraction (Gemini free tier)
      funding, stipend, housing, fee, deadline, IELTS/MOI,
      work experience, eligibility, required documents
                            |
         Memory (data/state.json): new vs updated vs seen
                            |
       Match against config/profile.yaml -> score + reasons
                            |
               HTML email + output/latest_report.html
```

A **seed database** (`config/scholarships_seed.yaml`) of 15 well-known recurring scholarships
means you get useful reminders from the very first run. When the agent reads the real dates on
an official page, they replace the estimates.

---

## Setup (about 20 minutes)

### 1. Install

```powershell
cd D:\workspace\projects\Uni-Find
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
```

### 2. Get the free keys

1. **Gemini API key** (free): https://aistudio.google.com/apikey
2. **Gmail app password**: turn on 2-Step Verification in your Google Account, then open
   *Security -> 2-Step Verification -> App passwords* and create one (16 characters).
3. *(Optional)* **Tavily** search key for better search results (1,000 free searches/month): https://tavily.com

### 3. Configure

```powershell
copy .env.example .env
```

Fill in `GEMINI_API_KEY`, `SMTP_USER`, `SMTP_PASSWORD` and `EMAIL_TO` in `.env`.
Then edit **`config/profile.yaml`** (CGPA, fields, IELTS plans, work experience).

### 4. Try it

```powershell
python -m scholar_radar test-email            # checks your email settings
python -m scholar_radar run --dry-run -v      # researches, but doesn't email or save
start output\latest_report.html               # open the report in your browser
python -m scholar_radar run                   # the real thing: research + email
```

The first real run takes 10-20 minutes because free AI tiers allow about 10 requests per minute.

---

## Run it automatically every week (free)

1. Create a **private** repository on GitHub and push this project:
   ```powershell
   git remote add origin https://github.com/<you>/scholar-radar.git
   git push -u origin main
   ```
2. On GitHub go to **Settings -> Secrets and variables -> Actions -> New repository secret** and add:
   `GEMINI_API_KEY`, `SMTP_HOST` (`smtp.gmail.com`), `SMTP_PORT` (`587`), `SMTP_USER`,
   `SMTP_PASSWORD`, `EMAIL_TO` and optionally `TAVILY_API_KEY`.
3. Open the **Actions** tab, choose **ScholarRadar weekly** and click **Run workflow** to test.

After that it runs every **Monday at 9:00 AM Pakistan time**. The job commits its memory
(`data/state.json`) back to the repo, so it never emails you the same news twice.

**Alternative (your own PC):** Windows Task Scheduler -> Create Basic Task -> Weekly -> Action
*Start a program* `D:\workspace\projects\Uni-Find\.venv\Scripts\python.exe` with arguments
`-m scholar_radar run` and *Start in* `D:\workspace\projects\Uni-Find`.

---

## Commands

| Command | What it does |
|---|---|
| `python -m scholar_radar run` | Full research run + email |
| `python -m scholar_radar run --dry-run` | Same, but no email and nothing saved |
| `python -m scholar_radar run --no-search --no-rss` | Only official pages + seed (fast) |
| `python -m scholar_radar run --no-ai` | Keyword mode, no API key needed |
| `python -m scholar_radar list` | Show your current matches in the terminal |
| `python -m scholar_radar list --all` | Also show excluded scholarships and why |
| `python -m scholar_radar checklist` | Print the documents checklist |
| `python -m scholar_radar visa Italy` | Bank statement / proof-of-funds rules for a country (no argument = all) |
| `python -m scholar_radar check-sources` | Test every official page and RSS feed |
| `python -m scholar_radar queries` | Show this week's search queries |
| `python -m pytest` | Run the tests |

## Customise

- **`config/profile.yaml`**: your CGPA, fields, English plan, work experience, fee and funding rules.
  Set `work_experience_years: 2` later and Chevening / DAAD EPOS will move out of "For later".
- **`config/sources.yaml`**: add official pages, RSS feeds, search queries or countries.
- **`config/scholarships_seed.yaml`**: add scholarships you already know about.
- **`config/visa_money.yaml`**: proof-of-funds and bank-statement rules for 43 countries.
  Update an amount whenever you confirm it on an embassy page.

## Honest limitations

- AI extraction can misread pages. Every item links to its source and lists what to **verify**.
- Some sites block bots or load content with JavaScript; `check-sources` shows which.
- Free search backends are sometimes rate-limited; failed searches are skipped and retried next week.
- The agent finds and tracks opportunities. **You** still write your statement of purpose, collect
  documents and apply. See [docs/GUIDE.md](docs/GUIDE.md) for the full roadmap.

## Project structure

```
config/                 profile, sources and seed database (edit these)
scholar_radar/
  sources/              official pages, RSS, web search discovery
  fetch.py              polite fetching (robots.txt, delays, retries)
  llm.py / extract.py   free-tier AI clients and structured extraction
  store.py              memory: change detection, dedup, reminders
  matcher.py            scoring against your profile
  checklist.py          documents you need
  report.py / emailer.py  weekly email
  pipeline.py           ties everything together
  __main__.py           command line
data/state.json         agent memory (created on first run)
docs/GUIDE.md           scholarship, visa and documents roadmap
.github/workflows/      weekly schedule
tests/                  pytest suite
```

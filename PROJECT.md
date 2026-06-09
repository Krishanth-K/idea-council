# IdeaCouncil
A council of local AI agents that scrape real signals from the internet, debate project ideas in a structured courtroom format, and persist the good ones. Fully offline, zero API cost.

## Features
- Multi-source API pipeline (GitHub, HN Algolia, arXiv, DEV.to, Lobste.rs)
- Courtroom-style multi-agent debate: one Lawyer per scoring dimension, two rounds, one Judge
- Round 1: each Lawyer presents their opening argument independently
- Round 2: each Lawyer reads all Round 1 arguments and delivers a short rebuttal
- Judge reads the full transcript and delivers a scored final verdict
- Persistent idea store (SQLite) with scores, tags, and full debate transcripts
- CLI to trigger runs, browse saved ideas, replay debate transcripts
- Configurable loop: run N cycles or run indefinitely on a schedule

## Tech stack
- **Runtime:** Python 3.11+
- **LLM runtime:** Ollama
- **Models:** Qwen2.5 14B (all agents)
- **HTTP client:** `httpx` (all API calls)
- **Storage:** SQLite via `sqlite3` stdlib
- **CLI:** `typer` + `rich`
- **Scheduling (optional):** `APScheduler`

### Rejected Alternatives
- **LangGraph / CrewAI / AutoGen** — pipeline is a linear DAG, no dynamic routing, no conditional branching. A framework adds abstraction with no payoff. Raw Python functions are sufficient and fully transparent.
- **BeautifulSoup / feedparser scraping** — fragile against HTML changes. All 5 sources have stable official APIs; use those instead.
- **Reddit API** — API terms tightened significantly in 2023, requires key, restrictive rate limits. Swapped for Lobste.rs (no auth, clean JSON, tech-focused audience).
- **PostgreSQL** — overkill for a personal tool storing hundreds of rows. SQLite is zero-config and sufficient.
- **ORM (SQLAlchemy etc.)** — unnecessary abstraction for 2 tables and simple queries.

---

# Architecture

## Pipeline overview

```
[CLI trigger / Scheduler]
        │
        ▼
[Scraper Layer]  ─────────────────────────────────────────────────
│  GitHub Scraper    (REST API — trending repos, weekly window)   │
│  HN Scraper        (Algolia API — top stories + Ask HN)        │
│  arXiv Scraper     (API — cs.CV, cs.LG, cs.SE, cs.RO)         │
│  DEV.to Scraper    (API — trending articles)                    │
│  Lobste.rs Scraper (JSON API — hottest stories, no key)        │
└──────────────────────────────────────────────────────────────────
        │
        ▼ raw Signal objects
[Deduplicator]  (SHA256 url hash vs seen_signals table)
        │
        ▼ ~30–50 fresh signals
[Ideator]  (proposes ONE grounded project idea)
        │
        ▼ proposed Idea
[Courtroom — Round 1: Opening Arguments]  ────────────────────────
│  Lawyer: Novelty         (is this underexplored?)               │
│  Lawyer: Feasibility     (can a solo dev ship in 2–6 weeks?)   │
│  Lawyer: Technical Depth (is the engineering non-trivial?)      │
│  Lawyer: Resume Value    (GSoC/interview/portfolio signal?)     │
│  Lawyer: Real Use Case   (does anyone actually need this?)      │
└──────────────────────────────────────────────────────────────────
        │
        ▼ all 5 opening arguments
[Courtroom — Round 2: Cross Examination]  ────────────────────────
│  Same 5 Lawyers, each reads ALL Round 1 args                    │
│  Each delivers a short rebuttal / challenge to other lawyers    │
└──────────────────────────────────────────────────────────────────
        │
        ▼ full transcript (Round 1 + Round 2)
[Judge]  (scores each dimension, delivers final verdict)
        │
        ▼
[Verdict Node]
  weighted score >= 6.5 → save to SQLite → next cycle
  weighted score <  6.5 → discard       → next cycle
  feasibility score < 5 → auto-discard  → next cycle
```

## Scraper layer (detail)

### Design rules
- Each scraper is a plain Python function, not an LLM agent. Scraping is deterministic — no LLM needed.
- Return type: `list[Signal]` where `Signal` is a dataclass: `{source, title, url, blurb, scraped_at}`
- All HTTP via `httpx`. Polite delay of 1–2s between requests per source.
- Dedup: SHA256 hash of `url` checked against `seen_signals` table before passing forward.
- Target: ~30–50 fresh signals per full scrape run across all 5 sources.

### API endpoints

| Source | Endpoint | Auth | What to extract |
|---|---|---|---|
| GitHub | `https://api.github.com/search/repositories?q=created:>DATE&sort=stars` | Optional token (5000 req/hr with, 60 without) | name, description, language, stargazers_count |
| Hacker News | `https://hn.algolia.com/api/v1/search?tags=front_page` + `tags=ask_hn` | None | title, points, num_comments |
| arXiv | `https://export.arxiv.org/api/query?search_query=cat:cs.CV&sortBy=submittedDate` | None | title, summary (first 300 chars) |
| DEV.to | `https://dev.to/api/articles?top=7` | None | title, description, tag_list |
| Lobste.rs | `https://lobste.rs/hottest.json` | None | title, description, tags |

### arXiv categories to query
```
cs.CV  — computer vision
cs.LG  — machine learning
cs.SE  — software engineering
cs.RO  — robotics
```

## Agent layer (detail)

### Core helper
Every agent is a wrapper around one function:

```python
import ollama

def call_llm(system: str, user: str) -> str:
    resp = ollama.chat(
        model="qwen2.5:14b",
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ]
    )
    return resp["message"]["content"]
```

No framework. No magic. Every agent is `call_llm(system_prompt, user_prompt)`.

### State object

```python
@dataclass
class CycleState:
    signals:        list[Signal]
    idea:           Idea
    round1:         dict[str, str]   # dimension -> lawyer argument
    round2:         dict[str, str]   # dimension -> rebuttal
    verdict:        Verdict
```

### Ideator
- **Input:** list of Signal titles + blurbs as a formatted string
- **Task:** identify a gap, niche, or interesting intersection in the signals. Propose ONE concrete project a solo dev can ship in 2–6 weeks.
- **Output (structured):** `{title, one_liner, problem_it_solves, core_technical_challenge}`
- Parse output as JSON. Retry once if malformed.

### Lawyers (Round 1 — Opening Arguments)
Five lawyers, each called independently (no lawyer sees another's output in Round 1).

| Lawyer | Dimension | Their argument |
|---|---|---|
| Novelty Lawyer | `novelty` | Is this genuinely underexplored? Cite comparable existing projects if any. |
| Feasibility Lawyer | `solo_feasibility` | Can one dev ship an MVP in 2–6 weeks? Identify the hardest scope risk. |
| Depth Lawyer | `technical_depth` | Is the core engineering non-trivial? What's the hard problem? |
| Resume Lawyer | `resume_value` | GSoC org fit, interview talking points, uniqueness vs commodity projects. |
| Use Case Lawyer | `real_use_case` | Who is the actual user? Is there a real pain point or is this a solution looking for a problem? |

Each lawyer outputs: `{score_1_to_10, argument, key_points: []}`.

### Lawyers (Round 2 — Cross Examination)
Same five lawyers, now each receives the full Round 1 transcript.
- Task: read all five opening arguments, then write a short rebuttal (2–4 sentences max). Can challenge other lawyers' claims or reinforce their own with new angle.
- Output: `{updated_score_1_to_10, rebuttal}`. Score can change from Round 1.

### Judge
- **Input:** full transcript (idea + all Round 1 args + all Round 2 rebuttals)
- **Task:** synthesize everything. Score each dimension independently. Make the final save/discard call.
- **Output:** `Verdict` dataclass (see below)

### Verdict and scoring rubric

```python
@dataclass
class Verdict:
    idea_title:         str
    one_liner:          str
    scores:             dict[str, float]   # dimension -> 1–10
    weighted_score:     float
    save:               bool
    summary:            str                # 3–5 sentence synthesis
    debate_transcript:  str                # full Round1 + Round2 + verdict
```

**Scoring dimensions:**

| Dimension | Weight | What it measures |
|---|---|---|
| `novelty` | 20% | Genuinely underexplored? (1 = solved a dozen times, 10 = rare gap) |
| `solo_feasibility` | 25% | Solo dev ships MVP in 2–6 weeks? (1 = needs a team, 10 = well-scoped) |
| `technical_depth` | 20% | Non-trivial engineering? (1 = CRUD app, 10 = novel systems work) |
| `resume_value` | 20% | Interview/GSoC/portfolio signal (1 = forgettable, 10 = strong talking point) |
| `real_use_case` | 15% | Real user, real pain point? (1 = no audience, 10 = clear pain) |

**Save threshold:** weighted score >= 6.5 / 10
**Hard discard rule:** `solo_feasibility` < 5 → auto-discard regardless of total score.

*Note: `personal_interest_fit` removed from rubric — too subjective to score reliably via LLM. Can be added as a manual tag later.*

## Storage schema

```sql
CREATE TABLE ideas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    one_liner       TEXT,
    scores          TEXT,       -- JSON: {dimension: score}
    weighted_score  REAL,
    saved           INTEGER,    -- 1 = saved, 0 = discarded
    summary         TEXT,
    transcript      TEXT,       -- full debate transcript
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE seen_signals (
    url_hash    TEXT PRIMARY KEY,
    url         TEXT,
    source      TEXT,
    scraped_at  TEXT
);
```

---

# Current state
Not started.

---

# Where I left off
—

---

# TODOs

## NOW
- [ ] Init repo, set up Python venv, install deps (`httpx`, `typer`, `rich`, `ollama`)
- [ ] Create `Signal`, `Idea`, `Verdict`, `CycleState` dataclasses in `models.py`
- [ ] Write SQLite init script (`init_db.py`) — create both tables
- [ ] Build GitHub scraper and test raw output
- [ ] Build HN scraper (Algolia API) and test raw output
- [ ] Wire both into `run_scrapers()` with dedup logic
- [ ] Print 20 deduped signals to terminal — verify quality before touching agents

## SOON
- [ ] Add arXiv scraper
- [ ] Add DEV.to scraper
- [ ] Add Lobste.rs scraper
- [ ] Implement `call_llm()` helper, test with a dummy prompt against Ollama
- [ ] Build Ideator agent, test with a hardcoded signal batch
- [ ] Build 5 Lawyer agents (Round 1)
- [ ] Build 5 Lawyer agents (Round 2) — same prompts, different input
- [ ] Build Judge agent
- [ ] Wire full cycle: scrape → ideate → round1 → round2 → judge → save
- [ ] Test one full end-to-end cycle, print verdict to terminal
- [ ] Build CLI: `run` (N cycles), `list` (browse saved ideas)

## SOMEDAY
- [ ] `replay <id>` CLI command — re-read full debate transcript for a saved idea
- [ ] Configurable scoring weights via `config.yaml`
- [ ] Scheduled auto-run via APScheduler (e.g. every 6 hours)
- [ ] Export saved ideas to markdown
- [ ] Filter/sort saved ideas by dimension score in CLI
- [ ] "Hard mode": Judge is instructed to be maximally skeptical

## DONE
—

---

# Decisions log

**No agent framework (v1)**
Pipeline is a linear DAG — scrape → ideate → debate → judge → save. No branching, no dynamic routing, no agents spawning agents. LangGraph/CrewAI add abstraction with no payoff here. Every agent is `call_llm(system, user)`. Revisit if pipeline becomes non-linear in v2.

**Courtroom architecture over free-form debate**
Original design had Critic vs Advocate arguing back and forth. Problem: open-ended loops are hard to terminate cleanly and easy to go in circles. Courtroom is strictly structured — Round 1 (independent), Round 2 (rebuttals), Judge (verdict). Same debate value, deterministic execution, easier to implement.

**Lawyers are independent in Round 1**
Each Lawyer only sees the idea in Round 1, not other lawyers' arguments. This prevents early anchoring — if Feasibility Lawyer sees a negative Novelty argument first, it biases their score. Independence in Round 1 ensures each dimension is evaluated on its own merits.

**Reddit → Lobste.rs**
Reddit API tightened significantly in 2023. Requires app registration, OAuth, and has restrictive rate limits. Lobste.rs has a clean public JSON API with no auth, tech-focused content, and good signal quality.

**APIs over scraping**
All 5 sources have stable official APIs. BeautifulSoup scraping breaks on HTML changes and is harder to rate-limit politely. APIs are more reliable, structured, and maintainable.

**`personal_interest_fit` removed from scoring rubric**
Too hard for an LLM to score reliably without a detailed personal profile in the prompt. Adds noise more than signal. Can be added later as a manual tag on saved ideas.

---

# Known issues / debt
—

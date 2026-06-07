# What this is

A council of (local) ai agents that find scrape potential project ideas from online sources, and debate them - project feasibility/resume value/complexity etc and saves the good ideas.

## Features

- Multi source scraping pipeline:
    - GitHub Trending
    - HN
    - arXiv
    - Reddit
    - DEV.to

- Structured multi-agent debate with defined roles: Researcher, Proposer, Critic, Resume Judge, Moderater
- CLI system to trigger runs, scrape ideas, and debate the ideas
- Different debate allocation system - single pass, round robin, etc


## Tech stack

- Runtime: Python 3.11+
- Local LLM runtime: Ollama
- Models: Qwen2.5 14B (reasoning agents) / Llama 3.2 3B (lightweight filter pass)
- Scraping: httpx + BeautifulSoup4 for HTML, feedparser for RSS/Atom feeds
- Storage: SQLite via sqlite3 stdlib (no ORM needed at this scale)
- CLI: typer + rich for output formatting
- Scheduling (optional): APScheduler for timed loops


### Rejected Alternatives

---

# Architecture
 
## Pipeline overview
 
```
[Scheduler / CLI trigger]
        │
        ▼
[Scraper Layer]  ──────────────────────────────────────────────
│  GitHub Trending Agent    (trending repos by language/period) │
│  HN Scraper Agent         (top/new posts, Ask HN threads)    │
│  arXiv RSS Agent          (cs.CV, cs.LG, cs.SE, cs.RO feeds) │
│  Reddit Agent             (r/programming, r/MachineLearning)  │
│  DEV.to RSS Agent         (trending tags)                     │
└───────────────────────────────────────────────────────────────
        │
        ▼ (raw signal batch: titles, blurbs, links)
[Signal Deduplicator]  (hash-based, skips already-seen URLs)
        │
        ▼
[Ideator Agent]  (proposes 1 concrete project idea grounded in signals)
        │
        ▼
[Debate Council]  ──────────────────────────────────────────────
│  Critic Agent       (argues against: scope, novelty, risk)    │
│  Advocate Agent     (argues for: opportunity, feasibility)    │
│  Resume Judge Agent (rates interview/GSoC/portfolio value)    │
│  Moderator Agent    (synthesizes, produces scored verdict)    │
└───────────────────────────────────────────────────────────────
        │
        ▼
[Verdict Node]
  score >= threshold → save to SQLite → loop
  score <  threshold → discard → loop
```
 

## Scraper agents (detail)
 
### How many scrapers?
5 scrapers, each as a simple Python function (not a full LLM agent — scraping is deterministic, no LLM needed here). LLM agents start at the Ideator stage.
 
### What each scraper targets
 
| Scraper | Source | Method | What to extract |
|---|---|---|---|
| GitHub Trending | `https://github.com/trending?since=weekly` | BeautifulSoup (HTML) | Repo name, description, language, stars |
| Hacker News | `https://news.ycombinator.com/` + Ask HN | BeautifulSoup (HTML) | Post titles, point counts, comment counts |
| arXiv | RSS feeds per category | feedparser | Paper titles, abstracts (first 200 chars) |
| Reddit | JSON API (`reddit.com/r/X.json`) | httpx + json | Post titles, score, flair |
| DEV.to | `https://dev.to/feed` (RSS) | feedparser | Article titles, tags |
 
### arXiv feeds to use
```
https://rss.arxiv.org/rss/cs.CV   (computer vision)
https://rss.arxiv.org/rss/cs.LG   (machine learning)
https://rss.arxiv.org/rss/cs.SE   (software engineering)
https://rss.arxiv.org/rss/cs.RO   (robotics)
```
 
### Scraper design rules

- Each scraper returns a list of `Signal` dataclass objects: `{source, title, url, blurb, scraped_at}`
- Scrapers are rate-limited with a small sleep (1–2s) between requests
- Deduplication: SHA256 hash of `url` checked against `seen_signals` table in SQLite before passing forward
- A single scraper run collects ~30–50 signals total across all sources; these are passed as a batch to the Ideator

---

## Agent design (detail)
 
### LangGraph state

```python
class CouncilState(TypedDict):
    signals: list[Signal]          # raw scraped signals
    proposed_idea: str             # Ideator's output
    critique: str                  # Critic's output
    advocacy: str                  # Advocate's output
    resume_analysis: str           # Resume Judge's output
    verdict: Verdict               # Moderator's scored output
    cycle_count: int
```
 

### Agent roles and prompts (condensed)
 
- **Ideator Agent:**
    - Input: batch of ~30–50 signal titles/blurbs
    - Task: Identify a gap, underserved niche, or interesting intersection visible in the signals. Propose ONE concrete project a solo dev could build in 2–6 weeks. Output a structured idea: `{title, one-liner, problem_it_solves, core_technical_challenge}`.
    - Model: Qwen2.5 14B

- **Critic Agent:**
    - Input: proposed idea
    - Task: Argue against. Cover: (1) is this already solved well? (2) is the scope realistic for solo dev? (3) is there a real user / use case? (4) is the technical challenge actually interesting or just tedious?
    - Output: structured critique with explicit weakness list
    - Model: Qwen2.5 14B

- **Advocate Agent:**
    - Input: proposed idea + critique
    - Task: Argue for. Rebut the critique where possible. Identify the strongest case for building this. Don't be a yes-man — if critique is fatal, say so.
    - Output: structured case with explicit strength list
    - Model: Qwen2.5 14B

- **Resume Judge Agent:**
    - Input: proposed idea
    - Task: Evaluate purely on career signal. Score and comment on: (1) GSoC org fit (2) systems/CV interview talking points (3) uniqueness vs commodity projects (4) demonstrable technical depth
    - Output: score + justification per axis
    - Model: Qwen2.5 14B

- **Moderator Agent:**
    - Input: idea + critique + advocacy + resume analysis
    - Task: Synthesize. Produce a final `Verdict` object with numeric scores. Make the save/discard call.
    - Output: `Verdict` dataclass (see below)
    - Model: Qwen2.5 14B


### Verdict / scoring rubric
 
```python
@dataclass
class Verdict:
    idea_title: str
    one_liner: str
    scores: dict  # keys below, values 1–10
    save: bool
    summary: str
    debate_transcript: str  # full concatenated agent outputs
```
 

**Scoring dimensions (all 1–10):**
 
| Dimension | Weight | What it measures |
|---|---|---|
| `novelty` | 20% | Is this genuinely underexplored? (1 = solved a dozen times, 10 = rare gap) |
| `solo_feasibility` | 25% | Can one dev ship an MVP in 2–6 weeks? (1 = needs a team, 10 = well-scoped) |
| `technical_depth` | 20% | Does it involve non-trivial engineering? (1 = CRUD app, 10 = novel systems work) |
| `resume_value` | 20% | Interview/GSoC/portfolio signal (1 = forgettable, 10 = strong talking point) |
| `real_use_case` | 10% | Does a real person actually need this? (1 = no audience, 10 = clear pain point) |
| `personal_interest_fit` | 5% | Overlap with systems, CV, astrophotography, CLI tools (softcoded) |
 
**Save threshold:** weighted score >= 6.5 / 10
 
**Tie-breaking rule:** if `solo_feasibility` < 5, auto-discard regardless of total score.
 
## Storage schema
 
```sql
CREATE TABLE ideas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    one_liner   TEXT,
    scores      TEXT,  -- JSON blob
    total_score REAL,
    save        INTEGER,
    summary     TEXT,
    transcript  TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);
 
CREATE TABLE seen_signals (
    url_hash    TEXT PRIMARY KEY,
    url         TEXT,
    scraped_at  TEXT
);
```


---

# Current state


---

# Where I left off


---

# TODOs

## NOW
- [ ] 

## SOON

## SOMEDAY

## DONE

---

# Decisions log

---

# Known issues / debt





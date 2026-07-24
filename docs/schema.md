# Database Schema

IdeaCouncil uses a two-table SQLite database (`council.db`) stored in the project root.

---

## `ideas` — Validated Project Proposals

Stores every proposal that completes the courtroom pipeline, whether accepted or rejected.

```sql
CREATE TABLE IF NOT EXISTS ideas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    one_liner       TEXT,
    scores          TEXT,       -- JSON: {"novelty": float, "solo_feasibility": float, ...}
    weighted_score  REAL,
    saved           INTEGER,    -- 1 = Accepted, 0 = Rejected
    summary         TEXT,       -- Judicial synthesis statement
    transcript      TEXT,       -- Full Round 1 + Round 2 debate record
    created_at      TEXT DEFAULT (datetime('now'))
);
```

---

## `seen_signals` — Deduplication Index

Tracks every signal URL that has been ingested so duplicate content is never reprocessed.

```sql
CREATE TABLE IF NOT EXISTS seen_signals (
    url_hash    TEXT PRIMARY KEY,  -- SHA-256 hash of signal URL
    url         TEXT,
    source      TEXT,
    scraped_at  TEXT
);
```

---

## Scoring & Decision Rules

| Dimension | Weight | Hard Gate |
|---|---|---|
| Novelty | 20% | — |
| Solo Feasibility | 25% | Score < 5.0 → auto-reject |
| Technical Depth | 20% | — |
| Resume Signal | 20% | — |
| Real-World Utility | 15% | — |

- **Persistence threshold**: `weighted_score >= 6.5` → saved to `ideas` table
- **Feasibility gate**: `solo_feasibility < 5.0` → discarded regardless of total score

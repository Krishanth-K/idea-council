# IdeaCouncil Implementation Plan — Dashboard Phase 1

This plan maps the Phase 1 changes from `CHANGES_PLAN.md` into actionable implementation steps. The focus is on parallelizing scrape and ideation, adding archive support, and building the real-time dashboard UI.

---

## Phase 1: Database & API Foundation

Get the storage layer and archive endpoints ready first.

### 1.1 Database Updates

- **Fix rejected ideas storage**: Currently only saved ideas go to DB. Update the rejected branch in `server.py` (~lines 671–677) to call `save_verdict(verdict, full_transcript, saved=0)` for rejected verdicts too.

### 1.2 Archive API Endpoints

- **`GET /api/archive`** — Returns both saved and rejected ideas, grouped. Payload: `id, title, one_liner, scores, weighted_score, summary, created_at` (exclude `transcript` for list view).
- **`GET /api/archive/{id}`** — Detail fetch, includes full `transcript` and verdict reasoning.

---

## Phase 2: Parallel Scraper Layer

Transform the sequential scraper into a parallel pipeline.

### 2.1 Backend Parallelization

- Modify `council/scrape/__init__.py`: wrap each `scraper_fn()` call in `asyncio.to_thread()` and fire all 5 with `asyncio.gather(*tasks, return_exceptions=True)`.
- No changes needed inside individual scraper files (`github.py`, `hn.py`, etc.) — they remain synchronous.

### 2.2 New WebSocket Events

Add these events extending the existing `emit_event` pattern:

- `source_started` — fired immediately when scrape starts, for all 5 sources.
- `source_completed` — fired per source when it finishes (independently, respecting network variance).
- `source_error` — fired per source on error; doesn't block other sources.

---

## Phase 3: Parallel Ideation

Parallelize idea generation across signals.

### 3.1 Backend Parallelization

- In `council/orchestrator.py` (~line 235), wrap each per-signal ideator call in `asyncio.to_thread()`.
- Add `asyncio.Semaphore(2)` to cap concurrent ideation calls (protect the shared GPU). Make configurable.

### 3.2 New WebSocket Events

- `ideation_started` — per signal, fired when ideation begins.
- `ideation_completed` — per signal, carries the generated idea payload.
- `ideation_error` — per signal, on failure.

---

## Phase 4: Debate WebSocket Events

Add events for the sequential debate flow (Round 1 → Round 2 → Judge).

### 4.1 New WebSocket Events

- `debate_started` — with `idea_id`
- `round1_lawyer_started` / `round1_lawyer_completed` — with `idea_id`, `dimension`
- `round2_lawyer_started` / `round2_lawyer_completed` — with `idea_id`, `dimension`
- `judge_started` / `judge_completed` — with `idea_id`, `verdict`

Note: Backend stays sequential (no `asyncio.gather` for lawyers in this phase). Round 1 parallelization is deferred to Phase 2.

---

## Phase 5: Zustand Store (`ui/src/store.js`)

Build the frontend state management.

### 5.1 Signal Status Enum

Add `status` field to each signal: `scraped` → `ideating` → `idea_generated` → `debating` → `resolved`

### 5.2 Queue Tracking

- `ideationQueue: []` — tracks signals pending/in-flight ideation
- `debateQueue: []` — tracks ideas pending/in-flight debate
- `activeCycle` — stays singular (debate is sequential across ideas in this phase)

### 5.3 Archive Data

- `archive: { saved: [], rejected: [] }` — populated by `/api/archive` endpoints on tab open (pull, not WS-streamed)

---

## Phase 6: UI Components

Build the dashboard layout and visualization components.

### 6.1 Page Layout

- **"Live Run" tab** — active pipeline board
- **"Archive" tab** — historical saved/rejected ideas

### 6.2 Live Run Tab

**Top Control Bar:**
- `[Start Scrape]` — disabled while scrape in-flight
- `[Run Ideator]` — disabled if no signals are `New` or ideation in-flight
- `[Start Debate]` — disabled if no ideas are `Pending Debate` or debate in-flight
- Status strip: `run_id`, current stage, elapsed time

**Three-Column Board:**
- **Column A — Signals**: scraped signals with badges (`New` / `Idea Generated` / `Debating` / `Resolved`)
- **Column B — Ideas**: ideas with badges (`Pending Debate` / `Debating` / `Saved` / `Rejected`)
- **Column C — Active Debate**: courtroom visualization for current idea, plus "up next" queue

**Detail Drawer:**
- Signal card: raw scraped payload, source, link, timestamp
- Idea card: generated text, parent signal, (after debate) transcript + scores

### 6.3 Scrape Animation

- 5 source cards (GitHub / Hacker News / arXiv / DEV.to / Lobste.rs)
- On click: all 5 transition to "scraping" state (pulse/shimmer + spinner)
- On `source_completed`: flip to "done" with count badge, signals slide into Column A with source-colored dots

### 6.4 Ideation Animation

- In Column A, `New` cards show thinking/spinner
- On `ideation_completed`: badge flips to `Idea Generated`, card slides to Column B

### 6.5 Debate Visualization

- 5 lawyer cards (Novelty / Feasibility / Technical Depth / Resume Value / Real Use Case)
- Sequential highlight: active lawyer highlights → reveals score + argument → moves to next
- Round 2: adds "Rebuttal" section below each argument
- Judge: "bench" card appears, shows score breakdown, weighted score, save/reject decision with verdict animation

### 6.6 Archive Tab

- Filter toggle: Saved / Rejected
- Card grid or table: title, one-liner, weighted score, per-dimension visualization, created_at
- Click opens detail drawer with full transcript + verdict reasoning

---

## Phase 7: Integration & Testing

Connect the pieces and verify the flow.

### 7.1 WS Connection

- Ensure frontend connects to WebSocket on load
- Route incoming events to correct store actions

### 7.2 Button Gating

- Verify buttons disable correctly based on pipeline state
- Test: Start Scrape → Run Ideator → Start Debate end-to-end

### 7.3 Archive Verification

- Run a cycle that saves an idea (weighted_score >= 6.5 AND solo_feasibility >= 5)
- Run a cycle that rejects an idea
- Verify both appear in `/api/archive` and display correctly in Archive tab

---

## Notes

- **Round 1 parallelization** is deferred to a future Phase 2 — the event schema already supports it.
- **Debate stays sequential** across ideas (not concurrent) to avoid 11+ simultaneous LLM calls on the single shared GPU.
- **Batch triggers**: "Run Ideator" and "Start Debate" act on all eligible items, not per-card actions.

---

Build the storage layer, wire up parallel scrapers and ideation, add archive endpoints, then construct the real-time dashboard UI.
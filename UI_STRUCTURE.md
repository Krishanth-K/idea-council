# IdeaCouncil UI Structure Specification

This document defines the structure and layout for a real-time UI that visualizes an IdeaCouncil run. It intentionally avoids visual design decisions such as colors, spacing, typography, animation style, and final component styling. The goal is to give future implementation tools a clear product and data structure to build from.

## Product Goal

The UI should let a user watch IdeaCouncil operate in real time:

- Scrapers collecting signals from GitHub, Hacker News, arXiv, DEV.to, and Lobste.rs.
- Signals entering a queue after deduplication.
- The Ideator converting one signal into one project idea.
- Five lawyer agents evaluating the idea in Round 1.
- The same five lawyer agents revising or defending their positions in Round 2.
- The Judge making a final weighted decision.
- Saved, rejected, skipped, and failed ideas accumulating during the run.

The UI should feel like a run monitor for an active pipeline, not a marketing page and not a generic chat interface.

## Existing Backend Concepts

The current Python code already has these core entities:

- `Signal`
  - `source`
  - `title`
  - `url`
  - `blurb`
  - `scraped_at`
- `Idea`
  - `title`
  - `one_liner`
  - `target_user`
  - `problem_it_solves`
  - `core_technical_challenge`
  - `source_signals`
  - `estimated_scope`
  - `skip`
  - `skip_reason`
- Round 1 lawyer result
  - `score`
  - `argument`
  - `key_points`
- Round 2 lawyer result
  - `updated_score`
  - `rebuttal`
- `Verdict`
  - `idea_title`
  - `one_liner`
  - `scores`
  - `weighted_score`
  - `save`
  - `summary`
  - `debate_transcript`

The current orchestration flow is:

```text
scrape_all
  -> deduplicate signals
  -> for each signal:
       run_ideator
       run_round1
       run_round2
       run_judge
       save_verdict if accepted
```

The UI should mirror this flow directly.

## High-Level Page Layout

Use a single-page application layout with three persistent regions:

```text
┌────────────────────────────────────────────────────────────────────┐
│ Run Header                                                         │
├──────────────────┬────────────────────────────────┬────────────────┤
│ Signal Sidebar   │ Active Council Cycle            │ Verdict Sidebar│
│                  │                                │                │
└──────────────────┴────────────────────────────────┴────────────────┘
```

### Region 1: Run Header

The Run Header is a top-level status bar for the entire execution.

It should remain visible regardless of which signal or verdict is selected.

Required content:

- Current run status.
- Current stage.
- Current signal progress.
- Total signals discovered.
- Total signals processed.
- Saved count.
- Rejected count.
- Skipped count.
- Error count.
- Optional run controls, if supported by the backend:
  - Start run.
  - Stop run.
  - Pause run.
  - Resume run.

Suggested fields:

```ts
type RunSummary = {
  run_id: string;
  status: RunStatus;
  stage: PipelineStage | null;
  current_signal_index: number;
  total_signals: number;
  signals_processed: number;
  saved_count: number;
  rejected_count: number;
  skipped_count: number;
  error_count: number;
  started_at: string | null;
  completed_at: string | null;
};
```

### Region 2: Signal Sidebar

The Signal Sidebar shows the raw input pipeline.

It answers:

- Which sources are being scraped?
- How many signals came from each source?
- Which signals are queued?
- Which signal is currently active?
- Which signals were deduplicated, skipped, processed, or failed?

Recommended sections:

1. Source status list.
2. Deduplication summary.
3. Fresh signal queue.

#### Source Status List

Show one row per scraper source:

- GitHub
- Hacker News
- arXiv
- DEV.to
- Lobste.rs

Each row should expose:

- Source name.
- Scrape status.
- Number of raw signals found.
- Number of fresh signals accepted.
- Number of duplicate signals ignored.
- Error message, if any.

Suggested shape:

```ts
type SourceStatus = {
  source: "github" | "hacker_news" | "arxiv" | "devto" | "lobsters";
  label: string;
  status: SourceScrapeStatus;
  raw_count: number;
  fresh_count: number;
  duplicate_count: number;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
};
```

#### Deduplication Summary

Show compact run-level counts:

- Raw signals scraped.
- Fresh signals queued.
- Duplicate signals ignored.
- Signals already processed.

Suggested shape:

```ts
type DedupSummary = {
  raw_total: number;
  fresh_total: number;
  duplicate_total: number;
  already_seen_total: number;
};
```

#### Fresh Signal Queue

Show a vertical list of signals.

Each item should display:

- Source.
- Title.
- Short blurb preview.
- Processing status.
- Position in queue.

The active signal should be visibly distinct from queued and completed signals, but this document does not prescribe styling.

Suggested shape:

```ts
type SignalListItem = {
  signal_id: string;
  source: string;
  title: string;
  url: string;
  blurb_preview: string;
  scraped_at: string;
  status: SignalStatus;
  queue_index: number;
};
```

### Region 3: Active Council Cycle

The Active Council Cycle is the central workspace. It shows exactly one signal moving through the council.

Recommended vertical structure:

```text
Active Signal
  ↓
Ideator
  ↓
Round 1: Opening Arguments
  ↓
Round 2: Cross Examination
  ↓
Judge
```

Only one active cycle should be primary at a time. If the backend later supports parallel processing, the UI can still use this region for the selected active cycle while the sidebars show the broader run state.

#### Active Signal Panel

Purpose: show the raw signal that triggered the current idea.

Required content:

- Source.
- Title.
- URL.
- Blurb.
- Scraped timestamp.
- Signal status.

Suggested shape:

```ts
type ActiveSignal = {
  signal_id: string;
  source: string;
  title: string;
  url: string;
  blurb: string;
  scraped_at: string;
  status: SignalStatus;
};
```

#### Ideator Panel

Purpose: show the first transformation from signal to project idea.

Required content:

- Ideator status.
- Proposed idea title.
- One-liner.
- Target user.
- Problem solved.
- Core technical challenge.
- Estimated scope.
- Source signal references.
- Skip state and skip reason, if applicable.
- Error state, if applicable.

Suggested shape:

```ts
type IdeatorState = {
  status: AgentStatus;
  idea: IdeaView | null;
  skip_reason: string | null;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
};

type IdeaView = {
  title: string;
  one_liner: string;
  target_user: string;
  problem_it_solves: string;
  core_technical_challenge: string;
  source_signals: string[];
  estimated_scope: string;
};
```

If the Ideator skips a signal, Round 1, Round 2, and Judge sections should remain collapsed or marked as not run.

#### Round 1 Panel

Purpose: show each lawyer's independent opening argument.

Use five lawyer result cards:

- Novelty.
- Solo Feasibility.
- Technical Depth.
- Resume Value.
- Real Use Case.

Each lawyer card should show:

- Dimension label.
- Agent status.
- Score out of 10.
- Key points.
- Argument body.
- Error, if any.

The layout should optimize for scanning all five scores at once. A grid is preferred over a chat transcript.

Suggested shape:

```ts
type RoundOneState = {
  status: RoundStatus;
  lawyers: Record<ScoringDimension, RoundOneLawyerState>;
  started_at: string | null;
  completed_at: string | null;
};

type RoundOneLawyerState = {
  dimension: ScoringDimension;
  label: string;
  status: AgentStatus;
  score: number | null;
  argument: string | null;
  key_points: string[];
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
};
```

#### Round 2 Panel

Purpose: show cross-examination and score movement after each lawyer sees all Round 1 arguments.

Use the same five lawyer dimensions as Round 1.

Each lawyer card should show:

- Dimension label.
- Agent status.
- Original Round 1 score.
- Updated Round 2 score.
- Score delta.
- Rebuttal text.
- Error, if any.

Suggested shape:

```ts
type RoundTwoState = {
  status: RoundStatus;
  lawyers: Record<ScoringDimension, RoundTwoLawyerState>;
  started_at: string | null;
  completed_at: string | null;
};

type RoundTwoLawyerState = {
  dimension: ScoringDimension;
  label: string;
  status: AgentStatus;
  original_score: number | null;
  updated_score: number | null;
  score_delta: number | null;
  rebuttal: string | null;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
};
```

#### Judge Panel

Purpose: show the final decision and synthesis.

Required content:

- Judge status.
- Final save or reject decision.
- Weighted score.
- Final score per dimension.
- Feasibility hard-discard indicator.
- Judge summary.
- Link or button to inspect full transcript.
- Error, if any.

Suggested shape:

```ts
type JudgeState = {
  status: AgentStatus;
  verdict: VerdictView | null;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
};

type VerdictView = {
  idea_title: string;
  one_liner: string;
  scores: Record<ScoringDimension, number>;
  weighted_score: number;
  save: boolean;
  summary: string;
  hard_discard_reason: string | null;
  debate_transcript: string;
};
```

### Region 4: Verdict Sidebar

The Verdict Sidebar shows accumulated outcomes from the current run.

It answers:

- Which ideas have been saved?
- Which ideas were rejected?
- Which signals were skipped?
- Which cycles failed?

Recommended sections:

1. Saved ideas.
2. Rejected ideas.
3. Skipped signals.
4. Errors.

Each item should be selectable. Selecting an item should load its details into a drawer, modal, or detail panel without losing the active run context.

#### Saved Ideas

Each item should show:

- Idea title.
- Weighted score.
- Short one-liner.
- Created/completed time.

#### Rejected Ideas

Each item should show:

- Idea title.
- Weighted score.
- Main reject reason, if available.
- Whether it was rejected by threshold or hard feasibility discard.

#### Skipped Signals

Each item should show:

- Source.
- Signal title.
- Skip reason.

#### Errors

Each item should show:

- Stage where the error happened.
- Associated source, signal, cycle, or agent.
- Error message.

## Detail Drawer or Modal

The UI needs a way to inspect a completed cycle without disrupting the active pipeline monitor.

Use a detail drawer, modal, or side panel. The exact presentation can be decided later.

The detail view should include:

- Original signal.
- Generated idea.
- Round 1 lawyer outputs.
- Round 2 lawyer outputs.
- Judge verdict.
- Full debate transcript.
- Raw error details, if any.

Suggested shape:

```ts
type CycleDetail = {
  cycle_id: string;
  signal: ActiveSignal;
  ideator: IdeatorState;
  round1: RoundOneState;
  round2: RoundTwoState;
  judge: JudgeState;
  final_status: CycleStatus;
};
```

## Component Hierarchy

Initial implementation should follow this component structure:

```text
App
├── RunHeader
├── DashboardLayout
│   ├── SignalSidebar
│   │   ├── SourceStatusList
│   │   ├── DedupSummary
│   │   └── SignalQueue
│   ├── ActiveCycleView
│   │   ├── ActiveSignalPanel
│   │   ├── IdeatorPanel
│   │   ├── RoundOnePanel
│   │   │   └── RoundOneLawyerCard
│   │   ├── RoundTwoPanel
│   │   │   └── RoundTwoLawyerCard
│   │   └── JudgePanel
│   └── VerdictSidebar
│       ├── SavedIdeasList
│       ├── RejectedIdeasList
│       ├── SkippedSignalsList
│       └── ErrorList
└── CycleDetailDrawer
```

## Status Enums

These enums should be used consistently across backend events and frontend state.

```ts
type RunStatus =
  | "idle"
  | "scraping"
  | "processing"
  | "complete"
  | "failed"
  | "cancelled";

type PipelineStage =
  | "scraping"
  | "deduplicating"
  | "queued"
  | "ideating"
  | "round1"
  | "round2"
  | "judging"
  | "saving"
  | "complete";

type SourceScrapeStatus =
  | "idle"
  | "scraping"
  | "complete"
  | "failed";

type SignalStatus =
  | "queued"
  | "processing"
  | "skipped"
  | "judged"
  | "saved"
  | "rejected"
  | "failed";

type AgentStatus =
  | "waiting"
  | "thinking"
  | "complete"
  | "skipped"
  | "error";

type RoundStatus =
  | "waiting"
  | "running"
  | "complete"
  | "skipped"
  | "error";

type CycleStatus =
  | "queued"
  | "ideating"
  | "round1"
  | "round2"
  | "judging"
  | "saved"
  | "rejected"
  | "skipped"
  | "failed";

type ScoringDimension =
  | "novelty"
  | "solo_feasibility"
  | "technical_depth"
  | "resume_value"
  | "real_use_case";
```

## Real-Time Event Model

The UI should be driven by append-only events from the backend. WebSocket, Server-Sent Events, or a local polling adapter can all use the same event shapes.

Each event should include:

- `type`
- `run_id`
- `timestamp`
- Optional `cycle_id`
- Optional `signal_id`
- Event-specific payload

Base shape:

```ts
type CouncilEvent = {
  type: CouncilEventType;
  run_id: string;
  timestamp: string;
  cycle_id?: string;
  signal_id?: string;
  payload: Record<string, unknown>;
};
```

Required event types:

```ts
type CouncilEventType =
  | "run_started"
  | "source_scrape_started"
  | "source_scrape_completed"
  | "source_scrape_failed"
  | "signal_discovered"
  | "signal_deduplicated"
  | "signal_queued"
  | "signal_processing_started"
  | "ideator_started"
  | "ideator_completed"
  | "ideator_skipped"
  | "ideator_failed"
  | "round_started"
  | "lawyer_started"
  | "lawyer_completed"
  | "lawyer_failed"
  | "judge_started"
  | "judge_completed"
  | "judge_failed"
  | "verdict_saved"
  | "verdict_rejected"
  | "cycle_completed"
  | "run_completed"
  | "run_failed";
```

### Example Events

#### Run Started

```json
{
  "type": "run_started",
  "run_id": "run_2026_06_21_001",
  "timestamp": "2026-06-21T10:00:00+05:30",
  "payload": {
    "max_signals_per_source": 10,
    "cycles": 1
  }
}
```

#### Source Scrape Completed

```json
{
  "type": "source_scrape_completed",
  "run_id": "run_2026_06_21_001",
  "timestamp": "2026-06-21T10:00:08+05:30",
  "payload": {
    "source": "github",
    "raw_count": 10,
    "fresh_count": 8,
    "duplicate_count": 2
  }
}
```

#### Signal Queued

```json
{
  "type": "signal_queued",
  "run_id": "run_2026_06_21_001",
  "timestamp": "2026-06-21T10:00:09+05:30",
  "signal_id": "signal_012",
  "payload": {
    "source": "github",
    "title": "Example Repository",
    "url": "https://github.com/example/repo",
    "blurb": "A short description of the repository.",
    "scraped_at": "2026-06-21T10:00:07+05:30",
    "queue_index": 12
  }
}
```

#### Ideator Completed

```json
{
  "type": "ideator_completed",
  "run_id": "run_2026_06_21_001",
  "cycle_id": "cycle_004",
  "signal_id": "signal_012",
  "timestamp": "2026-06-21T10:02:11+05:30",
  "payload": {
    "idea": {
      "title": "Dependency Drift Radar",
      "one_liner": "A local tool that detects when dependency updates introduce architectural drift.",
      "target_user": "Solo maintainers of medium-sized open source projects",
      "problem_it_solves": "Maintainers struggle to understand hidden consequences of dependency updates.",
      "core_technical_challenge": "Building a dependency graph diff and risk-scoring changed packages.",
      "source_signals": ["Example Repository"],
      "estimated_scope": "2-4 weeks"
    }
  }
}
```

#### Lawyer Completed

```json
{
  "type": "lawyer_completed",
  "run_id": "run_2026_06_21_001",
  "cycle_id": "cycle_004",
  "signal_id": "signal_012",
  "timestamp": "2026-06-21T10:03:24+05:30",
  "payload": {
    "round": 1,
    "dimension": "novelty",
    "score": 7,
    "argument": "The idea is moderately novel because most dependency tools focus on vulnerabilities rather than architectural drift.",
    "key_points": [
      "Related to dependency analysis",
      "Different from vulnerability scanning",
      "Novelty depends on quality of drift model"
    ]
  }
}
```

#### Round 2 Lawyer Completed

```json
{
  "type": "lawyer_completed",
  "run_id": "run_2026_06_21_001",
  "cycle_id": "cycle_004",
  "signal_id": "signal_012",
  "timestamp": "2026-06-21T10:05:02+05:30",
  "payload": {
    "round": 2,
    "dimension": "solo_feasibility",
    "original_score": 8,
    "updated_score": 7,
    "rebuttal": "The scope is still manageable, but the technical-depth argument correctly notes that high-quality graph analysis could expand beyond a 2-6 week MVP."
  }
}
```

#### Judge Completed

```json
{
  "type": "judge_completed",
  "run_id": "run_2026_06_21_001",
  "cycle_id": "cycle_004",
  "signal_id": "signal_012",
  "timestamp": "2026-06-21T10:06:30+05:30",
  "payload": {
    "verdict": {
      "idea_title": "Dependency Drift Radar",
      "one_liner": "A local tool that detects when dependency updates introduce architectural drift.",
      "scores": {
        "novelty": 7,
        "solo_feasibility": 7,
        "technical_depth": 8,
        "resume_value": 8,
        "real_use_case": 7
      },
      "weighted_score": 7.4,
      "save": true,
      "summary": "This is a focused and technically meaningful idea with a clear maintainer use case. The MVP can be scoped to dependency graph diffs and simple risk heuristics. It should be saved.",
      "hard_discard_reason": null
    }
  }
}
```

## Frontend State Model

The frontend should maintain derived state from events.

Suggested top-level state:

```ts
type CouncilRunState = {
  run: RunSummary;
  sources: Record<string, SourceStatus>;
  dedup: DedupSummary;
  signal_queue: SignalListItem[];
  active_cycle: CycleDetail | null;
  completed_cycles: CycleDetail[];
  saved_ideas: CycleDetail[];
  rejected_ideas: CycleDetail[];
  skipped_signals: CycleDetail[];
  errors: CouncilError[];
};

type CouncilError = {
  error_id: string;
  stage: PipelineStage | string;
  source?: string;
  cycle_id?: string;
  signal_id?: string;
  dimension?: ScoringDimension;
  message: string;
  timestamp: string;
};
```

The backend can emit events. The frontend reducer should update `CouncilRunState`.

## Mapping Backend Functions To UI Events

Current function-to-event mapping:

```text
main.run
  -> run_started

scrape_all
  -> source_scrape_started
  -> signal_discovered
  -> signal_deduplicated
  -> signal_queued
  -> source_scrape_completed

run_council_cycle
  -> signal_processing_started

run_ideator
  -> ideator_started
  -> ideator_completed OR ideator_skipped OR ideator_failed

run_round1
  -> round_started round=1
  -> lawyer_started round=1 dimension=...
  -> lawyer_completed round=1 dimension=...
  -> lawyer_failed round=1 dimension=...

run_round2
  -> round_started round=2
  -> lawyer_started round=2 dimension=...
  -> lawyer_completed round=2 dimension=...
  -> lawyer_failed round=2 dimension=...

run_judge
  -> judge_started
  -> judge_completed OR judge_failed

save_verdict
  -> verdict_saved

rejected verdict
  -> verdict_rejected

end of signal cycle
  -> cycle_completed

end of full run
  -> run_completed
```

## Minimal Viable UI

The first useful version should include:

1. Run Header.
2. Signal Sidebar with source statuses and signal queue.
3. Active Signal Panel.
4. Ideator Panel.
5. Round 1 lawyer grid.
6. Round 2 lawyer grid.
7. Judge Panel.
8. Verdict Sidebar with saved and rejected ideas.

Do not build settings, advanced filtering, transcript search, charts, or historical analytics in the first pass.

## Later Enhancements

After the basic real-time monitor works, consider:

- Run history page.
- Saved idea browser backed by SQLite.
- Full transcript search.
- Per-source scrape diagnostics.
- Agent latency measurements.
- Score distribution chart.
- Export verdict as Markdown.
- Replay mode for a completed run.
- Manual notes or tags on saved ideas.

## Implementation Notes

- The UI should not depend on LLM text streaming. It can update when each agent completes.
- If streaming token-level output is added later, it should be displayed inside the relevant active agent card only.
- The central active cycle should remain readable even when processing dozens of signals.
- Avoid treating lawyer outputs as chat messages. They are structured evaluations and should be shown as structured cards.
- The full transcript should be available but not always visible by default.
- Saved and rejected ideas should remain visible after the active cycle moves to the next signal.
- Error states should be first-class and tied to the stage where they occurred.


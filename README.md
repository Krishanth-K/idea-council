# IdeaCouncil

> An autonomous courtroom-style multi-agent engine that finds, debates, and validates software project ideas — so you never build the wrong thing.

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue?style=flat-square&logo=python)
![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)
![Local-first](https://img.shields.io/badge/LLM-Local%20%7C%20Cloud-purple?style=flat-square)
![FastAPI](https://img.shields.io/badge/Backend-FastAPI-teal?style=flat-square&logo=fastapi)

---

## What is this?

IdeaCouncil scrapes real developer signals from GitHub, Hacker News, arXiv, DEV.to, and Lobste.rs, synthesizes a grounded project idea, then runs it through a structured **two-round courtroom debate** between five specialized AI evaluators. A presiding Judge scores the proposal against a weighted rubric and only persists high-signal ideas to the database. Everything streams live to a React dashboard via WebSockets.

Built for solo developers who want meaningful, feasible portfolio projects — not generic CRUD apps or over-scoped enterprise fever dreams.

---

## Quick Start

```bash
# 1. Clone & install
git clone https://github.com/Krishanth-K/idea-council.git
cd idea-council
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Pull a local model (or set OLLAMA_HOST / DEFAULT_MODEL for cloud)
ollama pull qwen2.5:14b

# 3. Run a single evaluation cycle via CLI
python3 -m council.main run
```

To launch the live dashboard instead, see [Running the Dashboard](#running-the-dashboard).

---

## How It Works

```
[ CLI / Scheduler ]
        │
        ▼
┌───────────────────────────────────────────────────┐
│ Scraper Layer (async httpx)                        │
│  GitHub · Hacker News · arXiv · DEV.to · Lobste.rs│
└───────────────────────────────────────────────────┘
        │ raw signals
        ▼
┌───────────────────────────────────────────────────┐
│ Deduplication  (SHA-256 vs seen_signals table)     │
└───────────────────────────────────────────────────┘
        │ ~30–50 fresh signals
        ▼
┌───────────────────────────────────────────────────┐
│ Ideator Agent  →  ONE concrete proposal (2–6 wks) │
└───────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────┐
│ Round 1 — Independent Opening Arguments            │
│  Novelty · Feasibility · Depth · Resume · Utility │
└───────────────────────────────────────────────────┘
        │ full transcript
        ▼
┌───────────────────────────────────────────────────┐
│ Round 2 — Cross-Examination & Rebuttals            │
└───────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────┐
│ Judicial Verdict  →  weighted score (0–10)         │
│  Gate: score ≥ 6.5 AND feasibility ≥ 5.0          │
│  Pass → SQLite + WebSocket broadcast               │
│  Fail → logged and discarded                       │
└───────────────────────────────────────────────────┘
```

**Why a courtroom?** Standard LLM prompts suffer from sycophancy and agreement bias. Round 1 isolates each evaluator to prevent anchoring; Round 2 forces adversarial rebuttals before the Judge synthesizes a final verdict. See [Architecture Decisions](docs/architecture.md) for the full rationale.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Orchestration | Python 3.11 state machine (`dataclasses`, `asyncio`) |
| API Server | FastAPI + Uvicorn |
| Real-time | WebSockets (`/ws`) |
| Storage | SQLite (`sqlite3` stdlib) |
| HTTP Client | `httpx` with rate-limiting |
| CLI | `typer` + `rich` |
| Frontend | React 18 + Vite |
| Styling | Tailwind CSS + Lucide Icons |
| LLM Interface | Any OpenAI-compatible endpoint (Ollama, LM Studio, cloud) |

---

## Project Structure

```
idea-council/
├── council/
│   ├── scrape/         # Per-platform scrapers (GitHub, HN, arXiv, DEV.to, Lobste.rs)
│   ├── core.py         # LLM client interface
│   ├── db.py           # SQLite schema & data access
│   ├── main.py         # CLI (Typer)
│   ├── models.py       # Dataclass schemas
│   ├── orchestrator.py # Courtroom state machine
│   ├── prompts.py      # Evaluator & judicial prompts
│   └── utils.py        # JSON helpers
├── ui/                 # React dashboard (Vite)
├── docs/
│   ├── architecture.md # Engineering decision rationale
│   └── schema.md       # Database schema reference
├── server.py           # FastAPI server & WebSocket manager
├── test_council.py     # Integration test suite
└── requirements.txt
```

---

## Installation

### 1. Clone & Python environment

```bash
git clone https://github.com/Krishanth-K/idea-council.git
cd idea-council
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Frontend

```bash
cd ui && npm install && cd ..
```

### 3. Configure LLM

By default, IdeaCouncil connects to a local Ollama instance. Override with environment variables:

```bash
export OLLAMA_HOST="http://localhost:11434"   # or your cloud provider base URL
export DEFAULT_MODEL="qwen2.5:14b"            # any OpenAI-compatible model name
```

---

## Usage

### CLI

```bash
# Single cycle: Scrape → Ideate → Debate → Judge → Save
python3 -m council.main run

# Multiple continuous cycles
python3 -m council.main run --cycles 5
```

### Running the Dashboard

```bash
# Terminal 1 — backend
python3 server.py                 # listens on http://localhost:8000

# Terminal 2 — frontend
cd ui && npm run dev              # dashboard at http://localhost:5173
```

---

## Testing

```bash
python3 test_council.py
```

Covers: model connectivity, scraper extraction, deduplication hashing, JSON schema validation, and judicial scoring logic.

---

## Documentation

- [Architecture & Engineering Decisions](docs/architecture.md)
- [Database Schema](docs/schema.md)

---

## License

MIT — see [LICENSE](LICENSE).

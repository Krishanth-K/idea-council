"""API server for IdeaCouncil UI - provides WebSocket events."""

import asyncio
import hashlib
import json
import uuid
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from council.scrape import dict_to_signal
from council.scrape.arxiv import scrape_arxiv
from council.scrape.devto import scrape_devto
from council.scrape.github import scrape_github
from council.scrape.hn import scrape_hn
from council.scrape.lobsters import scrape_lobsters
from council.models import Signal
from council.db import get_saved_ideas, init_db, is_signal_seen, mark_signal_seen

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: set = set()

    def disconnect(self, websocket):
        self.active_connections.discard(websocket)

    async def send_event(self, event: dict):
        msg = json.dumps(event)
        for connection in list(self.active_connections):
            try:
                await connection.send_text(msg)
            except Exception:
                pass


manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Dashboard event stream."""
    await websocket.accept()
    manager.active_connections.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.active_connections.discard(websocket)


# In-memory state (could be replaced with proper DB state)
class AppState:
    def __init__(self):
        self.run_id: str | None = None
        self.status: str = "idle"
        self.started_at: str | None = None
        self.completed_at: str | None = None
        self.sources: dict = {}
        self.signals: list[dict] = []
        self.active_cycle: dict | None = None
        self.saved_ideas: list[dict] = []
        self.rejected_ideas: list[dict] = []
        self.skipped_signals: list[dict] = []
        self.errors: list[dict] = []


state = AppState()


SOURCE_SCRAPERS = [
    ("GitHub", lambda max_signals: scrape_github(max_signals)),
    ("Hacker News", lambda max_signals: scrape_hn()),
    ("arXiv", lambda max_signals: scrape_arxiv(max_results=max_signals)),
    ("DEV.to", lambda max_signals: scrape_devto(max_signals)),
    ("Lobste.rs", lambda max_signals: scrape_lobsters(max_signals)),
]


def verdict_to_dict(verdict) -> dict:
    """Serialize a verdict with enough data for the dashboard and transcripts."""
    return {
        "idea_title": verdict.idea_title,
        "one_liner": verdict.one_liner,
        "scores": verdict.scores,
        "weighted_score": verdict.weighted_score,
        "save": verdict.save,
        "summary": verdict.summary,
        "debate_transcript": verdict.debate_transcript,
    }


async def emit_event(
    event_type: str,
    run_id: str,
    payload: dict,
    cycle_id: str | None = None,
    signal_id: str | None = None
):
    """Emit an event to all connected WebSocket clients."""
    event = {
        "type": event_type,
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "payload": payload,
    }
    if cycle_id:
        event["cycle_id"] = cycle_id
    if signal_id:
        event["signal_id"] = signal_id

    await manager.send_event(event)
    return event


@app.get("/api/state")
async def get_state():
    """Get current state of the run."""
    return {
        "run": {
            "run_id": state.run_id,
            "status": state.status,
            "stage": None,
            "current_signal_index": 0,
            "total_signals": len(state.signals),
            "signals_processed": len(state.saved_ideas) + len(state.rejected_ideas) + len(state.skipped_signals),
            "saved_count": len(state.saved_ideas),
            "rejected_count": len(state.rejected_ideas),
            "skipped_count": len(state.skipped_signals),
            "error_count": len(state.errors),
            "started_at": state.started_at,
            "completed_at": state.completed_at,
        },
        "sources": state.sources,
        "signals": state.signals,
        "activeCycle": state.active_cycle,
        "savedIdeas": state.saved_ideas,
        "rejectedIdeas": state.rejected_ideas,
        "skippedSignals": state.skipped_signals,
        "errors": state.errors,
    }


@app.post("/api/run")
async def start_run(request: dict):
    """Start a new council run."""
    if state.status in {"scraping", "processing"}:
        return JSONResponse(
            {"run_id": state.run_id, "status": state.status, "error": "run already in progress"},
            status_code=409,
        )

    max_signals = request.get("max_signals", 10)
    run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    asyncio.create_task(execute_run(run_id, max_signals))
    return {"run_id": run_id, "status": "started"}


async def execute_run(run_id: str, max_signals: int):
    """Run scraping and council processing while streaming dashboard events."""
    state.run_id = run_id
    state.status = "scraping"
    state.started_at = datetime.now().isoformat()
    state.completed_at = None
    state.sources = {}
    state.signals = []
    state.active_cycle = None
    state.saved_ideas = []
    state.rejected_ideas = []
    state.skipped_signals = []
    state.errors = []

    # Emit run started
    await emit_event("run_started", run_id, {"max_signals": max_signals})

    init_db()

    # Scrape and stream each source independently so the dashboard updates live.
    for source, scraper_fn in SOURCE_SCRAPERS:
        state.sources[source] = {
            "source": source,
            "status": "scraping",
            "raw_count": 0,
            "fresh_count": 0,
            "duplicate_count": 0,
            "started_at": datetime.now().isoformat(),
        }
        await emit_event("source_scrape_started", run_id, {"source": source})

        raw_signals = await asyncio.to_thread(scraper_fn, max_signals)
        source_signals = []
        duplicate_count = 0

        for raw_signal in raw_signals:
            sig = dict_to_signal(raw_signal)
            if not sig.url:
                continue

            url_hash = hashlib.sha256(sig.url.encode()).hexdigest()
            if is_signal_seen(url_hash):
                duplicate_count += 1
                continue

            mark_signal_seen(url_hash, sig.url, sig.source, sig.scraped_at)
            source_signals.append(sig)

            signal_dict = {
                "signal_id": str(uuid.uuid4()),
                "source": sig.source,
                "title": sig.title,
                "url": sig.url,
                "blurb": sig.blurb,
                "scraped_at": sig.scraped_at,
                "status": "queued",
                "queue_index": len(state.signals),
            }
            state.signals.append(signal_dict)
            await emit_event("signal_queued", run_id, signal_dict, signal_id=signal_dict["signal_id"])

        state.sources[source] = {
            "source": source,
            "status": "complete",
            "raw_count": len(raw_signals),
            "fresh_count": len(source_signals),
            "duplicate_count": duplicate_count,
            "completed_at": datetime.now().isoformat(),
        }
        await emit_event(
            "source_scrape_completed",
            run_id,
            {
                "source": source,
                "raw_count": len(raw_signals),
                "fresh_count": len(source_signals),
                "duplicate_count": duplicate_count,
            }
        )

    # Run council cycles for each signal
    state.status = "processing"
    for i, signal_dict in enumerate(state.signals):
        cycle_id = str(uuid.uuid4())
        signal_dict["status"] = "processing"
        state.active_cycle = {
            "cycle_id": cycle_id,
            "signal_id": signal_dict["signal_id"],
            "signal": signal_dict,
            "ideator": {"status": "waiting"},
            "round1": None,
            "round2": None,
            "judge": None,
        }

        await emit_event(
            "signal_processing_started",
            run_id,
            {"signal_index": i},
            cycle_id=cycle_id,
            signal_id=signal_dict["signal_id"]
        )

        # Create Signal object for orchestrator
        signal = Signal(
            source=signal_dict["source"],
            title=signal_dict["title"],
            url=signal_dict["url"],
            blurb=signal_dict["blurb"],
            scraped_at=signal_dict["scraped_at"],
        )

        # Run Ideator
        from council.main import run_ideator
        idea = run_ideator(signal)

        if idea.skip:
            state.active_cycle["ideator"] = {
                "status": "skipped",
                "skip_reason": idea.skip_reason,
                "completed_at": datetime.now().isoformat(),
            }
            signal_dict["status"] = "skipped"
            state.skipped_signals.append({
                "cycle_id": cycle_id,
                "signal_id": signal_dict["signal_id"],
                "signal": signal_dict,
                "reason": idea.skip_reason,
            })
            await emit_event(
                "ideator_skipped",
                run_id,
                {"reason": idea.skip_reason},
                cycle_id=cycle_id,
                signal_id=signal_dict["signal_id"]
            )
            continue

        state.active_cycle["ideator"] = {
            "status": "complete",
            "idea": idea.to_dict(),
            "completed_at": datetime.now().isoformat(),
        }
        await emit_event(
            "ideator_completed",
            run_id,
            {"idea": idea.to_dict()},
            cycle_id=cycle_id,
            signal_id=signal_dict["signal_id"]
        )

        # Run Round 1
        state.active_cycle["round1"] = {
            "status": "running",
            "lawyers": {},
            "started_at": datetime.now().isoformat(),
        }
        await emit_event("round_started", run_id, {"round": 1}, cycle_id=cycle_id)

        from council.main import run_round1
        round1_results = run_round1(idea)

        for dim, result in round1_results.items():
            state.active_cycle["round1"]["lawyers"][dim] = {
                "score": result["score"],
                "argument": result["argument"],
                "key_points": result["key_points"],
                "status": "complete",
            }
            await emit_event(
                "lawyer_completed",
                run_id,
                {
                    "round": 1,
                    "dimension": dim,
                    "score": result["score"],
                    "argument": result["argument"],
                    "key_points": result["key_points"],
                },
                cycle_id=cycle_id,
                signal_id=signal_dict["signal_id"]
            )

        # Run Round 2
        state.active_cycle["round2"] = {
            "status": "running",
            "lawyers": {},
            "started_at": datetime.now().isoformat(),
        }
        await emit_event("round_started", run_id, {"round": 2}, cycle_id=cycle_id)

        from council.main import run_round2
        round2_results = run_round2(idea, round1_results)

        for dim, result in round2_results.items():
            state.active_cycle["round2"]["lawyers"][dim] = {
                "original_score": round1_results[dim]["score"],
                "updated_score": result["updated_score"],
                "rebuttal": result["rebuttal"],
                "status": "complete",
            }
            await emit_event(
                "lawyer_completed",
                run_id,
                {
                    "round": 2,
                    "dimension": dim,
                    "original_score": round1_results[dim]["score"],
                    "updated_score": result["updated_score"],
                    "rebuttal": result["rebuttal"],
                },
                cycle_id=cycle_id,
                signal_id=signal_dict["signal_id"]
            )

        # Run Judge
        from council.main import run_judge
        verdict = run_judge(idea, round1_results, round2_results)
        verdict_dict = verdict_to_dict(verdict)
        state.active_cycle["judge"] = {
            "status": "complete",
            "verdict": verdict_dict,
            "completed_at": datetime.now().isoformat(),
        }

        await emit_event(
            "judge_completed",
            run_id,
            {"verdict": verdict_dict},
            cycle_id=cycle_id,
            signal_id=signal_dict["signal_id"]
        )

        if verdict.save:
            await emit_event(
                "verdict_saved",
                run_id,
                {"verdict": verdict_dict},
                cycle_id=cycle_id,
                signal_id=signal_dict["signal_id"]
            )
            signal_dict["status"] = "saved"
            state.saved_ideas.append({
                "cycle_id": cycle_id,
                "signal_id": signal_dict["signal_id"],
                "signal": signal_dict,
                "idea": idea.to_dict(),
                "verdict": verdict_dict,
            })
        else:
            await emit_event(
                "verdict_rejected",
                run_id,
                {"verdict": verdict_dict},
                cycle_id=cycle_id,
                signal_id=signal_dict["signal_id"]
            )
            signal_dict["status"] = "rejected"
            state.rejected_ideas.append({
                "cycle_id": cycle_id,
                "signal_id": signal_dict["signal_id"],
                "signal": signal_dict,
                "idea": idea.to_dict(),
                "verdict": verdict_dict,
            })

        await emit_event("cycle_completed", run_id, {}, cycle_id=cycle_id, signal_id=signal_dict["signal_id"])

    state.status = "complete"
    state.completed_at = datetime.now().isoformat()
    await emit_event("run_completed", run_id, {})


if __name__ == "__main__":
    import uvicorn

    # Start FastAPI server
    uvicorn.run(app, host="0.0.0.0", port=8000)

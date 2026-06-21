"""API server for IdeaCouncil UI - provides WebSocket events."""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any

import fastapi
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
import websockets

from council.scrape import scrape_all
from council.orchestrator import run_council_cycle
from council.models import Signal, CycleState, Idea, Verdict
from council.db import get_saved_ideas

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# WebSocket connection manager using websockets library
class ConnectionManager:
    def __init__(self):
        self.active_connections: set = set()

    def disconnect(self, websocket):
        self.active_connections.discard(websocket)

    async def send_event(self, event: dict):
        msg = json.dumps(event)
        for connection in list(self.active_connections):
            try:
                await connection.send(msg)
            except Exception:
                pass


manager = ConnectionManager()


# WebSocket server using websockets library
async def websocket_server(websocket):
    """Standalone WebSocket server."""
    # websockets library auto-accepts the connection
    manager.active_connections.add(websocket)
    try:
        async for message in websocket:
            # Handle client messages if needed
            pass
    except Exception:
        pass
    finally:
        manager.active_connections.discard(websocket)


# In-memory state (could be replaced with proper DB state)
class AppState:
    def __init__(self):
        self.run_id: str | None = None
        self.sources: dict = {}
        self.signals: list[dict] = []
        self.active_cycle: dict | None = None
        self.saved_ideas: list[dict] = []
        self.rejected_ideas: list[dict] = []
        self.skipped_signals: list[dict] = []
        self.errors: list[dict] = []


state = AppState()


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
            "status": "idle" if not state.run_id else "processing",
            "stage": None,
            "current_signal_index": 0,
            "total_signals": len(state.signals),
            "signals_processed": len(state.saved_ideas) + len(state.rejected_ideas) + len(state.skipped_signals),
            "saved_count": len(state.saved_ideas),
            "rejected_count": len(state.rejected_ideas),
            "skipped_count": len(state.skipped_signals),
            "error_count": len(state.errors),
        },
        "sources": state.sources,
        "signals": state.signals,
        "savedIdeas": state.saved_ideas,
        "rejectedIdeas": state.rejected_ideas,
    }


@app.post("/api/run")
async def start_run(request: dict):
    """Start a new council run."""
    max_signals = request.get("max_signals", 10)
    run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    state.run_id = run_id
    state.sources = {}
    state.signals = []
    state.saved_ideas = []
    state.rejected_ideas = []
    state.skipped_signals = []
    state.errors = []

    # Emit run started
    await emit_event("run_started", run_id, {"max_signals": max_signals})

    # Scrape signals
    signals = scrape_all(max_per_source=max_signals)

    # Process each source
    for source in ["github", "hacker_news", "arxiv", "devto", "lobsters"]:
        source_signals = [s for s in signals if s.source == source]
        await emit_event(
            "source_scrape_completed",
            run_id,
            {
                "source": source,
                "raw_count": len(source_signals),
                "fresh_count": len(source_signals),
                "duplicate_count": 0,
            }
        )

        for sig in source_signals:
            signal_dict = {
                "signal_id": str(uuid.uuid4()),
                "source": sig.source,
                "title": sig.title,
                "url": sig.url,
                "blurb": sig.blurb,
                "scraped_at": sig.scraped_at,
                "status": "queued",
            }
            await emit_event("signal_queued", run_id, signal_dict, signal_id=signal_dict["signal_id"])
            state.signals.append(signal_dict)

    # Run council cycles for each signal
    for i, signal_dict in enumerate(state.signals):
        cycle_id = str(uuid.uuid4())

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
            await emit_event(
                "ideator_skipped",
                run_id,
                {"reason": idea.skip_reason},
                cycle_id=cycle_id,
                signal_id=signal_dict["signal_id"]
            )
            state.skipped_signals.append({"signal": signal_dict, "reason": idea.skip_reason})
            continue

        await emit_event(
            "ideator_completed",
            run_id,
            {"idea": idea.to_dict()},
            cycle_id=cycle_id,
            signal_id=signal_dict["signal_id"]
        )

        # Run Round 1
        await emit_event("round_started", run_id, {"round": 1}, cycle_id=cycle_id)

        from council.main import run_round1
        round1_results = run_round1(idea)

        for dim, result in round1_results.items():
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
        await emit_event("round_started", run_id, {"round": 2}, cycle_id=cycle_id)

        from council.main import run_round2
        round2_results = run_round2(idea, round1_results)

        for dim, result in round2_results.items():
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

        await emit_event(
            "judge_completed",
            run_id,
            {
                "verdict": {
                    "idea_title": verdict.idea_title,
                    "one_liner": verdict.one_liner,
                    "scores": verdict.scores,
                    "weighted_score": verdict.weighted_score,
                    "save": verdict.save,
                    "summary": verdict.summary,
                }
            },
            cycle_id=cycle_id,
            signal_id=signal_dict["signal_id"]
        )

        if verdict.save:
            await emit_event(
                "verdict_saved",
                run_id,
                {"verdict": {"idea_title": verdict.idea_title, "weighted_score": verdict.weighted_score}},
                cycle_id=cycle_id,
                signal_id=signal_dict["signal_id"]
            )
            state.saved_ideas.append({
                "cycle_id": cycle_id,
                "signal_id": signal_dict["signal_id"],
                "verdict": {"idea_title": verdict.idea_title, "weighted_score": verdict.weighted_score},
            })
        else:
            await emit_event(
                "verdict_rejected",
                run_id,
                {"verdict": {"idea_title": verdict.idea_title, "weighted_score": verdict.weighted_score}},
                cycle_id=cycle_id,
                signal_id=signal_dict["signal_id"]
            )
            state.rejected_ideas.append({
                "cycle_id": cycle_id,
                "signal_id": signal_dict["signal_id"],
                "verdict": {"idea_title": verdict.idea_title, "weighted_score": verdict.weighted_score},
            })

        await emit_event("cycle_completed", run_id, {}, cycle_id=cycle_id, signal_id=signal_dict["signal_id"])

    await emit_event("run_completed", run_id, {})

    return {"run_id": run_id, "status": "complete"}


if __name__ == "__main__":
    import uvicorn
    import threading

    # Start WebSocket server in a separate thread
    async def start_ws_server():
        async with websockets.serve(websocket_server, "0.0.0.0", 8001):
            print("WebSocket server running on ws://0.0.0.0:8001")
            await asyncio.Future()  # run forever

    ws_thread = threading.Thread(target=lambda: asyncio.run(start_ws_server()))
    ws_thread.daemon = True
    ws_thread.start()

    # Start FastAPI server
    uvicorn.run(app, host="0.0.0.0", port=8000)
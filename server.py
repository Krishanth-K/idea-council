"""API server for IdeaCouncil UI - provides WebSocket events."""

import asyncio
import json
import os
import uuid
from datetime import datetime

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from council.core import DEFAULT_MODEL, OLLAMA_HOST
from council.orchestrator import run_ideator, run_judge, run_round1, run_round2
from council.scrape import scrape_all, signal_to_dict
from council.db import (
    get_saved_ideas, init_db, save_signal, save_idea,
    save_lawyer_statement, save_verdict
)

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


async def check_llm_connection() -> dict:
    """Check whether the configured Ollama endpoint is reachable."""
    headers = {}
    api_key = os.getenv("OLLAMA_API_KEY", "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(f"{OLLAMA_HOST.rstrip('/')}/api/tags", headers=headers)
        response.raise_for_status()

    return {
        "provider": "ollama",
        "host": OLLAMA_HOST,
        "model": DEFAULT_MODEL,
    }


async def _emit_cycle_error(
    run_id: str,
    cycle_id: str,
    signal_dict: dict,
    stage: str,
    message: str,
):
    """Record a cycle failure and notify connected clients."""
    error = {
        "error_id": str(uuid.uuid4()),
        "stage": stage,
        "message": message,
        "created_at": datetime.now().isoformat(),
    }
    state.errors.append(error)
    signal_dict["status"] = "error"
    await emit_event(
        "cycle_failed",
        run_id,
        {"stage": stage, "error": message},
        cycle_id=cycle_id,
        signal_id=signal_dict["signal_id"],
    )


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


@app.post("/api/run/stop")
async def stop_run():
    """Stop the current run."""
    if state.status == "idle":
        return {"status": "idle", "message": "no run in progress"}

    state.status = "stopping"
    return {"status": "stopping", "message": "stopping run..."}


@app.post("/api/run/start-scraping")
async def start_scraping(request: dict):
    """Start scraping phase only."""
    if state.status in {"scraping", "processing"}:
        return JSONResponse(
            {"run_id": state.run_id, "status": state.status, "error": "run already in progress"},
            status_code=409,
        )

    max_signals = request.get("max_signals", 10)
    run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    asyncio.create_task(execute_scraping(run_id, max_signals))
    return {"run_id": run_id, "status": "started", "section": "scraping"}


@app.post("/api/run/start-ideator")
async def start_ideator(request: dict):
    """Start ideator phase only (requires signals to exist)."""
    if state.status in {"scraping", "processing"}:
        return JSONResponse(
            {"run_id": state.run_id, "status": state.status, "error": "run already in progress"},
            status_code=409,
        )

    if not state.signals:
        return JSONResponse(
            {"error": "no signals available - run scraping first"},
            status_code=400,
        )

    run_id = state.run_id or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    asyncio.create_task(execute_ideator_phase(run_id))
    return {"run_id": run_id, "status": "started", "section": "ideator"}


@app.post("/api/run/start-round1")
async def start_round1(request: dict):
    """Start round 1 phase only (requires ideas to exist)."""
    if state.status in {"scraping", "processing"}:
        return JSONResponse(
            {"run_id": state.run_id, "status": state.status, "error": "run already in progress"},
            status_code=409,
        )

    # Check if we have at least one signal with a completed idea
    signals_with_ideas = [s for s in state.signals if s.get("status") == "processing" and s.get("idea")]
    if not signals_with_ideas:
        return JSONResponse(
            {"error": "no ideas available - run ideator phase first"},
            status_code=400,
        )

    run_id = state.run_id or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    asyncio.create_task(execute_round1_phase(run_id))
    return {"run_id": run_id, "status": "started", "section": "round1"}


@app.post("/api/run/start-round2")
async def start_round2(request: dict):
    """Start round 2 phase only (requires round 1 to complete)."""
    if state.status in {"scraping", "processing"}:
        return JSONResponse(
            {"run_id": state.run_id, "status": state.status, "error": "run already in progress"},
            status_code=409,
        )

    run_id = state.run_id or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    asyncio.create_task(execute_round2_phase(run_id))
    return {"run_id": run_id, "status": "started", "section": "round2"}


async def execute_run(run_id: str, max_signals: int):
    """Run scraping and council processing while streaming dashboard events."""
    try:
        await _execute_run(run_id, max_signals)
    except Exception as exc:
        error = {
            "error_id": str(uuid.uuid4()),
            "stage": "run",
            "message": str(exc),
            "created_at": datetime.now().isoformat(),
        }
        state.errors.append(error)
        state.status = "failed"
        state.completed_at = datetime.now().isoformat()
        await emit_event("run_failed", run_id, {"error": str(exc)})


async def _execute_run(run_id: str, max_signals: int):
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

    # Scrape each source and emit events for dashboard updates
    # Import scrapers here to avoid import-time issues
    from council.scrape import (
        scrape_github, scrape_hn, scrape_arxiv,
        scrape_devto, scrape_lobsters, dict_to_signal
    )
    from council.db import is_signal_seen, mark_signal_seen

    source_scrapers = [
        ("GitHub", lambda: scrape_github(max_signals)),
        ("Hacker News", lambda: scrape_hn()),
        ("arXiv", lambda: scrape_arxiv(max_results=max_signals)),
        ("DEV.to", lambda: scrape_devto(max_signals)),
        ("Lobste.rs", lambda: scrape_lobsters(max_signals)),
    ]

    for source, scraper_fn in source_scrapers:
        state.sources[source] = {
            "source": source,
            "status": "scraping",
            "raw_count": 0,
            "fresh_count": 0,
            "duplicate_count": 0,
            "started_at": datetime.now().isoformat(),
        }
        await emit_event("source_scrape_started", run_id, {"source": source})

        raw_signals = await asyncio.to_thread(scraper_fn)
        source_signals = []
        duplicate_count = 0

        for raw_signal in raw_signals:
            sig = dict_to_signal(raw_signal)
            if not sig.url:
                continue

            url_hash = sig.url_hash()
            if is_signal_seen(url_hash):
                duplicate_count += 1
                continue

            mark_signal_seen(url_hash, sig.url, sig.source, sig.scraped_at)
            db_signal_id = save_signal(sig)
            source_signals.append(sig)

            signal_dict = signal_to_dict(sig, str(uuid.uuid4()), len(state.signals))
            signal_dict["db_signal_id"] = db_signal_id
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
        from council.scrape import dict_to_signal_from_dict
        signal = dict_to_signal_from_dict(signal_dict)

        # Run Ideator
        state.active_cycle["ideator"] = {
            "status": "connecting",
            "provider": "ollama",
            "host": OLLAMA_HOST,
            "model": DEFAULT_MODEL,
            "started_at": datetime.now().isoformat(),
        }
        await emit_event(
            "ideator_started",
            run_id,
            {
                "status": "connecting",
                "provider": "ollama",
                "host": OLLAMA_HOST,
                "model": DEFAULT_MODEL,
            },
            cycle_id=cycle_id,
            signal_id=signal_dict["signal_id"]
        )

        try:
            llm = await check_llm_connection()
        except Exception as exc:
            error = {
                "error_id": str(uuid.uuid4()),
                "stage": "ideator",
                "message": f"LLM connection failed: {exc}",
                "created_at": datetime.now().isoformat(),
            }
            state.errors.append(error)
            state.active_cycle["ideator"] = {
                "status": "failed",
                "error": error["message"],
                "completed_at": datetime.now().isoformat(),
            }
            signal_dict["status"] = "error"
            await emit_event(
                "ideator_failed",
                run_id,
                {"error": error["message"]},
                cycle_id=cycle_id,
                signal_id=signal_dict["signal_id"]
            )
            continue

        state.active_cycle["ideator"] = {
            "status": "thinking",
            **llm,
            "started_at": datetime.now().isoformat(),
        }
        await emit_event(
            "ideator_thinking",
            run_id,
            llm,
            cycle_id=cycle_id,
            signal_id=signal_dict["signal_id"]
        )

        try:
            idea = await asyncio.to_thread(run_ideator, signal)
            db_idea_id = save_idea(signal_dict["db_signal_id"], idea)
            signal_dict["db_idea_id"] = db_idea_id
        except Exception as exc:
            error = {
                "error_id": str(uuid.uuid4()),
                "stage": "ideator",
                "message": f"Ideator failed: {exc}",
                "created_at": datetime.now().isoformat(),
            }
            state.errors.append(error)
            state.active_cycle["ideator"] = {
                "status": "failed",
                "error": error["message"],
                "completed_at": datetime.now().isoformat(),
            }
            signal_dict["status"] = "error"
            await emit_event(
                "ideator_failed",
                run_id,
                {"error": error["message"]},
                cycle_id=cycle_id,
                signal_id=signal_dict["signal_id"]
            )
            continue

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

        try:
            round1_results = await asyncio.to_thread(run_round1, idea)
            # Save Round 1 lawyer statements to DB
            for dim, result in round1_results.items():
                save_lawyer_statement(
                    idea_id=db_idea_id,
                    dimension=dim,
                    round_num=1,
                    score=result["score"],
                    argument=result["argument"],
                    key_points=result["key_points"]
                )
        except Exception as exc:
            await _emit_cycle_error(
                run_id, cycle_id, signal_dict, "round1", f"Round 1 failed: {exc}"
            )
            continue

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

        try:
            round2_results = await asyncio.to_thread(run_round2, idea, round1_results)
            # Save Round 2 lawyer statements to DB
            for dim, result in round2_results.items():
                save_lawyer_statement(
                    idea_id=db_idea_id,
                    dimension=dim,
                    round_num=2,
                    score=result["updated_score"],
                    argument=result["rebuttal"]
                )
        except Exception as exc:
            await _emit_cycle_error(
                run_id, cycle_id, signal_dict, "round2", f"Round 2 failed: {exc}"
            )
            continue

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
        try:
            verdict = await asyncio.to_thread(run_judge, idea, round1_results, round2_results)
            # Save Verdict to DB (both saved and rejected)
            save_verdict(verdict, verdict.debate_transcript, saved=1 if verdict.save else 0, idea_id=db_idea_id)
        except Exception as exc:
            await _emit_cycle_error(
                run_id, cycle_id, signal_dict, "judge", f"Judge failed: {exc}"
            )
            continue

        verdict_dict = verdict.to_dict()
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


async def execute_scraping(run_id: str, max_signals: int):
    """Execute scraping phase only."""
    try:
        await _execute_scraping(run_id, max_signals)
    except Exception as exc:
        if state.status != "stopping":
            error = {
                "error_id": str(uuid.uuid4()),
                "stage": "scraping",
                "message": str(exc),
                "created_at": datetime.now().isoformat(),
            }
            state.errors.append(error)
            state.status = "failed"
            await emit_event("run_failed", run_id, {"error": str(exc)})


async def _execute_scraping(run_id: str, max_signals: int):
    """Scrape sources and queue signals."""
    state.run_id = run_id
    state.status = "scraping"
    state.started_at = datetime.now().isoformat()
    state.completed_at = None
    state.sources = {}
    state.signals = []
    state.errors = []

    await emit_event("run_started", run_id, {"max_signals": max_signals, "section": "scraping"})

    init_db()

    # Import scrapers here to avoid import-time issues
    from council.scrape import (
        scrape_github, scrape_hn, scrape_arxiv,
        scrape_devto, scrape_lobsters, dict_to_signal
    )
    from council.db import is_signal_seen, mark_signal_seen

    source_scrapers = [
        ("GitHub", lambda: scrape_github(max_signals)),
        ("Hacker News", lambda: scrape_hn()),
        ("arXiv", lambda: scrape_arxiv(max_results=max_signals)),
        ("DEV.to", lambda: scrape_devto(max_signals)),
        ("Lobste.rs", lambda: scrape_lobsters(max_signals)),
    ]

    for source, scraper_fn in source_scrapers:
        if state.status == "stopping":
            await emit_event("run_stopped", run_id, {"section": "scraping"})
            state.status = "idle"
            return

        state.sources[source] = {
            "source": source,
            "status": "scraping",
            "raw_count": 0,
            "fresh_count": 0,
            "duplicate_count": 0,
            "started_at": datetime.now().isoformat(),
        }
        await emit_event("source_scrape_started", run_id, {"source": source})

        raw_signals = await asyncio.to_thread(scraper_fn)
        source_signals = []
        duplicate_count = 0

        for raw_signal in raw_signals:
            if state.status == "stopping":
                await emit_event("run_stopped", run_id, {"section": "scraping"})
                state.status = "idle"
                return

            sig = dict_to_signal(raw_signal)
            if not sig.url:
                continue

            url_hash = sig.url_hash()
            if is_signal_seen(url_hash):
                duplicate_count += 1
                continue

            mark_signal_seen(url_hash, sig.url, sig.source, sig.scraped_at)
            db_signal_id = save_signal(sig)
            source_signals.append(sig)

            signal_dict = signal_to_dict(sig, str(uuid.uuid4()), len(state.signals))
            signal_dict["db_signal_id"] = db_signal_id
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

    state.status = "idle"
    state.completed_at = datetime.now().isoformat()
    await emit_event("section_completed", run_id, {"section": "scraping"})


async def execute_ideator_phase(run_id: str):
    """Execute ideator phase only."""
    try:
        await _execute_ideator(run_id)
    except Exception as exc:
        if state.status != "stopping":
            error = {
                "error_id": str(uuid.uuid4()),
                "stage": "ideator",
                "message": str(exc),
                "created_at": datetime.now().isoformat(),
            }
            state.errors.append(error)
            state.status = "failed"
            await emit_event("run_failed", run_id, {"error": str(exc)})


async def _execute_ideator(run_id: str):
    """Run ideator for each signal that doesn't have an idea yet."""
    state.status = "processing"
    state.run_id = run_id

    await emit_event("section_started", run_id, {"section": "ideator"})

    # Find signals that need ideator processing (queued or need retry)
    pending_signals = [s for s in state.signals if s.get("status") in {"queued", "processing"}]

    for i, signal_dict in enumerate(pending_signals):
        if state.status == "stopping":
            await emit_event("run_stopped", run_id, {"section": "ideator"})
            state.status = "idle"
            return

        # Skip if already has an idea
        if signal_dict.get("idea"):
            continue

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

        from council.scrape import dict_to_signal_from_dict
        signal = dict_to_signal_from_dict(signal_dict)

        # Run Ideator
        state.active_cycle["ideator"] = {
            "status": "connecting",
            "provider": "ollama",
            "host": OLLAMA_HOST,
            "model": DEFAULT_MODEL,
            "started_at": datetime.now().isoformat(),
        }
        await emit_event(
            "ideator_started",
            run_id,
            {"status": "connecting", "provider": "ollama", "host": OLLAMA_HOST, "model": DEFAULT_MODEL},
            cycle_id=cycle_id,
            signal_id=signal_dict["signal_id"]
        )

        try:
            llm = await check_llm_connection()
        except Exception as exc:
            error = {
                "error_id": str(uuid.uuid4()),
                "stage": "ideator",
                "message": f"LLM connection failed: {exc}",
                "created_at": datetime.now().isoformat(),
            }
            state.errors.append(error)
            state.active_cycle["ideator"] = {"status": "failed", "error": error["message"], "completed_at": datetime.now().isoformat()}
            signal_dict["status"] = "error"
            await emit_event("ideator_failed", run_id, {"error": error["message"]}, cycle_id=cycle_id, signal_id=signal_dict["signal_id"])
            continue

        state.active_cycle["ideator"] = {"status": "thinking", **llm, "started_at": datetime.now().isoformat()}
        await emit_event("ideator_thinking", run_id, llm, cycle_id=cycle_id, signal_id=signal_dict["signal_id"])

        try:
            idea = await asyncio.to_thread(run_ideator, signal)
            db_signal_id = signal_dict.get("db_signal_id") or save_signal(signal)
            db_idea_id = save_idea(db_signal_id, idea)
            signal_dict["db_signal_id"] = db_signal_id
            signal_dict["db_idea_id"] = db_idea_id
        except Exception as exc:
            error = {
                "error_id": str(uuid.uuid4()),
                "stage": "ideator",
                "message": f"Ideator failed: {exc}",
                "created_at": datetime.now().isoformat(),
            }
            state.errors.append(error)
            state.active_cycle["ideator"] = {"status": "failed", "error": error["message"], "completed_at": datetime.now().isoformat()}
            signal_dict["status"] = "error"
            await emit_event("ideator_failed", run_id, {"error": error["message"]}, cycle_id=cycle_id, signal_id=signal_dict["signal_id"])
            continue

        if idea.skip:
            state.active_cycle["ideator"] = {"status": "skipped", "skip_reason": idea.skip_reason, "completed_at": datetime.now().isoformat()}
            signal_dict["status"] = "skipped"
            state.skipped_signals.append({"cycle_id": cycle_id, "signal_id": signal_dict["signal_id"], "signal": signal_dict, "reason": idea.skip_reason})
            await emit_event("ideator_skipped", run_id, {"reason": idea.skip_reason}, cycle_id=cycle_id, signal_id=signal_dict["signal_id"])
            continue

        state.active_cycle["ideator"] = {"status": "complete", "idea": idea.to_dict(), "completed_at": datetime.now().isoformat()}
        signal_dict["idea"] = idea.to_dict()
        await emit_event("ideator_completed", run_id, {"idea": idea.to_dict()}, cycle_id=cycle_id, signal_id=signal_dict["signal_id"])

    state.status = "idle"
    await emit_event("section_completed", run_id, {"section": "ideator"})


async def execute_round1_phase(run_id: str):
    """Execute round 1 phase only."""
    try:
        await _execute_round1(run_id)
    except Exception as exc:
        if state.status != "stopping":
            error = {
                "error_id": str(uuid.uuid4()),
                "stage": "round1",
                "message": str(exc),
                "created_at": datetime.now().isoformat(),
            }
            state.errors.append(error)
            state.status = "failed"
            await emit_event("run_failed", run_id, {"error": str(exc)})


async def _execute_round1(run_id: str):
    """Run round 1 for signals that have ideas but no round1."""
    state.status = "processing"
    state.run_id = run_id

    await emit_event("section_started", run_id, {"section": "round1"})

    # Find signals with ideas but no round1
    signals_with_ideas = [s for s in state.signals if s.get("idea") and not s.get("round1")]

    for i, signal_dict in enumerate(signals_with_ideas):
        if state.status == "stopping":
            await emit_event("run_stopped", run_id, {"section": "round1"})
            state.status = "idle"
            return

        cycle_id = str(uuid.uuid4())
        signal_dict["status"] = "processing"
        idea_dict = signal_dict["idea"]

        state.active_cycle = {
            "cycle_id": cycle_id,
            "signal_id": signal_dict["signal_id"],
            "signal": signal_dict,
            "ideator": {"status": "complete", "idea": idea_dict},
            "round1": None,
            "round2": None,
            "judge": None,
        }

        await emit_event("signal_processing_started", run_id, {"signal_index": i}, cycle_id=cycle_id, signal_id=signal_dict["signal_id"])
        await emit_event("ideator_completed", run_id, {"idea": idea_dict}, cycle_id=cycle_id, signal_id=signal_dict["signal_id"])

        # Run Round 1
        state.active_cycle["round1"] = {"status": "running", "lawyers": {}, "started_at": datetime.now().isoformat()}
        await emit_event("round_started", run_id, {"round": 1}, cycle_id=cycle_id)

        try:
            from council.models import Idea
            idea = Idea.from_dict(idea_dict)
            db_idea_id = signal_dict.get("db_idea_id")
            if not db_idea_id:
                from council.scrape import dict_to_signal_from_dict
                db_signal_id = signal_dict.get("db_signal_id") or save_signal(dict_to_signal_from_dict(signal_dict))
                db_idea_id = save_idea(db_signal_id, idea)
                signal_dict["db_signal_id"] = db_signal_id
                signal_dict["db_idea_id"] = db_idea_id

            round1_results = await asyncio.to_thread(run_round1, idea)
            for dim, result in round1_results.items():
                save_lawyer_statement(
                    idea_id=db_idea_id,
                    dimension=dim,
                    round_num=1,
                    score=result["score"],
                    argument=result["argument"],
                    key_points=result["key_points"]
                )
        except Exception as exc:
            await _emit_cycle_error(run_id, cycle_id, signal_dict, "round1", f"Round 1 failed: {exc}")
            continue

        signal_dict["round1"] = round1_results
        for dim, result in round1_results.items():
            state.active_cycle["round1"]["lawyers"][dim] = {"score": result["score"], "argument": result["argument"], "key_points": result["key_points"], "status": "complete"}
            await emit_event("lawyer_completed", run_id, {"round": 1, "dimension": dim, "score": result["score"], "argument": result["argument"], "key_points": result["key_points"]}, cycle_id=cycle_id, signal_id=signal_dict["signal_id"])

    state.status = "idle"
    await emit_event("section_completed", run_id, {"section": "round1"})


async def execute_round2_phase(run_id: str):
    """Execute round 2 phase only."""
    try:
        await _execute_round2(run_id)
    except Exception as exc:
        if state.status != "stopping":
            error = {
                "error_id": str(uuid.uuid4()),
                "stage": "round2",
                "message": str(exc),
                "created_at": datetime.now().isoformat(),
            }
            state.errors.append(error)
            state.status = "failed"
            await emit_event("run_failed", run_id, {"error": str(exc)})


async def _execute_round2(run_id: str):
    """Run round 2 for signals that have round1 but no round2."""
    state.status = "processing"
    state.run_id = run_id

    await emit_event("section_started", run_id, {"section": "round2"})

    # Find signals with round1 but no round2
    signals_with_round1 = [s for s in state.signals if s.get("round1") and not s.get("round2")]

    for i, signal_dict in enumerate(signals_with_round1):
        if state.status == "stopping":
            await emit_event("run_stopped", run_id, {"section": "round2"})
            state.status = "idle"
            return

        cycle_id = str(uuid.uuid4())
        signal_dict["status"] = "processing"
        idea_dict = signal_dict["idea"]
        round1_results = signal_dict["round1"]

        state.active_cycle = {
            "cycle_id": cycle_id,
            "signal_id": signal_dict["signal_id"],
            "signal": signal_dict,
            "ideator": {"status": "complete", "idea": idea_dict},
            "round1": {"status": "complete", "lawyers": round1_results},
            "round2": None,
            "judge": None,
        }

        await emit_event("signal_processing_started", run_id, {"signal_index": i}, cycle_id=cycle_id, signal_id=signal_dict["signal_id"])
        await emit_event("ideator_completed", run_id, {"idea": idea_dict}, cycle_id=cycle_id, signal_id=signal_dict["signal_id"])
        await emit_event("round_started", run_id, {"round": 1}, cycle_id=cycle_id)
        for dim, result in round1_results.items():
            await emit_event("lawyer_completed", run_id, {"round": 1, "dimension": dim, "score": result["score"], "argument": result["argument"], "key_points": result.get("key_points", [])}, cycle_id=cycle_id, signal_id=signal_dict["signal_id"])

        # Run Round 2
        state.active_cycle["round2"] = {"status": "running", "lawyers": {}, "started_at": datetime.now().isoformat()}
        await emit_event("round_started", run_id, {"round": 2}, cycle_id=cycle_id)

        try:
            from council.models import Idea
            idea = Idea.from_dict(idea_dict)
            db_idea_id = signal_dict.get("db_idea_id")
            if not db_idea_id:
                from council.scrape import dict_to_signal_from_dict
                db_signal_id = signal_dict.get("db_signal_id") or save_signal(dict_to_signal_from_dict(signal_dict))
                db_idea_id = save_idea(db_signal_id, idea)
                signal_dict["db_signal_id"] = db_signal_id
                signal_dict["db_idea_id"] = db_idea_id

            round2_results = await asyncio.to_thread(run_round2, idea, round1_results)
            for dim, result in round2_results.items():
                save_lawyer_statement(
                    idea_id=db_idea_id,
                    dimension=dim,
                    round_num=2,
                    score=result["updated_score"],
                    argument=result["rebuttal"]
                )

            # Run and save Judge verdict
            verdict = await asyncio.to_thread(run_judge, idea, round1_results, round2_results)
            save_verdict(verdict, verdict.debate_transcript, saved=1 if verdict.save else 0, idea_id=db_idea_id)

            verdict_dict = verdict.to_dict()
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

        except Exception as exc:
            await _emit_cycle_error(run_id, cycle_id, signal_dict, "round2", f"Round 2/Judge failed: {exc}")
            continue

        signal_dict["round2"] = round2_results
        for dim, result in round2_results.items():
            state.active_cycle["round2"]["lawyers"][dim] = {"original_score": round1_results[dim]["score"], "updated_score": result["updated_score"], "rebuttal": result["rebuttal"], "status": "complete"}
            await emit_event("lawyer_completed", run_id, {"round": 2, "dimension": dim, "original_score": round1_results[dim]["score"], "updated_score": result["updated_score"], "rebuttal": result["rebuttal"]}, cycle_id=cycle_id, signal_id=signal_dict["signal_id"])

    state.status = "idle"
    await emit_event("section_completed", run_id, {"section": "round2"})


if __name__ == "__main__":
    import uvicorn

    # Start FastAPI server
    uvicorn.run(app, host="0.0.0.0", port=8000)

"""API server for IdeaCouncil — thin routing bridge only.

Responsibilities
----------------
- Accept HTTP requests and WebSocket connections.
- Validate that a run is not already in progress.
- Delegate all work to functions in ``council.phases``.
- Read (never write) ``council.state.state`` to serve /api/state.

No business logic lives here.
"""

import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from council.phases import (
    run_full,
    run_scraping,
    run_ideator_phase,
    run_round1_phase,
    run_round2_phase,
)
from council.server.events import manager, emit_event
from council.state import state, new_run_id, PrerequisiteError

app = FastAPI(title="IdeaCouncil API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup() -> None:
    """Initialise the database once when the server starts."""
    from council.db import init_db
    init_db()


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
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


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

@app.get("/api/state")
async def get_state() -> dict:
    """Return current run state for the dashboard."""
    return {
        "run": {
            "run_id": state.run_id,
            "status": state.status,
            "stage": None,
            "current_signal_index": 0,
            "total_signals": len(state.signals),
            "signals_processed": (
                len(state.saved_ideas)
                + len(state.rejected_ideas)
                + len(state.skipped_signals)
            ),
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


# ---------------------------------------------------------------------------
# Run control
# ---------------------------------------------------------------------------

@app.post("/api/run")
async def start_run(request: dict) -> dict:
    """Start a full pipeline run (scrape → ideate → debate → judge)."""
    if state.is_busy():
        return JSONResponse(
            {"run_id": state.run_id, "status": state.status,
             "error": "run already in progress"},
            status_code=409,
        )
    run_id = new_run_id()
    asyncio.create_task(
        run_full(run_id, request.get("max_signals", 10), on_event=emit_event)
    )
    return {"run_id": run_id, "status": "started"}


@app.post("/api/run/stop")
async def stop_run() -> dict:
    """Request a graceful stop of the current run."""
    if not state.is_busy():
        return {"status": state.status, "message": "no run in progress"}
    state.request_stop()
    return {"status": "stopping", "message": "stopping run…"}


@app.post("/api/run/scrape")
async def start_scraping(request: dict) -> dict:
    """Start the scraping phase only."""
    if state.is_busy():
        return JSONResponse(
            {"run_id": state.run_id, "status": state.status,
             "error": "run already in progress"},
            status_code=409,
        )
    run_id = new_run_id()
    asyncio.create_task(
        run_scraping(run_id, request.get("max_signals", 10), on_event=emit_event)
    )
    return {"run_id": run_id, "status": "started", "section": "scraping"}


@app.post("/api/run/ideator")
async def start_ideator(request: dict) -> dict:
    """Start the ideator phase (requires signals from scraping)."""
    if state.is_busy():
        return JSONResponse(
            {"run_id": state.run_id, "status": state.status,
             "error": "run already in progress"},
            status_code=409,
        )
    try:
        run_id = state.run_id or new_run_id()
        asyncio.create_task(run_ideator_phase(run_id, on_event=emit_event))
        return {"run_id": run_id, "status": "started", "section": "ideator"}
    except PrerequisiteError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.post("/api/run/round1")
async def start_round1(request: dict) -> dict:
    """Start Round 1 (requires completed ideas from ideator)."""
    if state.is_busy():
        return JSONResponse(
            {"run_id": state.run_id, "status": state.status,
             "error": "run already in progress"},
            status_code=409,
        )
    try:
        run_id = state.run_id or new_run_id()
        asyncio.create_task(run_round1_phase(run_id, on_event=emit_event))
        return {"run_id": run_id, "status": "started", "section": "round1"}
    except PrerequisiteError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.post("/api/run/round2")
async def start_round2(request: dict) -> dict:
    """Start Round 2 + Judge (requires completed Round 1)."""
    if state.is_busy():
        return JSONResponse(
            {"run_id": state.run_id, "status": state.status,
             "error": "run already in progress"},
            status_code=409,
        )
    try:
        run_id = state.run_id or new_run_id()
        asyncio.create_task(run_round2_phase(run_id, on_event=emit_event))
        return {"run_id": run_id, "status": "started", "section": "round2"}
    except PrerequisiteError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


# ---------------------------------------------------------------------------
# Entry point (dev only)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("council.server.server:app", host="0.0.0.0", port=8000, reload=True)

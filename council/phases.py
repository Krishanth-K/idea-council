"""
council/phases.py
=================
Core phase logic for IdeaCouncil.  Each public function maps to one UI action.

Design rules
------------
- No imports from ``council.server.*`` — this module is server-agnostic.
- State is read/written via the ``council.state.state`` singleton.
- WebSocket events are emitted through the ``on_event`` callback (optional).
  When ``on_event`` is None the phase still runs; events are just not sent.
- Prerequisite failures raise ``PrerequisiteError`` so callers can translate
  them to appropriate HTTP 400 responses.
"""

import asyncio
import os
import uuid
from datetime import datetime
from typing import Callable, Awaitable

import httpx

from council.core import DEFAULT_MODEL, OLLAMA_HOST
from council.db import (
    init_db, save_signal, save_idea,
    save_lawyer_statement, save_verdict,
)
from council.models import Idea
from council.orchestrator import run_ideator, run_round1, run_round2, run_judge
from council.scrape import signal_to_dict
from council.state import state, PrerequisiteError

# ---------------------------------------------------------------------------
# Type alias for the event callback
# ---------------------------------------------------------------------------
OnEvent = Callable[..., Awaitable[dict]] | None


# ---------------------------------------------------------------------------
# Internal: LLM connectivity
# ---------------------------------------------------------------------------

async def _check_llm_connection() -> dict:
    """Probe the configured Ollama endpoint.  Raises on failure."""
    headers = {}
    api_key = os.getenv("OLLAMA_API_KEY", "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(
            f"{OLLAMA_HOST.rstrip('/')}/api/tags", headers=headers
        )
        response.raise_for_status()

    return {"provider": "ollama", "host": OLLAMA_HOST, "model": DEFAULT_MODEL}


# ---------------------------------------------------------------------------
# Internal: shared event helper
# ---------------------------------------------------------------------------

async def _emit(
    on_event: OnEvent,
    event_type: str,
    run_id: str,
    payload: dict,
    **kwargs,
) -> None:
    """Call on_event if one was supplied; silently skip otherwise."""
    if on_event:
        await on_event(event_type, run_id, payload, **kwargs)


# ---------------------------------------------------------------------------
# Internal: error helpers
# ---------------------------------------------------------------------------

def _make_error(stage: str, message: str) -> dict:
    """Build a standard error dict and append it to state.errors."""
    error = {
        "error_id": str(uuid.uuid4()),
        "stage": stage,
        "message": message,
        "created_at": datetime.now().isoformat(),
    }
    state.errors.append(error)
    return error


async def _emit_cycle_error(
    on_event: OnEvent,
    run_id: str,
    cycle_id: str,
    signal_dict: dict,
    stage: str,
    message: str,
) -> None:
    """Record a cycle failure and notify connected clients."""
    error = _make_error(stage, message)
    signal_dict["status"] = "error"
    await _emit(
        on_event,
        "cycle_failed",
        run_id,
        {"stage": stage, "error": message},
        cycle_id=cycle_id,
        signal_id=signal_dict["signal_id"],
    )


# ---------------------------------------------------------------------------
# Internal: active_cycle dict factory
# ---------------------------------------------------------------------------

def _make_active_cycle(
    cycle_id: str,
    signal_dict: dict,
    *,
    ideator_status: dict | None = None,
    round1_status: dict | None = None,
    round2_status: dict | None = None,
    judge_status: dict | None = None,
) -> dict:
    """Return a fresh active_cycle dict with sensible defaults."""
    return {
        "cycle_id": cycle_id,
        "signal_id": signal_dict["signal_id"],
        "signal": signal_dict,
        "ideator": ideator_status or {"status": "waiting"},
        "round1": round1_status,
        "round2": round2_status,
        "judge": judge_status,
    }


# ---------------------------------------------------------------------------
# Internal: verdict persistence and event emission
# ---------------------------------------------------------------------------

async def _handle_verdict(
    on_event: OnEvent,
    run_id: str,
    cycle_id: str,
    signal_dict: dict,
    idea: Idea,
    verdict,
    db_idea_id: int,
) -> None:
    """Persist the verdict and emit the appropriate saved/rejected event."""
    save_verdict(
        verdict,
        verdict.debate_transcript,
        saved=1 if verdict.save else 0,
        idea_id=db_idea_id,
    )

    verdict_dict = verdict.to_dict()
    state.active_cycle["judge"] = {
        "status": "complete",
        "verdict": verdict_dict,
        "completed_at": datetime.now().isoformat(),
    }

    await _emit(
        on_event, "judge_completed", run_id,
        {"verdict": verdict_dict},
        cycle_id=cycle_id, signal_id=signal_dict["signal_id"],
    )

    entry = {
        "cycle_id": cycle_id,
        "signal_id": signal_dict["signal_id"],
        "signal": signal_dict,
        "idea": idea.to_dict(),
        "verdict": verdict_dict,
    }

    if verdict.save:
        await _emit(
            on_event, "verdict_saved", run_id,
            {"verdict": verdict_dict},
            cycle_id=cycle_id, signal_id=signal_dict["signal_id"],
        )
        signal_dict["status"] = "saved"
        state.saved_ideas.append(entry)
    else:
        await _emit(
            on_event, "verdict_rejected", run_id,
            {"verdict": verdict_dict},
            cycle_id=cycle_id, signal_id=signal_dict["signal_id"],
        )
        signal_dict["status"] = "rejected"
        state.rejected_ideas.append(entry)


# ---------------------------------------------------------------------------
# Internal: ideator execution for a single signal
# ---------------------------------------------------------------------------

async def _run_ideator_for_signal(
    on_event: OnEvent,
    run_id: str,
    cycle_id: str,
    signal_dict: dict,
) -> Idea | None:
    """
    Run the ideator for one signal dict.  Returns the Idea on success, or
    None if the signal should be skipped / errored (already handled internally).
    """
    from council.scrape import dict_to_signal_from_dict

    signal = dict_to_signal_from_dict(signal_dict)

    # --- connecting ---
    state.active_cycle["ideator"] = {
        "status": "connecting",
        "provider": "ollama",
        "host": OLLAMA_HOST,
        "model": DEFAULT_MODEL,
        "started_at": datetime.now().isoformat(),
    }
    await _emit(
        on_event, "ideator_started", run_id,
        {"status": "connecting", "provider": "ollama",
         "host": OLLAMA_HOST, "model": DEFAULT_MODEL},
        cycle_id=cycle_id, signal_id=signal_dict["signal_id"],
    )

    # --- LLM connectivity check ---
    try:
        llm = await _check_llm_connection()
    except Exception as exc:
        error = _make_error("ideator", f"LLM connection failed: {exc}")
        state.active_cycle["ideator"] = {
            "status": "failed",
            "error": error["message"],
            "completed_at": datetime.now().isoformat(),
        }
        signal_dict["status"] = "error"
        await _emit(
            on_event, "ideator_failed", run_id,
            {"error": error["message"]},
            cycle_id=cycle_id, signal_id=signal_dict["signal_id"],
        )
        return None

    # --- thinking ---
    state.active_cycle["ideator"] = {
        "status": "thinking",
        **llm,
        "started_at": datetime.now().isoformat(),
    }
    await _emit(
        on_event, "ideator_thinking", run_id, llm,
        cycle_id=cycle_id, signal_id=signal_dict["signal_id"],
    )

    # --- run ideator ---
    try:
        idea = await asyncio.to_thread(run_ideator, signal)
    except Exception as exc:
        error = _make_error("ideator", f"Ideator failed: {exc}")
        state.active_cycle["ideator"] = {
            "status": "failed",
            "error": error["message"],
            "completed_at": datetime.now().isoformat(),
        }
        signal_dict["status"] = "error"
        await _emit(
            on_event, "ideator_failed", run_id,
            {"error": error["message"]},
            cycle_id=cycle_id, signal_id=signal_dict["signal_id"],
        )
        return None

    # --- skip ---
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
        await _emit(
            on_event, "ideator_skipped", run_id,
            {"reason": idea.skip_reason},
            cycle_id=cycle_id, signal_id=signal_dict["signal_id"],
        )
        return None

    # --- complete ---
    state.active_cycle["ideator"] = {
        "status": "complete",
        "idea": idea.to_dict(),
        "completed_at": datetime.now().isoformat(),
    }
    await _emit(
        on_event, "ideator_completed", run_id,
        {"idea": idea.to_dict()},
        cycle_id=cycle_id, signal_id=signal_dict["signal_id"],
    )

    return idea


# ---------------------------------------------------------------------------
# Internal: source scraping loop (shared by run_scraping and run_full)
# ---------------------------------------------------------------------------

async def _scrape_sources(
    on_event: OnEvent,
    run_id: str,
    max_signals: int,
) -> None:
    """
    Scrape all sources and populate state.signals.
    Respects state.status == "stopping" between sources and between signals.
    """
    from council.scrape import (
        scrape_github, scrape_hn, scrape_arxiv,
        scrape_devto, scrape_lobsters, dict_to_signal,
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
            return

        state.sources[source] = {
            "source": source,
            "status": "scraping",
            "raw_count": 0,
            "fresh_count": 0,
            "duplicate_count": 0,
            "started_at": datetime.now().isoformat(),
        }
        await _emit(on_event, "source_scrape_started", run_id, {"source": source})

        raw_signals = await asyncio.to_thread(scraper_fn)
        source_signals = []
        duplicate_count = 0

        for raw_signal in raw_signals:
            if state.status == "stopping":
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
            await _emit(
                on_event, "signal_queued", run_id,
                signal_dict, signal_id=signal_dict["signal_id"],
            )

        state.sources[source] = {
            "source": source,
            "status": "complete",
            "raw_count": len(raw_signals),
            "fresh_count": len(source_signals),
            "duplicate_count": duplicate_count,
            "completed_at": datetime.now().isoformat(),
        }
        await _emit(
            on_event, "source_scrape_completed", run_id,
            {
                "source": source,
                "raw_count": len(raw_signals),
                "fresh_count": len(source_signals),
                "duplicate_count": duplicate_count,
            },
        )


# ===========================================================================
# Public phase functions
# ===========================================================================

async def run_scraping(
    run_id: str,
    max_signals: int,
    on_event: OnEvent = None,
) -> None:
    """
    Phase 1 — Scrape all sources and queue signals into state.

    Called by: POST /api/run/scrape
    """
    state.run_id = run_id
    state.status = "scraping"
    state.started_at = datetime.now().isoformat()
    state.completed_at = None
    state.reset_for_scraping()

    await _emit(on_event, "run_started", run_id,
                {"max_signals": max_signals, "section": "scraping"})

    await _scrape_sources(on_event, run_id, max_signals)

    if state.status == "stopping":
        await _emit(on_event, "run_stopped", run_id, {"section": "scraping"})
        state.status = "idle"
        return

    state.status = "idle"
    state.completed_at = datetime.now().isoformat()
    await _emit(on_event, "section_completed", run_id, {"section": "scraping"})


async def run_ideator_phase(
    run_id: str,
    on_event: OnEvent = None,
) -> None:
    """
    Phase 2 — Run the Ideator for every queued signal that has no idea yet.

    Called by: POST /api/run/ideator
    Raises PrerequisiteError if there are no signals to process.
    """
    pending = [s for s in state.signals if s.get("status") in {"queued", "processing"}]
    if not pending:
        raise PrerequisiteError("No signals available — run scraping first.")

    state.status = "processing"
    state.run_id = run_id

    await _emit(on_event, "section_started", run_id, {"section": "ideator"})

    for i, signal_dict in enumerate(pending):
        if state.status == "stopping":
            await _emit(on_event, "run_stopped", run_id, {"section": "ideator"})
            state.status = "idle"
            return

        if signal_dict.get("idea"):
            continue  # already processed

        cycle_id = str(uuid.uuid4())
        signal_dict["status"] = "processing"
        state.active_cycle = _make_active_cycle(cycle_id, signal_dict)

        await _emit(
            on_event, "signal_processing_started", run_id,
            {"signal_index": i},
            cycle_id=cycle_id, signal_id=signal_dict["signal_id"],
        )

        idea = await _run_ideator_for_signal(on_event, run_id, cycle_id, signal_dict)
        if idea is None:
            continue

        # Persist
        db_signal_id = signal_dict.get("db_signal_id") or save_signal(
            __import__("council.scrape", fromlist=["dict_to_signal_from_dict"])
            .dict_to_signal_from_dict(signal_dict)
        )
        db_idea_id = save_idea(db_signal_id, idea)
        signal_dict["db_signal_id"] = db_signal_id
        signal_dict["db_idea_id"] = db_idea_id
        signal_dict["idea"] = idea.to_dict()

    state.status = "idle"
    await _emit(on_event, "section_completed", run_id, {"section": "ideator"})


async def run_round1_phase(
    run_id: str,
    on_event: OnEvent = None,
) -> None:
    """
    Phase 3 — Run Round 1 lawyers for signals that have ideas but no round1.

    Called by: POST /api/run/round1
    Raises PrerequisiteError if no eligible signals exist.
    """
    eligible = [s for s in state.signals if s.get("idea") and not s.get("round1")]
    if not eligible:
        raise PrerequisiteError("No ideas available — run the ideator phase first.")

    state.status = "processing"
    state.run_id = run_id

    await _emit(on_event, "section_started", run_id, {"section": "round1"})

    for i, signal_dict in enumerate(eligible):
        if state.status == "stopping":
            await _emit(on_event, "run_stopped", run_id, {"section": "round1"})
            state.status = "idle"
            return

        cycle_id = str(uuid.uuid4())
        signal_dict["status"] = "processing"
        idea_dict = signal_dict["idea"]

        state.active_cycle = _make_active_cycle(
            cycle_id, signal_dict,
            ideator_status={"status": "complete", "idea": idea_dict},
        )

        await _emit(
            on_event, "signal_processing_started", run_id,
            {"signal_index": i},
            cycle_id=cycle_id, signal_id=signal_dict["signal_id"],
        )
        await _emit(
            on_event, "ideator_completed", run_id,
            {"idea": idea_dict},
            cycle_id=cycle_id, signal_id=signal_dict["signal_id"],
        )

        state.active_cycle["round1"] = {
            "status": "running", "lawyers": {},
            "started_at": datetime.now().isoformat(),
        }
        await _emit(on_event, "round_started", run_id, {"round": 1}, cycle_id=cycle_id)

        try:
            idea = Idea.from_dict(idea_dict)
            db_idea_id = signal_dict.get("db_idea_id")
            if not db_idea_id:
                from council.scrape import dict_to_signal_from_dict
                db_signal_id = (signal_dict.get("db_signal_id")
                                or save_signal(dict_to_signal_from_dict(signal_dict)))
                db_idea_id = save_idea(db_signal_id, idea)
                signal_dict["db_signal_id"] = db_signal_id
                signal_dict["db_idea_id"] = db_idea_id

            round1_results = await asyncio.to_thread(run_round1, idea)

            for dim, result in round1_results.items():
                save_lawyer_statement(
                    idea_id=db_idea_id, dimension=dim, round_num=1,
                    score=result["score"], argument=result["argument"],
                    key_points=result["key_points"],
                )
        except Exception as exc:
            await _emit_cycle_error(
                on_event, run_id, cycle_id, signal_dict,
                "round1", f"Round 1 failed: {exc}",
            )
            continue

        signal_dict["round1"] = round1_results
        for dim, result in round1_results.items():
            state.active_cycle["round1"]["lawyers"][dim] = {
                "score": result["score"],
                "argument": result["argument"],
                "key_points": result["key_points"],
                "status": "complete",
            }
            await _emit(
                on_event, "lawyer_completed", run_id,
                {"round": 1, "dimension": dim, "score": result["score"],
                 "argument": result["argument"], "key_points": result["key_points"]},
                cycle_id=cycle_id, signal_id=signal_dict["signal_id"],
            )

    state.status = "idle"
    await _emit(on_event, "section_completed", run_id, {"section": "round1"})


async def run_round2_phase(
    run_id: str,
    on_event: OnEvent = None,
) -> None:
    """
    Phase 4 — Run Round 2 (rebuttals) + Judge for signals with round1 but no round2.

    Called by: POST /api/run/round2
    Raises PrerequisiteError if no eligible signals exist.
    """
    eligible = [s for s in state.signals if s.get("round1") and not s.get("round2")]
    if not eligible:
        raise PrerequisiteError("No round 1 results available — run round 1 first.")

    state.status = "processing"
    state.run_id = run_id

    await _emit(on_event, "section_started", run_id, {"section": "round2"})

    for i, signal_dict in enumerate(eligible):
        if state.status == "stopping":
            await _emit(on_event, "run_stopped", run_id, {"section": "round2"})
            state.status = "idle"
            return

        cycle_id = str(uuid.uuid4())
        signal_dict["status"] = "processing"
        idea_dict = signal_dict["idea"]
        round1_results = signal_dict["round1"]

        state.active_cycle = _make_active_cycle(
            cycle_id, signal_dict,
            ideator_status={"status": "complete", "idea": idea_dict},
            round1_status={"status": "complete", "lawyers": round1_results},
        )

        await _emit(
            on_event, "signal_processing_started", run_id,
            {"signal_index": i},
            cycle_id=cycle_id, signal_id=signal_dict["signal_id"],
        )
        await _emit(
            on_event, "ideator_completed", run_id,
            {"idea": idea_dict},
            cycle_id=cycle_id, signal_id=signal_dict["signal_id"],
        )
        await _emit(on_event, "round_started", run_id, {"round": 1}, cycle_id=cycle_id)

        for dim, result in round1_results.items():
            await _emit(
                on_event, "lawyer_completed", run_id,
                {"round": 1, "dimension": dim, "score": result["score"],
                 "argument": result["argument"],
                 "key_points": result.get("key_points", [])},
                cycle_id=cycle_id, signal_id=signal_dict["signal_id"],
            )

        state.active_cycle["round2"] = {
            "status": "running", "lawyers": {},
            "started_at": datetime.now().isoformat(),
        }
        await _emit(on_event, "round_started", run_id, {"round": 2}, cycle_id=cycle_id)

        try:
            idea = Idea.from_dict(idea_dict)
            db_idea_id = signal_dict.get("db_idea_id")
            if not db_idea_id:
                from council.scrape import dict_to_signal_from_dict
                db_signal_id = (signal_dict.get("db_signal_id")
                                or save_signal(dict_to_signal_from_dict(signal_dict)))
                db_idea_id = save_idea(db_signal_id, idea)
                signal_dict["db_signal_id"] = db_signal_id
                signal_dict["db_idea_id"] = db_idea_id

            round2_results = await asyncio.to_thread(run_round2, idea, round1_results)
            for dim, result in round2_results.items():
                save_lawyer_statement(
                    idea_id=db_idea_id, dimension=dim, round_num=2,
                    score=result["updated_score"], argument=result["rebuttal"],
                )

            verdict = await asyncio.to_thread(run_judge, idea, round1_results, round2_results)
        except Exception as exc:
            await _emit_cycle_error(
                on_event, run_id, cycle_id, signal_dict,
                "round2", f"Round 2/Judge failed: {exc}",
            )
            continue

        signal_dict["round2"] = round2_results
        for dim, result in round2_results.items():
            state.active_cycle["round2"]["lawyers"][dim] = {
                "original_score": round1_results[dim]["score"],
                "updated_score": result["updated_score"],
                "rebuttal": result["rebuttal"],
                "status": "complete",
            }
            await _emit(
                on_event, "lawyer_completed", run_id,
                {"round": 2, "dimension": dim,
                 "original_score": round1_results[dim]["score"],
                 "updated_score": result["updated_score"],
                 "rebuttal": result["rebuttal"]},
                cycle_id=cycle_id, signal_id=signal_dict["signal_id"],
            )

        await _handle_verdict(
            on_event, run_id, cycle_id, signal_dict, idea, verdict, db_idea_id
        )
        await _emit(
            on_event, "cycle_completed", run_id, {},
            cycle_id=cycle_id, signal_id=signal_dict["signal_id"],
        )

    state.status = "idle"
    await _emit(on_event, "section_completed", run_id, {"section": "round2"})


async def run_full(
    run_id: str,
    max_signals: int,
    on_event: OnEvent = None,
) -> None:
    """
    Full pipeline — scrape → ideate → round1 → round2 + judge in one go.

    Called by: POST /api/run
    """
    state.run_id = run_id
    state.status = "scraping"
    state.started_at = datetime.now().isoformat()
    state.completed_at = None
    state.reset_for_run()

    await _emit(on_event, "run_started", run_id, {"max_signals": max_signals})

    # --- Scraping ---
    await _scrape_sources(on_event, run_id, max_signals)
    if state.status == "stopping":
        await _emit(on_event, "run_stopped", run_id, {})
        state.status = "idle"
        return

    # --- Council cycles ---
    state.status = "processing"
    for i, signal_dict in enumerate(state.signals):
        if state.status == "stopping":
            await _emit(on_event, "run_stopped", run_id, {})
            state.status = "idle"
            return

        cycle_id = str(uuid.uuid4())
        signal_dict["status"] = "processing"
        state.active_cycle = _make_active_cycle(cycle_id, signal_dict)

        await _emit(
            on_event, "signal_processing_started", run_id,
            {"signal_index": i},
            cycle_id=cycle_id, signal_id=signal_dict["signal_id"],
        )

        # Ideator
        idea = await _run_ideator_for_signal(on_event, run_id, cycle_id, signal_dict)
        if state.status == "stopping":
            await _emit(on_event, "run_stopped", run_id, {})
            state.status = "idle"
            return
        if idea is None:
            continue

        db_signal_id = signal_dict["db_signal_id"]
        db_idea_id = save_idea(db_signal_id, idea)
        signal_dict["db_idea_id"] = db_idea_id

        # Round 1
        if state.status == "stopping":
            await _emit(on_event, "run_stopped", run_id, {})
            state.status = "idle"
            return

        state.active_cycle["round1"] = {
            "status": "running", "lawyers": {},
            "started_at": datetime.now().isoformat(),
        }
        await _emit(on_event, "round_started", run_id, {"round": 1}, cycle_id=cycle_id)

        try:
            round1_results = await asyncio.to_thread(run_round1, idea)
            for dim, result in round1_results.items():
                save_lawyer_statement(
                    idea_id=db_idea_id, dimension=dim, round_num=1,
                    score=result["score"], argument=result["argument"],
                    key_points=result["key_points"],
                )
        except Exception as exc:
            await _emit_cycle_error(
                on_event, run_id, cycle_id, signal_dict,
                "round1", f"Round 1 failed: {exc}",
            )
            continue

        if state.status == "stopping":
            await _emit(on_event, "run_stopped", run_id, {})
            state.status = "idle"
            return

        for dim, result in round1_results.items():
            state.active_cycle["round1"]["lawyers"][dim] = {
                "score": result["score"],
                "argument": result["argument"],
                "key_points": result["key_points"],
                "status": "complete",
            }
            await _emit(
                on_event, "lawyer_completed", run_id,
                {"round": 1, "dimension": dim, "score": result["score"],
                 "argument": result["argument"], "key_points": result["key_points"]},
                cycle_id=cycle_id, signal_id=signal_dict["signal_id"],
            )

        # Round 2
        if state.status == "stopping":
            await _emit(on_event, "run_stopped", run_id, {})
            state.status = "idle"
            return

        state.active_cycle["round2"] = {
            "status": "running", "lawyers": {},
            "started_at": datetime.now().isoformat(),
        }
        await _emit(on_event, "round_started", run_id, {"round": 2}, cycle_id=cycle_id)

        try:
            round2_results = await asyncio.to_thread(run_round2, idea, round1_results)
            for dim, result in round2_results.items():
                save_lawyer_statement(
                    idea_id=db_idea_id, dimension=dim, round_num=2,
                    score=result["updated_score"], argument=result["rebuttal"],
                )
        except Exception as exc:
            await _emit_cycle_error(
                on_event, run_id, cycle_id, signal_dict,
                "round2", f"Round 2 failed: {exc}",
            )
            continue

        if state.status == "stopping":
            await _emit(on_event, "run_stopped", run_id, {})
            state.status = "idle"
            return

        for dim, result in round2_results.items():
            state.active_cycle["round2"]["lawyers"][dim] = {
                "original_score": round1_results[dim]["score"],
                "updated_score": result["updated_score"],
                "rebuttal": result["rebuttal"],
                "status": "complete",
            }
            await _emit(
                on_event, "lawyer_completed", run_id,
                {"round": 2, "dimension": dim,
                 "original_score": round1_results[dim]["score"],
                 "updated_score": result["updated_score"],
                 "rebuttal": result["rebuttal"]},
                cycle_id=cycle_id, signal_id=signal_dict["signal_id"],
            )

        # Judge
        if state.status == "stopping":
            await _emit(on_event, "run_stopped", run_id, {})
            state.status = "idle"
            return

        try:
            verdict = await asyncio.to_thread(
                run_judge, idea, round1_results, round2_results
            )
        except Exception as exc:
            await _emit_cycle_error(
                on_event, run_id, cycle_id, signal_dict,
                "judge", f"Judge failed: {exc}",
            )
            continue

        await _handle_verdict(
            on_event, run_id, cycle_id, signal_dict, idea, verdict, db_idea_id
        )
        await _emit(
            on_event, "cycle_completed", run_id, {},
            cycle_id=cycle_id, signal_id=signal_dict["signal_id"],
        )

    state.status = "complete"
    state.completed_at = datetime.now().isoformat()
    await _emit(on_event, "run_completed", run_id, {})

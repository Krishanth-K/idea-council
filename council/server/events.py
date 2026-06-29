"""WebSocket connection manager and event broadcaster for the IdeaCouncil server."""

import json
from datetime import datetime

from fastapi import WebSocket


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts events."""

    def __init__(self):
        self.active_connections: set = set()

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.discard(websocket)

    async def send_event(self, event: dict) -> None:
        """Broadcast a JSON event to all connected clients."""
        msg = json.dumps(event)
        for conn in list(self.active_connections):
            try:
                await conn.send_text(msg)
            except Exception:
                self.active_connections.discard(conn)


manager = ConnectionManager()


async def emit_event(
    event_type: str,
    run_id: str,
    payload: dict,
    cycle_id: str | None = None,
    signal_id: str | None = None,
) -> dict:
    """Build an event envelope and broadcast it to all WebSocket clients.

    This function is passed as the ``on_event`` callback to core phase
    functions so they can push updates without importing anything from
    ``council.server``.
    """
    event: dict = {
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

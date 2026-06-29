"""Application state for IdeaCouncil — lives in core, never imports from council.server."""

from datetime import datetime


class PrerequisiteError(Exception):
    """Raised when a phase is called without its prerequisites being met."""
    pass


def new_run_id() -> str:
    """Generate a timestamped run ID."""
    return f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


class AppState:
    """Singleton in-memory state for the current run."""

    def __init__(self):
        self.run_id: str | None = None
        self.status: str = "idle"          # idle | scraping | processing | stopping | failed | complete
        self.started_at: str | None = None
        self.completed_at: str | None = None
        self.sources: dict = {}
        self.signals: list[dict] = []
        self.active_cycle: dict | None = None
        self.saved_ideas: list[dict] = []
        self.rejected_ideas: list[dict] = []
        self.skipped_signals: list[dict] = []
        self.errors: list[dict] = []

    def is_busy(self) -> bool:
        """Return True if a run is currently in progress."""
        return self.status in {"scraping", "processing"}

    def request_stop(self) -> None:
        """Signal all running phase loops to stop gracefully."""
        self.status = "stopping"

    def reset_for_run(self) -> None:
        """Full reset — call before starting a fresh combined run."""
        self.sources = {}
        self.signals = []
        self.active_cycle = None
        self.saved_ideas = []
        self.rejected_ideas = []
        self.skipped_signals = []
        self.errors = []

    def reset_for_scraping(self) -> None:
        """Partial reset — only clears scraping-related state."""
        self.sources = {}
        self.signals = []
        self.errors = []


# Global singleton — imported by phases.py and read (never written) by server.py
state = AppState()

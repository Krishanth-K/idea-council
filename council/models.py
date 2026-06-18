"""Data models for IdeaCouncil."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Signal:
    """A single signal scraped from a source."""
    source: str
    title: str
    url: str
    blurb: str
    scraped_at: str

    def url_hash(self) -> str:
        """SHA256 hash of the URL for deduplication."""
        import hashlib
        return hashlib.sha256(self.url.encode()).hexdigest()


@dataclass
class Idea:
    """A project idea proposed by the Ideator agent."""
    title: str
    one_liner: str
    target_user: str
    problem_it_solves: str
    core_technical_challenge: str
    source_signals: list[str] = field(default_factory=list)
    estimated_scope: str = ""
    skip: bool = False
    skip_reason: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "Idea":
        """Create Idea from parsed JSON dict."""
        if data.get("skip"):
            return cls(
                title="",
                one_liner="",
                target_user="",
                problem_it_solves="",
                core_technical_challenge="",
                skip=True,
                skip_reason=data.get("reason", "")
            )
        return cls(
            title=data.get("title", ""),
            one_liner=data.get("one_liner", ""),
            target_user=data.get("target_user", ""),
            problem_it_solves=data.get("problem_it_solves", ""),
            core_technical_challenge=data.get("core_technical_challenge", ""),
            source_signals=data.get("source_signals", []),
            estimated_scope=data.get("estimated_scope", "")
        )

    def to_dict(self) -> dict:
        """Convert Idea to dict for JSON serialization."""
        if self.skip:
            return {"skip": True, "reason": self.skip_reason}
        return {
            "title": self.title,
            "one_liner": self.one_liner,
            "target_user": self.target_user,
            "problem_it_solves": self.problem_it_solves,
            "core_technical_challenge": self.core_technical_challenge,
            "source_signals": self.source_signals,
            "estimated_scope": self.estimated_scope
        }


@dataclass
class Verdict:
    """Final verdict from the Judge agent."""
    idea_title: str
    one_liner: str
    scores: dict[str, float] = field(default_factory=dict)
    weighted_score: float = 0.0
    save: bool = False
    summary: str = ""
    debate_transcript: str = ""

    # Scoring weights (must sum to 1.0)
    WEIGHTS = {
        "novelty": 0.20,
        "solo_feasibility": 0.25,
        "technical_depth": 0.20,
        "resume_value": 0.20,
        "real_use_case": 0.15
    }

    # Thresholds
    SAVE_THRESHOLD = 6.5
    FEASIBILITY_DISCARD_THRESHOLD = 5.0

    def compute_weighted_score(self) -> float:
        """Compute weighted score from individual dimension scores."""
        total = 0.0
        for dim, weight in self.WEIGHTS.items():
            score = self.scores.get(dim, 0.0)
            total += score * weight
        return round(total, 2)

    def should_save(self) -> bool:
        """Determine if this idea should be saved based on thresholds."""
        self.weighted_score = self.compute_weighted_score()

        # Hard discard: feasibility too low
        if self.scores.get("solo_feasibility", 0) < self.FEASIBILITY_DISCARD_THRESHOLD:
            self.save = False
            return False

        # Save threshold
        if self.weighted_score >= self.SAVE_THRESHOLD:
            self.save = True
            return False

        self.save = False
        return False

    @classmethod
    def from_dict(cls, data: dict) -> "Verdict":
        """Create Verdict from parsed JSON dict."""
        return cls(
            idea_title=data.get("idea_title", ""),
            one_liner=data.get("one_liner", ""),
            scores=data.get("scores", {}),
            weighted_score=data.get("weighted_score", 0.0),
            save=data.get("save", False),
            summary=data.get("summary", ""),
            debate_transcript=""
        )


@dataclass
class CycleState:
    """Holds all state for one complete council cycle."""
    signals: list[Signal] = field(default_factory=list)
    idea: Optional[Idea] = None
    round1: dict[str, str] = field(default_factory=dict)  # dimension -> lawyer argument
    round2: dict[str, str] = field(default_factory=dict)  # dimension -> rebuttal
    verdict: Optional[Verdict] = None

    def format_signals(self) -> str:
        """Format signals for the Ideator prompt."""
        lines = []
        for sig in self.signals:
            lines.append(f"Source: {sig.source}\nTitle: {sig.title}\nBlurb: {sig.blurb}\n---")
        return "\n".join(lines)

    def format_round1_transcript(self) -> str:
        """Format Round 1 arguments for Round 2."""
        lines = [f"=== ROUND 1: Opening Arguments ===\n"]
        for dim, arg in self.round1.items():
            lines.append(f"\n--- {dim.upper()} Lawyer ---\n{arg}")
        return "\n".join(lines)

    def format_full_transcript(self) -> str:
        """Format full transcript for the Judge."""
        if self.idea is None:
            raise ValueError("Cannot format transcript: idea is None")

        idea = self.idea
        lines = [
            f"=== IDEA ===\nTitle: {idea.title}\n{idea.one_liner}\n",
            f"Target User: {idea.target_user}\n",
            f"Problem: {idea.problem_it_solves}\n",
            f"Technical Challenge: {idea.core_technical_challenge}\n",
            f"\n{self.format_round1_transcript()}",
            f"\n=== ROUND 2: Rebuttals ===\n"
        ]
        for dim, rebuttal in self.round2.items():
            lines.append(f"\n--- {dim.upper()} Rebuttal ---\n{rebuttal}")
        return "\n".join(lines)
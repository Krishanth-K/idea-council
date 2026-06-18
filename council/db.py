"""SQLite database for IdeaCouncil."""

import sqlite3
import json
from pathlib import Path
from typing import Optional

from council.models import Verdict


DB_PATH = Path(__file__).parent.parent / "ideacouncil.db"


def get_connection() -> sqlite3.Connection:
    """Get a database connection. Creates DB if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize the database with required tables."""
    conn = get_connection()
    cursor = conn.cursor()

    # Ideas table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ideas (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            title           TEXT NOT NULL,
            one_liner       TEXT,
            scores          TEXT,
            weighted_score  REAL,
            saved           INTEGER,
            summary         TEXT,
            transcript      TEXT,
            created_at      TEXT DEFAULT (datetime('now'))
        )
    """)

    # Seen signals table (for deduplication)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS seen_signals (
            url_hash    TEXT PRIMARY KEY,
            url         TEXT,
            source      TEXT,
            scraped_at  TEXT
        )
    """)

    conn.commit()
    conn.close()


def is_signal_seen(url_hash: str) -> bool:
    """Check if a URL hash has already been processed."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT 1 FROM seen_signals WHERE url_hash = ?", (url_hash,))
    result = cursor.fetchone() is not None

    conn.close()
    return result


def mark_signal_seen(url_hash: str, url: str, source: str, scraped_at: str) -> None:
    """Mark a signal as seen in the database."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT OR IGNORE INTO seen_signals (url_hash, url, source, scraped_at) VALUES (?, ?, ?, ?)",
        (url_hash, url, source, scraped_at)
    )

    conn.commit()
    conn.close()


def save_verdict(verdict: Verdict, full_transcript: str) -> int:
    """
    Save a verdict to the database.
    Returns the inserted row ID.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO ideas (
            title, one_liner, scores, weighted_score, saved, summary, transcript
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            verdict.idea_title,
            verdict.one_liner,
            json.dumps(verdict.scores),
            verdict.weighted_score,
            1 if verdict.save else 0,
            verdict.summary,
            full_transcript
        )
    )

    row_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return row_id


def get_saved_ideas(limit: int = 20) -> list[dict]:
    """Retrieve saved ideas from the database."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, title, one_liner, scores, weighted_score, summary, created_at
        FROM ideas
        WHERE saved = 1
        ORDER BY weighted_score DESC, created_at DESC
        LIMIT ?
        """,
        (limit,)
    )

    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        results.append({
            "id": row["id"],
            "title": row["title"],
            "one_liner": row["one_liner"],
            "scores": json.loads(row["scores"]) if row["scores"] else {},
            "weighted_score": row["weighted_score"],
            "summary": row["summary"],
            "created_at": row["created_at"]
        })

    return results


def get_idea_transcript(idea_id: int) -> Optional[str]:
    """Get the full debate transcript for a saved idea."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT transcript FROM ideas WHERE id = ?", (idea_id,))
    row = cursor.fetchone()
    conn.close()

    return row["transcript"] if row else None


if __name__ == "__main__":
    # Initialize DB when run directly
    init_db()
    print(f"Database initialized at: {DB_PATH}")
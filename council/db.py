"""SQLite database for IdeaCouncil."""

import sqlite3
import json
from pathlib import Path
from typing import Optional

from council.models import Verdict, Signal, Idea


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

    # Ideas table (representing final verdicts)
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

    # Signals table (stores full signal details)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT,
            source      TEXT,
            url         TEXT,
            blurb       TEXT,
            summary     TEXT,
            scraped_at  TEXT,
            url_hash    TEXT UNIQUE
        )
    """)

    # Pipeline Ideas table (stores generated ideas, skipped or not)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_ideas (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id           INTEGER REFERENCES signals(id),
            title               TEXT,
            one_liner           TEXT,
            target_user         TEXT,
            problem_it_solves   TEXT,
            core_technical_challenge TEXT,
            estimated_scope     TEXT,
            skip                INTEGER, -- 0 or 1
            skip_reason         TEXT,
            created_at          TEXT DEFAULT (datetime('now'))
        )
    """)

    # Lawyer statements table (R1 and R2 statements)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lawyer_statements (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            idea_id         INTEGER REFERENCES pipeline_ideas(id),
            dimension       TEXT,
            round           INTEGER, -- 1 or 2
            score           INTEGER,
            argument        TEXT,
            key_points      TEXT, -- JSON list of strings (for round 1)
            created_at      TEXT DEFAULT (datetime('now'))
        )
    """)

    # Ensure ideas table has the new columns if needed (backward compatibility migration)
    try:
        cursor.execute("ALTER TABLE ideas ADD COLUMN idea_id INTEGER REFERENCES pipeline_ideas(id)")
    except sqlite3.OperationalError:
        # Column already exists
        pass

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


def save_signal(signal: Signal) -> int:
    """Save a signal and return its database ID."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Check if signal is already in signals table
    cursor.execute("SELECT id FROM signals WHERE url_hash = ?", (signal.url_hash(),))
    row = cursor.fetchone()
    if row:
        signal_id = row["id"]
    else:
        cursor.execute(
            """
            INSERT INTO signals (title, source, url, blurb, summary, scraped_at, url_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal.title,
                signal.source,
                signal.url,
                signal.blurb,
                signal.summary,
                signal.scraped_at,
                signal.url_hash()
            )
        )
        signal_id = cursor.lastrowid
        
    conn.commit()
    conn.close()
    return signal_id


def save_idea(signal_id: int, idea: Idea) -> int:
    """Save a pipeline idea and return its database ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO pipeline_ideas (
            signal_id, title, one_liner, target_user, problem_it_solves,
            core_technical_challenge, estimated_scope, skip, skip_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            signal_id,
            idea.title,
            idea.one_liner,
            idea.target_user,
            idea.problem_it_solves,
            idea.core_technical_challenge,
            idea.estimated_scope,
            1 if idea.skip else 0,
            idea.skip_reason
        )
    )
    idea_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return idea_id


def save_lawyer_statement(idea_id: int, dimension: str, round_num: int, score: int, argument: str, key_points: list[str] = None) -> int:
    """Save a lawyer statement (argument or rebuttal)."""
    conn = get_connection()
    cursor = conn.cursor()
    kp_json = json.dumps(key_points) if key_points else None
    cursor.execute(
        """
        INSERT INTO lawyer_statements (
            idea_id, dimension, round, score, argument, key_points
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (idea_id, dimension, round_num, score, argument, kp_json)
    )
    statement_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return statement_id


def save_verdict(verdict: Verdict, full_transcript: str, saved: Optional[int] = None, idea_id: Optional[int] = None) -> int:
    """
    Save a verdict to the database.
    Returns the inserted row ID.
    """
    conn = get_connection()
    cursor = conn.cursor()

    is_saved = saved if saved is not None else (1 if verdict.save else 0)

    cursor.execute(
        """
        INSERT INTO ideas (
            title, one_liner, scores, weighted_score, saved, summary, transcript, idea_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            verdict.idea_title,
            verdict.one_liner,
            json.dumps(verdict.scores),
            verdict.weighted_score,
            is_saved,
            verdict.summary,
            full_transcript,
            idea_id
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
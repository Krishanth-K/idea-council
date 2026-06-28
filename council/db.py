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

    # 1. Signals table (stores full signal details)
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

    # 2. Seen signals table (for deduplication)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS seen_signals (
            url_hash    TEXT PRIMARY KEY,
            url         TEXT,
            source      TEXT,
            scraped_at  TEXT
        )
    """)

    # 3. Ideas table (consolidated lifecycle representing raw + debated ideas)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ideas (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id               INTEGER REFERENCES signals(id),
            title                   TEXT NOT NULL,
            one_liner               TEXT,
            target_user             TEXT,
            problem_it_solves       TEXT,
            core_technical_challenge TEXT,
            estimated_scope         TEXT,
            skip                    INTEGER DEFAULT 0, -- 0 or 1
            skip_reason             TEXT,
            debated                 INTEGER DEFAULT 0, -- 0 or 1
            accepted_by_council     INTEGER DEFAULT 0, -- 0 or 1
            created_at              TEXT DEFAULT (datetime('now'))
        )
    """)

    # 4. Lawyer statements table (R1 and R2 statements)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lawyer_statements (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            idea_id         INTEGER REFERENCES ideas(id),
            dimension       TEXT,
            round           INTEGER, -- 1 or 2
            statement_type  TEXT, -- 'statement' or 'rebuttal'
            against         TEXT, -- NULL or dimension rebutted
            score           INTEGER,
            argument        TEXT,
            key_points      TEXT, -- JSON list of strings (for round 1)
            created_at      TEXT DEFAULT (datetime('now'))
        )
    """)

    # 5. Verdicts table (stores final judge scoring/synthesis transcripts for accepted ideas)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS verdicts (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            idea_id             INTEGER UNIQUE REFERENCES ideas(id),
            weighted_score      REAL,
            scores              TEXT, -- JSON of dimension -> score
            summary             TEXT, -- Judge synthesis
            debate_transcript   TEXT, -- Full transcript
            created_at          TEXT DEFAULT (datetime('now'))
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
        INSERT INTO ideas (
            signal_id, title, one_liner, target_user, problem_it_solves,
            core_technical_challenge, estimated_scope, skip, skip_reason,
            debated, accepted_by_council
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0)
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


def save_lawyer_statement(
    idea_id: int,
    dimension: str,
    round_num: int,
    score: int,
    argument: str,
    key_points: list[str] = None,
    statement_type: Optional[str] = None,
    against: Optional[str] = None,
) -> int:
    """Save a lawyer statement (argument or rebuttal)."""
    conn = get_connection()
    cursor = conn.cursor()
    kp_json = json.dumps(key_points) if key_points else None
    
    # Infer statement type if not explicitly provided
    if not statement_type:
        statement_type = "statement" if round_num == 1 else "rebuttal"
        
    cursor.execute(
        """
        INSERT INTO lawyer_statements (
            idea_id, dimension, round, statement_type, against, score, argument, key_points
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (idea_id, dimension, round_num, statement_type, against, score, argument, kp_json)
    )
    statement_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return statement_id


def save_verdict(verdict: Verdict, full_transcript: str, saved: Optional[int] = None, idea_id: Optional[int] = None) -> int:
    """
    Save a verdict to the database.
    Updates the ideas table and inserts into the verdicts table if accepted.
    Returns the verdict ID if saved, or idea_id as fallback.
    """
    conn = get_connection()
    cursor = conn.cursor()

    is_saved = saved if saved is not None else (1 if verdict.save else 0)

    # 1. Update the ideas table state
    if idea_id is not None:
        cursor.execute(
            """
            UPDATE ideas
            SET debated = 1, accepted_by_council = ?
            WHERE id = ?
            """,
            (is_saved, idea_id)
        )
    else:
        # Fallback: attempt to resolve idea_id via title
        cursor.execute(
            """
            UPDATE ideas
            SET debated = 1, accepted_by_council = ?
            WHERE title = ? AND debated = 0
            """,
            (is_saved, verdict.idea_title)
        )
        cursor.execute("SELECT id FROM ideas WHERE title = ? ORDER BY id DESC LIMIT 1", (verdict.idea_title,))
        row = cursor.fetchone()
        if row:
            idea_id = row["id"]

    # 2. Insert into the verdicts table (if accepted/saved)
    verdict_id = 0
    if is_saved:
        cursor.execute(
            """
            INSERT INTO verdicts (
                idea_id, weighted_score, scores, summary, debate_transcript
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                idea_id,
                verdict.weighted_score,
                json.dumps(verdict.scores),
                verdict.summary,
                full_transcript
            )
        )
        verdict_id = cursor.lastrowid

    conn.commit()
    conn.close()

    # Return the verdict_id (or idea_id as fallback) for backward compatibility
    return verdict_id if verdict_id else (idea_id if idea_id else 0)


def get_saved_ideas(limit: int = 20) -> list[dict]:
    """Retrieve saved ideas from the database."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT i.id AS idea_id, v.id AS verdict_id, i.title, i.one_liner, v.scores, v.weighted_score, v.summary, v.created_at
        FROM verdicts v
        JOIN ideas i ON v.idea_id = i.id
        ORDER BY v.weighted_score DESC, v.created_at DESC
        LIMIT ?
        """,
        (limit,)
    )

    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        results.append({
            "id": row["idea_id"],  # Keep ID as ideas.id for backward compatibility
            "idea_id": row["idea_id"],
            "verdict_id": row["verdict_id"],
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

    # Query using either the idea_id (preferred) or the verdict_id (as fallback)
    cursor.execute(
        """
        SELECT debate_transcript 
        FROM verdicts 
        WHERE idea_id = ? OR id = ?
        """,
        (idea_id, idea_id)
    )
    row = cursor.fetchone()
    conn.close()

    return row["debate_transcript"] if row else None


if __name__ == "__main__":
    # Initialize DB when run directly
    init_db()
    print(f"Database initialized at: {DB_PATH}")
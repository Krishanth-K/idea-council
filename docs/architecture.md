# Architectural Rationale & Engineering Decisions

This document explains the key technical decisions behind IdeaCouncil's design.

---

## 1. Direct Python Orchestration vs. Multi-Agent Frameworks

**Decision**: Direct Python DAG instead of LangGraph, CrewAI, or AutoGen.

**Rationale**: The pipeline is a deterministic Directed Acyclic Graph with fixed execution phases (Scrape → Deduplicate → Ideate → Round 1 → Round 2 → Verdict). Framework abstractions introduce opaque state management, hidden LLM retry loops, and debugging complexity without performance benefits. Plain Python functions and dataclasses provide absolute control over prompt formatting, JSON parsing retries, error fallbacks, and execution logging.

---

## 2. Structured Courtroom Protocol vs. Open-Ended Debates

**Decision**: Strict two-round courtroom structure with isolated first-round evaluations, not open-ended conversational loops.

**Rationale**: Open-ended multi-agent discussions frequently suffer from sycophancy cascades — where agents abandon valid criticisms to align with the emerging majority — or become trapped in infinite loops. The courtroom structure guarantees deterministic termination. Isolating Round 1 prevents early anchoring bias; Round 2 rebuttals ensure critical points are tested before final synthesis.

---

## 3. Official APIs vs. Web Scraping

**Decision**: All ingestion layers consume official public APIs (REST, Algolia, OAI-PMH) instead of raw HTML parsing.

**Rationale**: HTML scraping via BeautifulSoup or Playwright is brittle against layout changes and requires ongoing maintenance. Official APIs provide stable schemas, predictable performance, and structured metadata while respecting platform rate limits.

---

## 4. Lobste.rs Over Reddit

**Decision**: Lobste.rs JSON API instead of Reddit API.

**Rationale**: After Reddit's 2023 API policy changes, access requires OAuth registration and imposes restrictive rate limits. Lobste.rs provides a public JSON endpoint with no authentication, delivering clean data focused exclusively on technical and engineering topics.

---

## 5. SQLite vs. PostgreSQL / ORM

**Decision**: SQLite via the standard library `sqlite3` module, no ORM.

**Rationale**: IdeaCouncil is a local autonomous engine operating on a simple two-table schema. SQLite requires zero external server configuration, maintains a single-file footprint, and delivers sub-millisecond query performance. An ORM adds unnecessary overhead at this scale.

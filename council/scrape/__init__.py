"""Scraper orchestrator - combines all sources with deduplication."""

import hashlib
from typing import List

from council.models import Signal
from council.db import is_signal_seen, mark_signal_seen, init_db
from council.scrape.hn import scrape_hn
from council.scrape.arxiv import scrape_arxiv
from council.scrape.devto import scrape_devto
from council.scrape.github import scrape_github
from council.scrape.lobsters import scrape_lobsters


def dict_to_signal(d: dict) -> Signal:
    """Convert a scraper dict to a Signal dataclass."""
    return Signal(
        source=d.get("source", "unknown"),
        title=d.get("title", ""),
        url=d.get("url", ""),
        blurb=d.get("blurb", ""),
        scraped_at=d.get("scraped_at", "")
    )


def scrape_all(max_per_source: int = 30) -> List[Signal]:
    """
    Scrape all sources and return deduplicated signals.
    Checks URL hashes against the seen_signals table.
    """
    init_db()  # Ensure DB exists

    all_signals = []
    seen_count = 0

    # Define scrapers to run
    scrapers = [
        ("GitHub", lambda: scrape_github(max_per_source)),
        ("HN", lambda: scrape_hn()),
        ("arXiv", lambda: scrape_arxiv(max_results=max_per_source)),
        ("DEV.to", lambda: scrape_devto(max_per_source)),
        ("Lobste.rs", lambda: scrape_lobsters(max_per_source)),
    ]

    for source_name, scraper_fn in scrapers:
        try:
            raw_signals = scraper_fn()
            for d in raw_signals:
                sig = dict_to_signal(d)

                # Skip empty URLs
                if not sig.url:
                    continue

                # Check deduplication
                url_hash = hashlib.sha256(sig.url.encode()).hexdigest()

                if is_signal_seen(url_hash):
                    seen_count += 1
                    continue

                # Mark as seen and add to results
                mark_signal_seen(url_hash, sig.url, sig.source, sig.scraped_at)
                all_signals.append(sig)

        except Exception as e:
            print(f"Error scraping {source_name}: {e}")

    print(f"Scraped {len(all_signals)} new signals ({seen_count} duplicates skipped)")
    return all_signals


def batch_signals(signals: List[Signal]) -> str:
    """
    Concatenate Signal objects into a formatted text block for the Ideator.
    """
    lines = ["=== SIGNALS ===\n"]

    for sig in signals:
        lines.append(f"Source: {sig.source}")
        lines.append(f"Title: {sig.title}")
        lines.append(f"Blurb: {sig.blurb}")
        lines.append(f"URL: {sig.url}")
        lines.append("---")

    return "\n".join(lines)


if __name__ == "__main__":
    # Test run
    signals = scrape_all(max_per_source=10)
    print(f"\nTotal new signals: {len(signals)}")
    print("\n--- BATCH OUTPUT ---\n")
    print(batch_signals(signals[:3]))
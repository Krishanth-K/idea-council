#!/usr/bin/env python
"""Testing script for IdeaCouncil with various options."""

import argparse
import sys
from pprint import pprint

import os
from dotenv import load_dotenv
load_dotenv()

from council.db import get_saved_ideas, get_idea_transcript, init_db
from council.scrape import scrape_all
from council.orchestrator import run_council_cycle, run_ideator, run_round1, run_round2, run_judge
from council.models import Signal


# Display current config
print("=" * 50)
print(f"LLM Model: {os.getenv('LLM_MODEL', 'not set')}")
print(f"Ollama Host: {os.getenv('OLLAMA_HOST', 'not set')}")
print("=" * 50)
print()


def cmd_scrape(args):
    """Scrape signals and show them."""
    signals = scrape_all(max_per_source=args.max_per_source)
    print(f"\n=== Scraped {len(signals)} signals ===\n")

    for i, sig in enumerate(signals[:args.limit]):
        print(f"[{i+1}] {sig.source}: {sig.title[:60]}")
        print(f"     {sig.blurb[:80]}...")
        print()


def cmd_ideate(args):
    """Test just the Ideator on one signal."""
    signals = scrape_all(max_per_source=1)
    if not signals:
        print("No signals scraped!")
        return

    signal = signals[args.signal_num - 1] if args.signal_num <= len(signals) else signals[0]
    print(f"\n=== Signal {args.signal_num} ===")
    print(f"Source: {signal.source}")
    print(f"Title: {signal.title}")
    print(f"Blurb: {signal.blurb}")
    print("\n=== Ideator Output ===\n")

    idea = run_ideator(signal)

    if idea.skip:
        print(f"SKIPPED: {idea.skip_reason}")
    else:
        print(f"Title: {idea.title}")
        print(f"One-liner: {idea.one_liner}")
        print(f"Target User: {idea.target_user}")
        print(f"Problem: {idea.problem_it_solves}")
        print(f"Technical Challenge: {idea.core_technical_challenge}")
        print(f"Estimated Scope: {idea.estimated_scope}")


def cmd_debate(args):
    """Test full debate on one signal."""
    signals = scrape_all(max_per_source=1)
    if not signals:
        print("No signals scraped!")
        return

    signal = signals[args.signal_num - 1] if args.signal_num <= len(signals) else signals[0]
    print(f"\n=== Running full debate on signal {args.signal_num} ===")
    print(f"Source: {signal.source} | {signal.title[:50]}...\n")

    verdicts = run_council_cycle([signal])

    if verdicts and verdicts[0]:
        v = verdicts[0]
        print(f"\n=== VERDICT ===")
        print(f"Title: {v.idea_title}")
        print(f"Score: {v.weighted_score}/10")
        print(f"Saved: {v.save}")
        print(f"Summary: {v.summary}")


def cmd_run(args):
    """Run full council cycle on N signals."""
    signals = scrape_all(max_per_source=args.max_per_source)
    if not signals:
        print("No signals scraped!")
        return

    # Limit signals
    signals = signals[:args.limit]
    print(f"\n=== Running council on {len(signals)} signals ===\n")

    verdicts = run_council_cycle(signals)

    # Summary
    saved = [v for v in verdicts if v and v.save]
    print(f"\n=== SUMMARY ===")
    print(f"Total: {len(signals)}")
    print(f"Saved: {len(saved)}")
    print(f"Rejected: {len(signals) - len(saved)}")

    if args.save and saved:
        print(f"\nSaved ideas:")
        for v in saved:
            print(f"  - {v.idea_title} (score: {v.weighted_score})")


def cmd_list(args):
    """List saved ideas."""
    ideas = get_saved_ideas(limit=args.limit)

    if not ideas:
        print("No saved ideas.")
        return

    print(f"=== Saved Ideas ({len(ideas)}) ===\n")
    for idea in ideas:
        print(f"[{idea['id']}] {idea['title']}")
        print(f"    Score: {idea['weighted_score']:.1f}/10")
        print(f"    Summary: {idea['summary'][:80]}...")
        print()


def cmd_transcript(args):
    """View full transcript for an idea."""
    transcript = get_idea_transcript(args.idea_id)

    if not transcript:
        print(f"No idea found with ID {args.idea_id}")
        return

    print(f"\n=== Full Transcript for Idea #{args.idea_id} ===\n")
    print(transcript)


def cmd_recent(args):
    """View transcript of the most recent saved idea."""
    ideas = get_saved_ideas(limit=1)

    if not ideas:
        print("No saved ideas.")
        return

    transcript = get_idea_transcript(ideas[0]['id'])

    print(f"\n=== Most Recent Transcript (ID: {ideas[0]['id']}) ===\n")
    print(transcript)


def main():
    parser = argparse.ArgumentParser(description="IdeaCouncil Testing Script")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # scrape
    p_scrape = subparsers.add_parser("scrape", help="Scrape signals")
    p_scrape.add_argument("--max", dest="max_per_source", type=int, default=5)
    p_scrape.add_argument("--limit", type=int, default=10)

    # ideate
    p_ideate = subparsers.add_parser("ideate", help="Test Ideator on one signal")
    p_ideate.add_argument("--signal", dest="signal_num", type=int, default=1)

    # debate
    p_debate = subparsers.add_parser("debate", help="Test full debate on one signal")
    p_debate.add_argument("--signal", dest="signal_num", type=int, default=1)

    # run
    p_run = subparsers.add_parser("run", help="Run full council cycle")
    p_run.add_argument("--max", dest="max_per_source", type=int, default=5)
    p_run.add_argument("--limit", type=int, default=3, help="Number of signals to process")
    p_run.add_argument("--save", action="store_true", help="Show saved ideas")

    # list
    p_list = subparsers.add_parser("list", help="List saved ideas")
    p_list.add_argument("--limit", type=int, default=10)

    # transcript
    p_trans = subparsers.add_parser("transcript", help="View full transcript")
    p_trans.add_argument("idea_id", type=int, help="Idea ID")

    # recent
    p_recent = subparsers.add_parser("recent", help="View most recent transcript")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        print("\n=== Examples ===")
        print("python test_council.py scrape              # Scrape signals")
        print("python test_council.py ideate              # Test Ideator")
        print("python test_council.py debate             # Test full debate")
        print("python test_council.py run --limit 3      # Run 3 signals")
        print("python test_council.py list              # List saved ideas")
        print("python test_council.py transcript 1       # View transcript ID 1")
        print("python test_council.py recent             # View most recent")
        return

    # Commands
    commands = {
        "scrape": cmd_scrape,
        "ideate": cmd_ideate,
        "debate": cmd_debate,
        "run": cmd_run,
        "list": cmd_list,
        "transcript": cmd_transcript,
        "recent": cmd_recent,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
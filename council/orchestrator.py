"""Courtroom orchestrator - runs the full council cycle."""

from typing import Optional

from council.core import call_llm, call_llm_json
from council.db import save_verdict
from council.models import CycleState, Idea, Signal, Verdict
from council.prompts import (IDEATOR_PROMPT, JUDGE_PROMPT, LAWYER_PROMPTS_R1,
                             LAWYER_PROMPTS_R2)


def run_ideator(signal: Signal) -> Idea:
    """
    Run the Ideator agent to propose a project idea from a single signal.

    Args:
        signal: A single Signal object to feed the Ideator

    Returns:
        Idea object (or Idea with skip=True if signal is insufficient)
    """
    # Format the single signal
    signal_text = f"""
    Source: {signal.source}
    Title: {signal.title}
    Blurb: {signal.blurb}
    URL: {signal.url}"""

    user_prompt = f"""Here is a signal from a source:
    {signal_text}
    Based on this signal, propose a project idea that a solo developer can build.
    The idea should be directly inspired by this signal — use the title, blurb, or context as a starting point."""

    # Call LLM and parse JSON
    try:
        result = call_llm_json(IDEATOR_PROMPT, user_prompt)
        idea = Idea.from_dict(result)

        # Track which signal inspired this idea
        if not idea.skip:
            idea.source_signals = [signal.title]
        return idea
    except ValueError as e:
        # If JSON parsing fails, create a skip idea
        print(f"Ideator error: {e}")
        return Idea(
            title="",
            one_liner="",
            target_user="",
            problem_it_solves="",
            core_technical_challenge="",
            skip=True,
            skip_reason="Failed to parse Ideator response"
        )


def run_round1(idea: Idea) -> dict[str, dict]:
    """
    Run Round 1: Each lawyer evaluates the idea independently.

    Args:
        idea: The Idea to evaluate

    Returns:
        Dictionary mapping dimension -> {score, argument, key_points}
    """
    results = {}

    # Format the idea for the user prompt
    idea_text = f"""Title: {idea.title}
    One-liner: {idea.one_liner}
    Target User: {idea.target_user}
    Problem: {idea.problem_it_solves}
    Technical Challenge: {idea.core_technical_challenge}
    Estimated Scope: {idea.estimated_scope}"""

    for dimension, prompt in LAWYER_PROMPTS_R1.items():
        try:
            result = call_llm_json(prompt, idea_text)
            results[dimension] = {
                "score": result.get("score", 0),
                "argument": result.get("argument", ""),
                "key_points": result.get("key_points", []),
            }
            print(f"  {dimension}: score {result.get('score', '?')}/10")
        except ValueError as e:
            print(f"  {dimension}: error parsing response")
            results[dimension] = {
                "score": 5,  # Default score on error
                "argument": f"Error: {e}",
                "key_points": [],
            }

    return results


def run_round2(idea: Idea, round1_results: dict[str, dict]) -> dict[str, dict]:
    """
    Run Round 2: Each lawyer reads all R1 arguments and delivers a rebuttal.

    Args:
        idea: The Idea being evaluated
        round1_results: Results from Round 1

    Returns:
        Dictionary mapping dimension -> {updated_score, rebuttal}
    """
    results = {}

    # Format Round 1 transcript
    transcript_parts = ["=== ROUND 1: Opening Arguments ===\n"]
    for dim, data in round1_results.items():
        transcript_parts.append(f"\n--- {dim.upper()} Lawyer ---\nScore: {data['score']}/10\n{data['argument']}")

    transcript = "\n".join(transcript_parts)

    # Format idea for the prompt
    idea_text = f"Title: {idea.title}\nOne-liner: {idea.one_liner}"

    for dimension in LAWYER_PROMPTS_R1.keys():
        # Use the R2 prompt template
        prompt = LAWYER_PROMPTS_R2[dimension].replace("{idea}", idea_text)
        prompt = prompt.replace("{transcript}", transcript)

        try:
            result = call_llm_json(prompt, "")
            results[dimension] = {
                "updated_score": result.get("updated_score", round1_results[dimension]["score"]),
                "rebuttal": result.get("rebuttal", ""),
            }
            print(f"  {dimension} R2: score {result.get('updated_score', '?')}/10")
        except ValueError as e:
            print(f"  {dimension} R2: error parsing response")
            results[dimension] = {
                "updated_score": round1_results[dimension]["score"],
                "rebuttal": f"Error: {e}",
            }

    return results


def run_judge(idea: Idea, round1_results: dict, round2_results: dict) -> Verdict:
    """
    Run the Judge to deliver the final verdict.

    Args:
        idea: The Idea being judged
        round1_results: Results from Round 1
        round2_results: Results from Round 2

    Returns:
        Verdict object with scores and save decision
    """
    # Build full transcript
    transcript_parts = [
        "=== IDEA ===",
        f"Title: {idea.title}",
        f"One-liner: {idea.one_liner}",
        f"Target User: {idea.target_user}",
        f"Problem: {idea.problem_it_solves}",
        f"Technical Challenge: {idea.core_technical_challenge}",
        "",
        "=== ROUND 1: Opening Arguments ===",
    ]

    for dim, data in round1_results.items():
        transcript_parts.append(f"\n--- {dim.upper()} ---")
        transcript_parts.append(f"Score: {data['score']}/10")
        transcript_parts.append(data["argument"])

    transcript_parts.append("\n=== ROUND 2: Rebuttals ===")
    for dim, data in round2_results.items():
        transcript_parts.append(f"\n--- {dim.upper()} ---")
        transcript_parts.append(f"Updated Score: {data['updated_score']}/10")
        transcript_parts.append(data["rebuttal"])

    full_transcript = "\n".join(transcript_parts)

    try:
        result = call_llm_json(JUDGE_PROMPT, full_transcript)

        # Extract scores from the result
        scores = result.get("scores", {})

        # Use R2 scores for final verdict
        for dim in scores:
            if dim in round2_results:
                scores[dim] = round2_results[dim]["updated_score"]

        verdict = Verdict(
            idea_title=result.get("idea_title", idea.title),
            one_liner=result.get("one_liner", idea.one_liner),
            scores=scores,
            weighted_score=result.get("weighted_score", 0.0),
            save=result.get("save", False),
            summary=result.get("summary", ""),
            debate_transcript=full_transcript,
        )

        # Apply save thresholds
        verdict.should_save()

        return verdict

    except ValueError as e:
        print(f"Judge error: {e}")
        # Return a default verdict on error
        return Verdict(
            idea_title=idea.title,
            one_liner=idea.one_liner,
            scores={"novelty": 5, "solo_feasibility": 5, "technical_depth": 5,
                    "resume_value": 5, "real_use_case": 5},
            save=False,
            summary=f"Error parsing Judge response: {e}",
            debate_transcript=full_transcript,
        )


def run_council_cycle(signals: list[Signal]) -> list[Optional[Verdict]]:
    """
    Run complete council cycles: one per signal.
    For each signal: Ideate -> Round 1 -> Round 2 -> Judge -> Save.

    Args:
        signals: List of signals to process

    Returns:
        List of Verdict objects (None for skipped ideas)
    """
    print("\n" + "=" * 50)
    print(f"COUNCIL CYCLE STARTING ({len(signals)} signals)")
    print("=" * 50)

    verdicts = []

    for i, signal in enumerate(signals):
        print(f"\n--- Signal {i + 1}/{len(signals)} ---")
        print(f"Source: {signal.source} | {signal.title[:50]}...")

        # Initialize state for this signal
        state = CycleState(signals=[signal])

        # Step 1: Ideator (one idea per signal)
        print("\n[1/4] Running Ideator...")
        state.idea = run_ideator(signal)

        if state.idea.skip:
            print(f"  Skipped: {state.idea.skip_reason}")
            verdicts.append(None)
            continue

        print(f"  Proposed: {state.idea.title}")

        # Step 2: Round 1
        print("\n[2/4] Running Round 1 (Opening Arguments)...")
        state.round1 = run_round1(state.idea)

        # Step 3: Round 2
        print("\n[3/4] Running Round 2 (Cross Examination)...")
        state.round2 = run_round2(state.idea, state.round1)

        # Step 4: Judge
        print("\n[4/4] Running Judge...")
        state.verdict = run_judge(state.idea, state.round1, state.round2)

        # Print verdict summary
        print("\n" + "-" * 30)
        print(f"  Idea: {state.verdict.idea_title}")
        print(f"  Scores: {state.verdict.scores}")
        print(f"  Weighted: {state.verdict.weighted_score}/10")
        print(f"  Save: {state.verdict.save}")

        # Save if threshold met
        if state.verdict.save:
            print("  ✓ Saving to database...")
            save_verdict(state.verdict, state.verdict.debate_transcript)
        else:
            print("  ✗ Rejected")

        verdicts.append(state.verdict)

    # Summary
    saved = sum(1 for v in verdicts if v and v.save)
    print("\n" + "=" * 50)
    print(f"CYCLE COMPLETE: {saved}/{len(signals)} ideas saved")
    print("=" * 50)

    return verdicts


if __name__ == "__main__":
    # Test with a small signal batch
    from council.scrape import scrape_all

    signals = scrape_all(max_per_source=3)
    if signals:
        run_council_cycle(signals[:10])

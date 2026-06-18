"""Courtroom orchestrator - runs the full council cycle."""

from typing import Optional

from council.core import call_llm_json, call_llm
from council.models import Idea, Verdict, CycleState, Signal
from council.prompts import IDEATOR_PROMPT, LAWYER_PROMPTS_R1, LAWYER_PROMPTS_R2, JUDGE_PROMPT
from council.db import save_verdict


def run_ideator(signals: list[Signal]) -> Idea:
    """
    Run the Ideator agent to propose a project idea from signals.

    Args:
        signals: List of Signal objects to feed the Ideator

    Returns:
        Idea object (or Idea with skip=True if batch is insufficient)
    """
    # Format signals into a batch
    signal_text = "\n\n".join([
        f"Source: {s.source}\nTitle: {s.title}\n{s.blurb}"
        for s in signals
    ])

    user_prompt = f"""Here is a batch of signals from various sources:

{signal_text}

Based on these signals, propose ONE project idea that a solo developer can build."""

    # Call LLM and parse JSON
    try:
        result = call_llm_json(IDEATOR_PROMPT, user_prompt)
        return Idea.from_dict(result)
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


def run_council_cycle(signals: list[Signal]) -> Optional[Verdict]:
    """
    Run one complete council cycle: Ideate -> Round 1 -> Round 2 -> Judge.

    Args:
        signals: List of signals to feed the Ideator

    Returns:
        Verdict object if idea was generated, None if skipped
    """
    print("\n" + "=" * 50)
    print("COUNCIL CYCLE STARTING")
    print("=" * 50)

    # Initialize state
    state = CycleState(signals=signals)

    # Step 1: Ideator
    print("\n[1/4] Running Ideator...")
    state.idea = run_ideator(signals)

    if state.idea.skip:
        print(f"  Skipped: {state.idea.skip_reason}")
        return None

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
    print("\n" + "=" * 50)
    print("VERDICT")
    print("=" * 50)
    print(f"  Idea: {state.verdict.idea_title}")
    print(f"  Scores: {state.verdict.scores}")
    print(f"  Weighted: {state.verdict.weighted_score}/10")
    print(f"  Save: {state.verdict.save}")
    print(f"  Summary: {state.verdict.summary[:100]}...")

    # Save if threshold met
    if state.verdict.save:
        print("\n  ✓ Saving to database...")
        save_verdict(state.verdict, state.verdict.debate_transcript)

    return state.verdict


if __name__ == "__main__":
    # Test with a small signal batch
    from council.scrape import scrape_all

    signals = scrape_all(max_per_source=3)
    if signals:
        run_council_cycle(signals[:10])
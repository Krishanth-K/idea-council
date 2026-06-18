"""IdeaCouncil - CLI entry point."""

import typer
from rich.console import Console
from rich.table import Table

from council.scrape import scrape_all, batch_signals
from council.db import get_saved_ideas, init_db

app = typer.Typer()
console = Console()


@app.command()
def scrape(
    max_per_source: int = typer.Option(10, "--max", help="Max signals per source"),
    preview: bool = typer.Option(True, "--preview/--no-preview", help="Show preview of signals"),
):
    """Scrape all sources and show results."""
    console.print("[bold cyan]Scraping sources...[/bold cyan]")
    signals = scrape_all(max_per_source=max_per_source)

    console.print(f"[green]Got {len(signals)} signals[/green]")

    if preview and signals:
        console.print("\n[bold]Sample signals:[/bold]")
        for sig in signals[:5]:
            console.print(f"\n  [{sig.source}] {sig.title}")
            console.print(f"    {sig.blurb[:100]}...")

    # Also show the batched output
    console.print("\n[bold]Batched output (first 800 chars):[/bold]")
    console.print(batch_signals(signals[:10])[:800])


@app.command()
def list(
    limit: int = typer.Option(20, "--limit", help="Max ideas to show"),
):
    """List saved ideas from the database."""
    ideas = get_saved_ideas(limit=limit)

    if not ideas:
        console.print("[yellow]No saved ideas yet.[/yellow]")
        return

    table = Table(title="Saved Ideas")
    table.add_column("ID", style="cyan")
    table.add_column("Title", style="green")
    table.add_column("Score", style="yellow")
    table.add_column("Summary", style="white")

    for idea in ideas:
        table.add_row(
            str(idea["id"]),
            idea["title"][:30],
            f"{idea['weighted_score']:.1f}",
            idea["summary"][:50] if idea["summary"] else ""
        )

    console.print(table)


@app.command()
def init():
    """Initialize the database."""
    init_db()
    console.print("[green]Database initialized![/green]")


@app.command()
def run(
    cycles: int = typer.Option(1, "--cycles", "-n", help="Number of council cycles to run"),
    max_signals: int = typer.Option(10, "--max-signals", help="Max signals per source"),
):
    """Run the full council cycle (scrape -> debate -> judge -> save)."""
    from council.orchestrator import run_council_cycle
    from council.scrape import scrape_all

    console.print(f"[bold cyan]Running {cycles} council cycle(s)...[/bold cyan]")

    for i in range(cycles):
        console.print(f"\n[bold]Cycle {i + 1}/{cycles}[/bold]")

        # Scrape signals
        signals = scrape_all(max_per_source=max_signals)
        if not signals:
            console.print("[yellow]No signals scraped, skipping cycle.[/yellow]")
            continue

        # Run council cycle
        verdict = run_council_cycle(signals)

        if verdict is None:
            console.print("[yellow]Idea was skipped (batch too weak).[/yellow]")
        elif verdict.save:
            console.print(f"[green]✓ Saved: {verdict.idea_title} (score: {verdict.weighted_score})[/green]")
        else:
            console.print(f"[red]✗ Rejected: {verdict.idea_title} (score: {verdict.weighted_score})[/red]")

    console.print("\n[bold cyan]Done![/bold cyan]")


if __name__ == "__main__":
    app()
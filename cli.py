#!/usr/bin/env python3
"""CLI for the NL-to-SQL agent."""

import sys

from dotenv import load_dotenv
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from agent.sql_generator import SQLGenerationError, UnsafeSQLError, generate_sql
from db.schema import execute_query, get_display_name, get_engine

load_dotenv()

console = Console()


def _confidence_color(confidence: float) -> str:
    if confidence >= 0.8:
        return "green"
    if confidence >= 0.5:
        return "yellow"
    return "red"


def _engine_color(engine: str) -> str:
    return "blue" if engine == "postgresql" else "cyan"


def _print_results(rows: list[dict]) -> None:
    if not rows:
        console.print("[dim]No rows returned.[/dim]")
        return

    cols = list(rows[0].keys())
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    for col in cols:
        table.add_column(str(col))

    for row in rows:
        table.add_row(*[str(v) if v is not None else "[dim]NULL[/dim]" for v in row.values()])

    console.print(table)
    console.print(f"[dim]{len(rows)} row(s) returned[/dim]")


def run_query(question: str) -> None:
    console.print()
    console.print(Panel(f"[bold]{question}[/bold]", title="Question", border_style="blue"))

    with console.status("[bold blue]Generating SQL…[/bold blue]", spinner="dots"):
        try:
            result = generate_sql(question)
        except UnsafeSQLError as exc:
            console.print(f"\n[bold red]Safety check failed:[/bold red] {exc}")
            return
        except SQLGenerationError as exc:
            console.print(f"\n[bold red]Generation error:[/bold red] {exc}")
            return

    # --- SQL panel ---
    sql_syntax = Syntax(result.sql, "sql", theme="monokai", line_numbers=False, word_wrap=True)
    console.print(Panel(sql_syntax, title="Generated SQL", border_style="green"))

    # --- Confidence + explanation ---
    color = _confidence_color(result.confidence)
    console.print(
        f"[bold]Confidence:[/bold] [{color}]{result.confidence:.0%}[/{color}]  "
        f"[dim]|[/dim]  [bold]Explanation:[/bold] {result.explanation}"
    )
    console.print()

    # --- Execute ---
    try:
        rows = execute_query(result.sql)
    except Exception as exc:
        console.print(f"[bold red]Execution error:[/bold red] {exc}")
        return

    _print_results(rows)
    console.print()


def _header_panel() -> Panel:
    engine = get_engine()
    display = get_display_name()
    color = _engine_color(engine)
    engine_label = "PostgreSQL" if engine == "postgresql" else "SQLite"
    return Panel(
        f"[bold cyan]NL-to-SQL Agent[/bold cyan]\n"
        f"[dim]Connected to:[/dim] [{color}]{engine_label}[/{color}]  [dim]{display}[/dim]\n"
        f"[dim]Ask questions in plain English. Type [bold]exit[/bold] or Ctrl-C to quit.[/dim]",
        border_style="cyan",
    )


def interactive_loop() -> None:
    console.print(_header_panel())

    while True:
        try:
            question = console.input("[bold cyan]>[/bold cyan] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        if not question:
            continue
        if question.lower() in ("exit", "quit", "q"):
            console.print("[dim]Goodbye.[/dim]")
            break

        run_query(question)


def main() -> None:
    # Only seed the demo SQLite DB; skip if pointed at PostgreSQL
    if get_engine() == "sqlite":
        try:
            from db.seed import seed_db
            seed_db()
        except Exception as exc:
            console.print(f"[yellow]Warning: DB seed skipped — {exc}[/yellow]")

    if len(sys.argv) > 1:
        engine = get_engine()
        display = get_display_name()
        color = _engine_color(engine)
        engine_label = "PostgreSQL" if engine == "postgresql" else "SQLite"
        console.print(
            f"[dim]Connected to:[/dim] [{color}]{engine_label}[/{color}]  [dim]{display}[/dim]"
        )
        question = " ".join(sys.argv[1:])
        run_query(question)
    else:
        interactive_loop()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""CLI for the NL-to-SQL agent."""

import os
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

_HELP_TEXT = """\
[bold]Meta-commands[/bold] (start with /)
  [cyan]/db[/cyan]                        Show current connection
  [cyan]/connect <url>[/cyan]             Switch to PostgreSQL
                               e.g.  /connect postgresql://user:pass@localhost:5432/mydb
  [cyan]/connect sqlite[/cyan]            Switch back to SQLite (demo database)
  [cyan]/connect sqlite <path>[/cyan]     Switch to a specific SQLite file
  [cyan]/help[/cyan]                      Show this message
  [cyan]exit[/cyan] / [cyan]quit[/cyan] / Ctrl-C        Quit

Anything else is treated as a natural language question.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _confidence_color(confidence: float) -> str:
    if confidence >= 0.8:
        return "green"
    if confidence >= 0.5:
        return "yellow"
    return "red"


def _engine_color(engine: str) -> str:
    return "blue" if engine == "postgresql" else "cyan"


def _connection_line() -> str:
    engine = get_engine()
    display = get_display_name()
    color = _engine_color(engine)
    label = "PostgreSQL" if engine == "postgresql" else "SQLite"
    return f"[dim]Connected to:[/dim] [{color}]{label}[/{color}]  [dim]{display}[/dim]"


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


# ---------------------------------------------------------------------------
# Meta-command handler
# ---------------------------------------------------------------------------

def _handle_meta(command: str) -> bool:
    """Handle a /command. Returns True if it was a meta-command, False otherwise."""
    parts = command.strip().split(None, 2)
    cmd = parts[0].lower()

    if cmd == "/help":
        console.print(Panel(_HELP_TEXT.strip(), title="Help", border_style="dim"))
        return True

    if cmd == "/db":
        console.print(_connection_line())
        return True

    if cmd == "/connect":
        if len(parts) < 2:
            console.print("[yellow]Usage: /connect <postgresql-url>  or  /connect sqlite  or  /connect sqlite <path>[/yellow]")
            return True

        target = parts[1].lower()

        # Switch to SQLite
        if target == "sqlite":
            os.environ.pop("DATABASE_URL", None)
            if len(parts) == 3:
                os.environ["DB_PATH"] = parts[2]
            else:
                os.environ.pop("DB_PATH", None)

            # Seed if pointing at the default demo DB
            if get_engine() == "sqlite":
                try:
                    from db.seed import seed_db
                    seed_db()
                except Exception as exc:
                    console.print(f"[yellow]Seed skipped: {exc}[/yellow]")

            console.print(f"[green]✓[/green] Switched — {_connection_line()}")
            return True

        # Switch to PostgreSQL (or any other DATABASE_URL)
        url = parts[1]  # preserve original case for the URL
        if len(parts) == 3:
            url = parts[1] + " " + parts[2]  # shouldn't happen, but be safe

        if not (url.startswith("postgres://") or url.startswith("postgresql://")):
            console.print("[yellow]URL should start with postgresql:// — setting anyway.[/yellow]")

        os.environ["DATABASE_URL"] = url

        # Verify the connection
        try:
            execute_query("SELECT 1")
            console.print(f"[green]✓[/green] Switched — {_connection_line()}")
        except Exception as exc:
            os.environ.pop("DATABASE_URL", None)
            console.print(f"[bold red]Connection failed:[/bold red] {exc}")
            console.print(f"[dim]Reverted to previous connection — {_connection_line()}[/dim]")
        return True

    return False


# ---------------------------------------------------------------------------
# Query runner
# ---------------------------------------------------------------------------

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

    sql_syntax = Syntax(result.sql, "sql", theme="monokai", line_numbers=False, word_wrap=True)
    console.print(Panel(sql_syntax, title="Generated SQL", border_style="green"))

    color = _confidence_color(result.confidence)
    console.print(
        f"[bold]Confidence:[/bold] [{color}]{result.confidence:.0%}[/{color}]  "
        f"[dim]|[/dim]  [bold]Explanation:[/bold] {result.explanation}"
    )
    console.print()

    try:
        rows = execute_query(result.sql)
    except Exception as exc:
        console.print(f"[bold red]Execution error:[/bold red] {exc}")
        return

    _print_results(rows)
    console.print()


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def _header_panel() -> Panel:
    engine = get_engine()
    display = get_display_name()
    color = _engine_color(engine)
    label = "PostgreSQL" if engine == "postgresql" else "SQLite"
    return Panel(
        f"[bold cyan]NL-to-SQL Agent[/bold cyan]\n"
        f"[dim]Connected to:[/dim] [{color}]{label}[/{color}]  [dim]{display}[/dim]\n"
        f"[dim]Ask questions in plain English · [bold]/help[/bold] for commands · "
        f"[bold]exit[/bold] or Ctrl-C to quit[/dim]",
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
        if question.startswith("/"):
            _handle_meta(question)
            continue

        run_query(question)


def main() -> None:
    if get_engine() == "sqlite":
        try:
            from db.seed import seed_db
            seed_db()
        except Exception as exc:
            console.print(f"[yellow]Warning: DB seed skipped — {exc}[/yellow]")

    if len(sys.argv) > 1:
        console.print(_connection_line())
        question = " ".join(sys.argv[1:])
        run_query(question)
    else:
        interactive_loop()


if __name__ == "__main__":
    main()

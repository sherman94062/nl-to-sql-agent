#!/usr/bin/env python3
"""Run the evaluation harness and print a summary report."""

import sys

from dotenv import load_dotenv
from rich import box
from rich.console import Console
from rich.table import Table

from db.seed import seed_db
from eval.harness import DEFAULT_CASES, run_eval

load_dotenv()
console = Console()


def main() -> None:
    console.print("\n[bold cyan]NL-to-SQL Evaluation Harness[/bold cyan]\n")

    # Ensure DB is ready
    seed_db()

    cases = DEFAULT_CASES
    console.print(f"Running [bold]{len(cases)}[/bold] eval cases…\n")

    results = run_eval(cases)

    # --- Summary table ---
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold")
    table.add_column("ID", style="dim")
    table.add_column("Question", max_width=40)
    table.add_column("Pass", justify="center")
    table.add_column("Confidence", justify="right")
    table.add_column("Rows", justify="right")
    table.add_column("Latency", justify="right")
    table.add_column("Error / SQL (truncated)", max_width=50)

    passed = 0
    for r in results:
        status = "[green]✓[/green]" if r.passed else "[red]✗[/red]"
        if r.passed:
            passed += 1

        conf = f"{r.sql_result.confidence:.0%}" if r.sql_result else "—"
        rows = str(len(r.rows)) if r.sql_result else "—"
        latency = f"{r.latency_ms:.0f}ms"
        detail = (r.error or (r.sql_result.sql[:60] + "…" if r.sql_result else ""))

        table.add_row(r.case.id, r.case.question, status, conf, rows, latency, detail)

    console.print(table)

    total = len(results)
    color = "green" if passed == total else ("yellow" if passed >= total // 2 else "red")
    console.print(
        f"\n[{color}]Results: {passed}/{total} passed[/{color}]  "
        f"| Avg latency: {sum(r.latency_ms for r in results)/total:.0f}ms\n"
    )

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()

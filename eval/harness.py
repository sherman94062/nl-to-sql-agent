"""Evaluation harness for the NL-to-SQL agent (Phase 2 will expand this)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from agent.sql_generator import SQLGenerationError, SQLResult, generate_sql
from db.schema import execute_query


@dataclass
class EvalCase:
    """A single evaluation test case."""
    id: str
    question: str
    expected_columns: list[str] | None = None   # column names that must appear in results
    min_rows: int | None = None                  # minimum number of result rows expected
    max_rows: int | None = None                  # maximum number of result rows expected
    notes: str = ""


@dataclass
class EvalResult:
    """Result for a single eval case."""
    case: EvalCase
    sql_result: SQLResult | None = None
    rows: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    latency_ms: float = 0.0

    @property
    def passed(self) -> bool:
        if self.error:
            return False
        if self.sql_result is None:
            return False
        c = self.case
        if c.expected_columns:
            if not self.rows:
                return False
            actual_cols = set(self.rows[0].keys())
            if not set(c.expected_columns).issubset(actual_cols):
                return False
        if c.min_rows is not None and len(self.rows) < c.min_rows:
            return False
        if c.max_rows is not None and len(self.rows) > c.max_rows:
            return False
        return True


def run_eval(cases: list[EvalCase]) -> list[EvalResult]:
    """Run a list of eval cases and return results."""
    results: list[EvalResult] = []

    for case in cases:
        t0 = time.monotonic()
        try:
            sql_result = generate_sql(case.question)
            rows = execute_query(sql_result.sql)
            latency = (time.monotonic() - t0) * 1000
            results.append(EvalResult(case=case, sql_result=sql_result, rows=rows, latency_ms=latency))
        except Exception as exc:
            latency = (time.monotonic() - t0) * 1000
            results.append(EvalResult(case=case, error=str(exc), latency_ms=latency))

    return results


# Default eval suite (Phase 1 scaffold — expand in Phase 2)
DEFAULT_CASES: list[EvalCase] = [
    EvalCase(
        id="basic-customers",
        question="List all customers from California",
        expected_columns=["name", "email"],
        min_rows=1,
    ),
    EvalCase(
        id="top-products",
        question="What are the 5 most expensive products?",
        expected_columns=["name", "price"],
        min_rows=1,
        max_rows=5,
    ),
    EvalCase(
        id="order-count",
        question="How many orders are in each status?",
        expected_columns=["status"],
        min_rows=1,
    ),
    EvalCase(
        id="revenue-by-category",
        question="What is the total revenue by product category?",
        expected_columns=["category"],
        min_rows=1,
    ),
    EvalCase(
        id="low-inventory",
        question="Which products have fewer than 10 units in stock across all warehouses?",
        expected_columns=["name"],
    ),
    EvalCase(
        id="customer-orders",
        question="Show me the customers who have placed more than 2 orders",
        expected_columns=["name"],
    ),
]

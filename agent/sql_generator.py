"""SQL generator: converts natural language questions to SQL via Claude."""

import os
import re

import anthropic
import sqlparse
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

# Patterns that indicate unsafe (mutating) SQL operations
_UNSAFE_PATTERN = re.compile(
    r"\b(DROP|DELETE|TRUNCATE|ALTER|INSERT|UPDATE|CREATE|REPLACE|ATTACH)\b",
    re.IGNORECASE,
)


class SQLResult(BaseModel):
    sql: str
    explanation: str
    confidence: float


class SQLGenerationError(Exception):
    pass


class UnsafeSQLError(SQLGenerationError):
    pass


def validate_sql_safety(sql: str) -> None:
    """Raise UnsafeSQLError if the query contains any mutating operations."""
    match = _UNSAFE_PATTERN.search(sql)
    if match:
        raise UnsafeSQLError(
            f"Query contains unsafe operation '{match.group().upper()}'. "
            "Only SELECT queries are permitted."
        )


def _build_system_prompt(schema: str, engine: str) -> str:
    dialect = "PostgreSQL" if engine == "postgresql" else "SQLite"
    date_hint = (
        "Use NOW(), CURRENT_DATE, and INTERVAL for date arithmetic."
        if engine == "postgresql"
        else "Use strftime('%Y-%m-%d', 'now') and datetime('now', '-N days') for date arithmetic."
    )
    return f"""You are an expert SQL assistant specializing in {dialect}.
Convert natural language questions into correct, efficient {dialect} SELECT queries.

{schema}

Rules:
- Generate ONLY SELECT queries — never INSERT, UPDATE, DELETE, DROP, TRUNCATE, ALTER, or CREATE.
- Use proper {dialect} syntax. {date_hint}
- Use table aliases when joining multiple tables for readability.
- Include ORDER BY when the question implies ranked or sorted results.
- Use LIMIT when the question asks for "top N" or "most/least".
- Set confidence (0.0–1.0) to reflect how certain you are the query answers the question correctly.
  Use lower confidence when the question is ambiguous or requires assumptions.
"""


def generate_sql(question: str) -> SQLResult:
    """Generate a SQL query from a natural language question.

    Introspects the configured database (SQLite or PostgreSQL) for schema context
    and asks Claude to generate the appropriate dialect.

    Returns:
        SQLResult with sql, explanation, and confidence.

    Raises:
        UnsafeSQLError: If the generated SQL contains mutating operations.
        SQLGenerationError: If the model fails to return a valid structured response.
    """
    from db.schema import get_engine, get_schema_description

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SQLGenerationError(
            "ANTHROPIC_API_KEY environment variable is not set. "
            "Copy .env.example to .env and add your key."
        )

    engine = get_engine()
    schema = get_schema_description()
    system_prompt = _build_system_prompt(schema, engine)

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.parse(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": question}],
        output_format=SQLResult,
    )

    result = response.parsed_output
    if result is None:
        raise SQLGenerationError(
            "Model returned a refusal or unparseable response. "
            f"Stop reason: {response.stop_reason}"
        )

    # Validate safety before formatting so the error message shows the raw SQL
    validate_sql_safety(result.sql)

    # Pretty-print with sqlparse
    result.sql = sqlparse.format(
        result.sql,
        reindent=True,
        keyword_case="upper",
        strip_comments=True,
    ).strip()

    return result

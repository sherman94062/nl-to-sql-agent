"""SQL generator: converts natural language questions to SQLite queries via Claude."""

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

SCHEMA_DESCRIPTION = """
E-commerce SQLite database schema:

Table: customers
  - id          INTEGER PRIMARY KEY AUTOINCREMENT
  - name        TEXT NOT NULL
  - email       TEXT UNIQUE NOT NULL
  - phone       TEXT
  - address     TEXT
  - city        TEXT
  - state       TEXT        -- 2-letter US abbreviation, e.g. 'CA', 'OR', 'TX'
  - country     TEXT
  - created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP

Table: products
  - id          INTEGER PRIMARY KEY AUTOINCREMENT
  - name        TEXT NOT NULL
  - description TEXT
  - category    TEXT NOT NULL
  - price       REAL NOT NULL
  - sku         TEXT UNIQUE NOT NULL

Table: inventory
  - id          INTEGER PRIMARY KEY AUTOINCREMENT
  - product_id  INTEGER NOT NULL REFERENCES products(id)
  - quantity    INTEGER NOT NULL DEFAULT 0
  - warehouse   TEXT NOT NULL
  - updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP

Table: orders
  - id           INTEGER PRIMARY KEY AUTOINCREMENT
  - customer_id  INTEGER NOT NULL REFERENCES customers(id)
  - status       TEXT NOT NULL  -- one of: pending, processing, shipped, delivered, cancelled
  - total_amount REAL NOT NULL
  - created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  - shipped_at   TIMESTAMP

Table: order_items
  - id          INTEGER PRIMARY KEY AUTOINCREMENT
  - order_id    INTEGER NOT NULL REFERENCES orders(id)
  - product_id  INTEGER NOT NULL REFERENCES products(id)
  - quantity    INTEGER NOT NULL
  - unit_price  REAL NOT NULL

Relationships:
  - orders.customer_id → customers.id
  - order_items.order_id → orders.id
  - order_items.product_id → products.id
  - inventory.product_id → products.id
"""

SYSTEM_PROMPT = f"""You are an expert SQL assistant specializing in SQLite.
Convert natural language questions into correct, efficient SQLite SELECT queries.

{SCHEMA_DESCRIPTION}

Rules:
- Generate ONLY SELECT queries — never INSERT, UPDATE, DELETE, DROP, TRUNCATE, ALTER, or CREATE.
- Use proper SQLite syntax (e.g., strftime for dates, LIKE for pattern matching).
- Use table aliases when joining multiple tables for readability.
- Include ORDER BY when the question implies ranked or sorted results.
- Use LIMIT when the question asks for "top N" or "most/least".
- Set confidence (0.0–1.0) to reflect how certain you are the query answers the question correctly.
  Use lower confidence when the question is ambiguous or requires assumptions.
"""


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


def generate_sql(question: str) -> SQLResult:
    """Generate a SQL query from a natural language question.

    Args:
        question: Natural language question about the e-commerce database.

    Returns:
        SQLResult with sql, explanation, and confidence.

    Raises:
        UnsafeSQLError: If the generated SQL contains mutating operations.
        SQLGenerationError: If the model fails to return a valid structured response.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SQLGenerationError(
            "ANTHROPIC_API_KEY environment variable is not set. "
            "Copy .env.example to .env and add your key."
        )

    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.parse(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
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

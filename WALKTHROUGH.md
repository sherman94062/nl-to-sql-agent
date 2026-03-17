# Walkthrough: NL-to-SQL Agent

This document explains the architecture, design decisions, and every meaningful code path in the project. Read this if you want to understand how it works before extending it.

---

## Table of Contents

1. [Project overview](#1-project-overview)
2. [Directory layout](#2-directory-layout)
3. [The database layer (`db/`)](#3-the-database-layer-db)
4. [The agent (`agent/sql_generator.py`)](#4-the-agent-agentsql_generatorpy)
5. [The CLI (`cli.py`)](#5-the-cli-clipy)
6. [The evaluation harness (`eval/`)](#6-the-evaluation-harness-eval)
7. [The eval runner (`run_eval.py`)](#7-the-eval-runner-run_evalpy)
8. [Request lifecycle — end to end](#8-request-lifecycle--end-to-end)
9. [Design decisions](#9-design-decisions)
10. [Extending the project](#10-extending-the-project)

---

## 1. Project Overview

The agent answers questions like:

> *"Which customers haven't placed an order in the last 60 days?"*

by:
1. Sending the question (plus the full DB schema) to Claude via the Anthropic API.
2. Receiving a structured `SQLResult` — not raw text, a validated Pydantic object.
3. Safety-checking the SQL, executing it against a local SQLite database, and printing the results.

The entire flow is synchronous and CLI-first. There is no web server, no ORM, no query builder — just Python calling the Anthropic API and SQLite.

---

## 2. Directory Layout

```
nl-to-sql-agent/
├── agent/
│   ├── __init__.py
│   └── sql_generator.py      ← the brain
├── db/
│   ├── __init__.py
│   ├── schema.py             ← table definitions + connection helper
│   └── seed.py               ← demo data
├── eval/
│   ├── __init__.py
│   └── harness.py            ← test case definitions + runner logic
├── cli.py                    ← entry point for humans
├── run_eval.py               ← entry point for automated evals
├── .env.example
├── requirements.txt
├── README.md
└── WALKTHROUGH.md            ← you are here
```

Each subdirectory is a Python package (`__init__.py`). Imports always use fully-qualified paths (e.g. `from db.schema import get_connection`) so the project works when run from the repo root.

---

## 3. The Database Layer (`db/`)

### `db/schema.py` — table definitions and connection

```python
def get_db_path() -> Path:
    return Path(os.environ.get("DB_PATH", str(_DEFAULT_DB_PATH)))
```

The DB path defaults to `db/ecommerce.db` but can be overridden via the `DB_PATH` environment variable. This matters for testing (you can point tests at an in-memory or temp DB).

```python
def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row          # rows behave like dicts
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
```

`row_factory = sqlite3.Row` means every row supports both `row["column_name"]` and `dict(row)`. Foreign key enforcement is off by default in SQLite — we turn it on.

```python
def init_db(db_path: Path | None = None) -> Path:
    ...
    conn.executescript(_CREATE_TABLES_SQL)
```

`init_db` is idempotent (uses `CREATE TABLE IF NOT EXISTS`). It's safe to call on every startup.

#### Schema design

Five tables cover a realistic e-commerce slice:

| Table | Purpose |
|---|---|
| `customers` | End users, including city/state for geographic queries |
| `products` | Catalog items with category and SKU |
| `inventory` | Stock levels per product per warehouse |
| `orders` | Customer purchases with status lifecycle |
| `order_items` | Line items linking orders to products |

The `orders.status` column has a `CHECK` constraint (`pending / processing / shipped / delivered / cancelled`) so invalid values are rejected at the DB level, not just in application code.

### `db/seed.py` — demo data

`seed_db()` is idempotent: it checks whether customers already exist before inserting.

```python
existing = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
if existing > 0 and not force:
    return
```

Pass `force=True` to wipe and re-seed (useful during development).

The seed generates:
- **25 customers** across 15 US states
- **30 products** in 6 categories (Electronics, Books, Office, Clothing, Health, Kitchen)
- **66 inventory entries** (1–3 warehouses per product, randomised quantities 0–200)
- **80 orders** with realistic status distribution (55% delivered, 20% shipped, 10% processing, 10% cancelled, 5% pending)
- **~238 order_items** (1–5 line items per order)

`random.seed(42)` makes the data reproducible across runs.

---

## 4. The Agent (`agent/sql_generator.py`)

This is the core of the project. It has three responsibilities:

1. Define the data contract (`SQLResult`)
2. Build the prompt (system + user message)
3. Call the API, validate the output, and apply safety checks

### The output schema

```python
class SQLResult(BaseModel):
    sql: str
    explanation: str
    confidence: float
```

This Pydantic model is the contract between the agent and the rest of the application. Claude is not asked to return freeform text — it is constrained to return exactly these three fields.

### The system prompt

```python
SCHEMA_DESCRIPTION = """
E-commerce SQLite database schema:

Table: customers
  - id          INTEGER PRIMARY KEY AUTOINCREMENT
  - state       TEXT   -- 2-letter US abbreviation, e.g. 'CA', 'OR', 'TX'
  ...
"""
```

The full schema is embedded verbatim in the system prompt. This is intentional: Claude needs to know column names, types, and constraints to generate correct SQL without hallucinating column names. The note about 2-letter state abbreviations is a concrete example of why schema comments matter — without it, the model generates `WHERE state = 'California'` instead of `WHERE state = 'CA'`.

### The API call

```python
response = client.messages.parse(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    system=SYSTEM_PROMPT,
    messages=[{"role": "user", "content": question}],
    output_format=SQLResult,
)
result = response.parsed_output
```

`client.messages.parse()` is the Anthropic SDK's structured-output endpoint. It:
- Sends the schema to Claude as a JSON schema derived from the Pydantic model
- Forces Claude's response to conform to that schema
- Validates and deserialises the response into a `SQLResult` instance

`response.parsed_output` is `None` if the model refused or returned something unparseable (`stop_reason == "refusal"`). We check for this explicitly and raise `SQLGenerationError`.

### Safety validation

```python
_UNSAFE_PATTERN = re.compile(
    r"\b(DROP|DELETE|TRUNCATE|ALTER|INSERT|UPDATE|CREATE|REPLACE|ATTACH)\b",
    re.IGNORECASE,
)

def validate_sql_safety(sql: str) -> None:
    match = _UNSAFE_PATTERN.search(sql)
    if match:
        raise UnsafeSQLError(...)
```

This is a defence-in-depth layer. The system prompt already tells Claude to only generate `SELECT` queries, but we also check the output before executing anything. The `\b` word-boundary anchors prevent false positives on column names that contain these strings (e.g. a column named `last_updated`).

`validate_sql_safety` runs *before* `sqlparse.format()` so the error message shows the raw SQL from the model, not the formatted version.

### SQL formatting

```python
result.sql = sqlparse.format(
    result.sql,
    reindent=True,
    keyword_case="upper",
    strip_comments=True,
).strip()
```

This normalises the SQL for display: uppercase keywords, consistent indentation, no inline comments. It's cosmetic — the query is semantically unchanged.

### Error hierarchy

```
Exception
└── SQLGenerationError        ← base class for all agent errors
    └── UnsafeSQLError        ← blocked by safety check
```

Callers only need to catch `SQLGenerationError` to handle all agent failures.

---

## 5. The CLI (`cli.py`)

The CLI has two modes:

```python
if len(sys.argv) > 1:
    question = " ".join(sys.argv[1:])
    run_query(question)         # non-interactive
else:
    interactive_loop()          # REPL
```

### `run_query(question)`

This is the core rendering function. It:

1. Shows the question in a blue panel.
2. Calls `generate_sql()` inside a Rich spinner (so the terminal doesn't look frozen).
3. Renders the SQL in a green panel with Monokai syntax highlighting via `rich.syntax.Syntax`.
4. Prints confidence (green ≥ 80%, yellow ≥ 50%, red < 50%) and explanation inline.
5. Executes the SQL and renders rows in a `rich.table.Table`.

```python
def _confidence_color(confidence: float) -> str:
    if confidence >= 0.8:
        return "green"
    if confidence >= 0.5:
        return "yellow"
    return "red"
```

The confidence coloring gives quick visual feedback on how reliable the generated query is. A red confidence score is a cue to review the SQL before trusting the results.

### Error handling in the CLI

```python
try:
    result = generate_sql(question)
except UnsafeSQLError as exc:
    console.print(f"\n[bold red]Safety check failed:[/bold red] {exc}")
    return
except SQLGenerationError as exc:
    console.print(f"\n[bold red]Generation error:[/bold red] {exc}")
    return
```

Errors are printed inline without crashing the REPL. The interactive loop continues after an error.

---

## 6. The Evaluation Harness (`eval/harness.py`)

The harness provides a structured way to define expected behaviour and measure it.

### `EvalCase`

```python
@dataclass
class EvalCase:
    id: str
    question: str
    expected_columns: list[str] | None = None
    min_rows: int | None = None
    max_rows: int | None = None
    notes: str = ""
```

Each test case specifies what the result *must* contain. Checks are deliberately loose (columns that must appear, row count bounds) rather than exact (specific cell values), because the model may legitimately include extra columns or vary ordering.

### `EvalResult.passed`

```python
@property
def passed(self) -> bool:
    if self.error:
        return False
    if c.expected_columns:
        actual_cols = set(self.rows[0].keys())
        if not set(c.expected_columns).issubset(actual_cols):
            return False
    if c.min_rows is not None and len(self.rows) < c.min_rows:
        return False
    if c.max_rows is not None and len(self.rows) > c.max_rows:
        return False
    return True
```

A case passes if:
- No exception was raised (generation *or* execution)
- All `expected_columns` appear in the result columns (subset check, not equality)
- Row count is within `[min_rows, max_rows]`

### Default test suite

The 6 built-in cases cover distinct SQL patterns:

| Case | SQL pattern tested |
|---|---|
| `basic-customers` | `WHERE state = 'CA'` — simple filter |
| `top-products` | `ORDER BY price DESC LIMIT 5` — sorting + limit |
| `order-count` | `GROUP BY status` — scalar aggregation |
| `revenue-by-category` | JOIN + `SUM()` — multi-table aggregation |
| `low-inventory` | `HAVING SUM(quantity) < 10` — post-aggregation filter |
| `customer-orders` | `HAVING COUNT(*) > 2` — aggregation on foreign key |

---

## 7. The Eval Runner (`run_eval.py`)

```python
results = run_eval(cases)
```

`run_eval()` loops over cases, calls `generate_sql()` + executes the SQL, records latency, and catches errors without short-circuiting. Every case produces an `EvalResult` regardless of success or failure.

The runner prints a Rich table with one row per case, then exits with code `0` if all pass, `1` otherwise. This makes it usable in CI pipelines:

```bash
python run_eval.py || echo "eval failed"
```

---

## 8. Request Lifecycle — End to End

Here is what happens when you type a question:

```
User types: "Which warehouses have more than 100 units of Electronics?"

cli.py
  └─ seed_db()          ← ensure DB exists (no-op if already seeded)
  └─ run_query(question)
       └─ generate_sql(question)              [agent/sql_generator.py]
            ├─ build system prompt (schema embedded)
            ├─ client.messages.parse(...)     [Anthropic API]
            │     Claude receives: schema + question
            │     Claude returns: {"sql": "...", "explanation": "...", "confidence": 0.9}
            │     SDK validates against SQLResult Pydantic schema
            ├─ validate_sql_safety(result.sql)
            └─ sqlparse.format(result.sql)
       └─ [Rich panel: formatted SQL]
       └─ [Rich inline: confidence + explanation]
       └─ conn.execute(result.sql).fetchall() [db/schema.py]
       └─ [Rich table: query results]
```

Total round-trips to external services: **1** (the Anthropic API call). Everything else is local.

---

## 9. Design Decisions

### Why structured outputs instead of prompting for JSON?

Prompting Claude to "respond in JSON" works most of the time but occasionally produces:
- Markdown code fences around the JSON
- Trailing commas
- Extra commentary before/after the JSON block

`client.messages.parse()` with a Pydantic schema eliminates all of these. The SDK enforces the schema at the API level — you either get a valid `SQLResult` or an explicit error.

### Why SQLite?

- No setup: `sqlite3` is in the Python standard library.
- The whole database is a single file, easy to reset or share.
- Supports enough SQL for interesting queries (window functions, CTEs, `strftime`).
- The eval harness can use a temporary in-memory DB (`:memory:`) for isolation.

### Why include the full schema in every system prompt?

The alternative — dynamically selecting relevant tables — would require an extra LLM call or a semantic search step. For a 5-table schema, the full schema fits comfortably in the context window and avoids any risk of the model missing a relevant table. For schemas with 50+ tables, dynamic schema selection becomes worthwhile.

### Why `\b` word boundaries in the safety regex?

Without them, `DROP` would match inside column names like `drop_date` or string literals. The `\b` anchors ensure only the standalone keywords are caught.

### Why is `confidence` a float instead of an enum?

A continuous score (0.0–1.0) is more informative than Low/Medium/High. The CLI uses thresholds (≥ 0.8 = green, ≥ 0.5 = yellow, < 0.5 = red) to convert it to a visual signal. Applications that need to gate on confidence (e.g. "only execute if confidence > 0.7") can use the raw float.

---

## 10. Extending the Project

### Add a new eval case

Edit `eval/harness.py` and append to `DEFAULT_CASES`:

```python
EvalCase(
    id="never-ordered",
    question="Which products have never been ordered?",
    expected_columns=["name"],
    notes="Requires LEFT JOIN or NOT IN subquery",
),
```

### Use a different model

Change the `model` parameter in `agent/sql_generator.py`. Any model that supports `client.messages.parse()` works (currently `claude-sonnet-4-6`, `claude-opus-4-6`, `claude-haiku-4-5`).

### Add your own database

1. Replace `_CREATE_TABLES_SQL` in `db/schema.py` with your schema.
2. Update `SCHEMA_DESCRIPTION` in `agent/sql_generator.py` to describe your tables.
3. Replace the seed data in `db/seed.py`.

### Add a confidence threshold gate

In `cli.py`, after calling `generate_sql()`:

```python
if result.confidence < 0.6:
    console.print("[yellow]Low confidence — review the SQL before trusting results.[/yellow]")
    if not Confirm.ask("Execute anyway?"):
        return
```

### Run evals in CI

```yaml
# .github/workflows/eval.yml
- name: Run eval suite
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  run: python run_eval.py
```

### Phase 2 ideas

- **Expanded eval suite** — 50+ cases covering edge cases (NULLs, date arithmetic, subqueries, CTEs)
- **Auto-correction loop** — if the SQL fails to execute, feed the error back to Claude and retry
- **Query caching** — cache `(question_hash, schema_hash) → SQLResult` to avoid redundant API calls
- **Schema introspection** — derive `SCHEMA_DESCRIPTION` automatically from `sqlite_master` instead of maintaining it by hand
- **Web UI** — a minimal FastAPI + HTMX frontend over the same `generate_sql()` function

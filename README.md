# NL-to-SQL Agent

Ask a question in plain English. Get back a SQL query, an explanation, a confidence score, and live results — all in your terminal.

Powered by **Claude** (`claude-sonnet-4-6`) with **Pydantic structured outputs** and a **Rich** CLI.

---

## Demo

```
> What are the top 5 best-selling products?

╭─────────────────────────────── Generated SQL ───────────────────────────────╮
│ SELECT p.name,                                                               │
│        p.category,                                                           │
│        SUM(oi.quantity) AS total_sold                                        │
│ FROM order_items oi                                                          │
│ JOIN products p ON p.id = oi.product_id                                     │
│ GROUP BY p.id                                                                │
│ ORDER BY total_sold DESC                                                     │
│ LIMIT 5                                                                      │
╰──────────────────────────────────────────────────────────────────────────────╯
Confidence: 98%  |  Joins order_items with products, sums quantity per product.

╭─────────────────────────────── Results ──────────────────────────────────────╮
│ name                    │ category    │ total_sold │
│ Wireless Headphones     │ Electronics │ 24         │
│ Clean Code              │ Books       │ 21         │
│ ...                                                │
╰──────────────────────────────────────────────────────────────────────────────╯
```

---

## Features

- **Natural language → SQL** using Claude with Pydantic structured output (`SQLResult`)
- **Full schema context** — the entire DB schema is in the system prompt on every request
- **SQL safety validation** — rejects `DROP`, `DELETE`, `TRUNCATE`, `ALTER`, `INSERT`, `UPDATE`, `CREATE`, `REPLACE`
- **Rich CLI** — syntax-highlighted SQL, color-coded confidence, formatted results table
- **Evaluation harness** — run a batch of test cases and get a pass/fail report
- **Realistic seed data** — 25 customers, 30 products (6 categories), 80 orders, 238 line items

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/sherman94062/nl-to-sql-agent
cd nl-to-sql-agent

# 2. Install
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
#    → edit .env and set ANTHROPIC_API_KEY=sk-ant-...

# 4. Run (seeds the DB automatically on first launch)
python cli.py
```

---

## Usage

### Interactive mode

```bash
python cli.py
```

Type any question at the `>` prompt. Type `exit` or `Ctrl-C` to quit.

### Single question

```bash
python cli.py "Show total revenue by product category"
```

### Evaluation suite

```bash
python run_eval.py
```

Runs 6 built-in test cases and prints a pass/fail summary table.

---

## Example Questions

| Question | SQL pattern |
|---|---|
| List all customers from California | `WHERE state = 'CA'` |
| What are the 5 most expensive products? | `ORDER BY price DESC LIMIT 5` |
| How many orders are in each status? | `GROUP BY status` |
| Total revenue by product category | Multi-table JOIN + `SUM` |
| Products with fewer than 10 units in stock | `HAVING SUM(quantity) < 10` |
| Customers who placed more than 2 orders | `HAVING COUNT(*) > 2` |
| Which products have never been ordered? | `LEFT JOIN … WHERE … IS NULL` |
| Average order value last 30 days | `AVG` + `strftime` date filter |

---

## Project Structure

```
nl-to-sql-agent/
├── agent/
│   └── sql_generator.py   # Claude API call, SQLResult schema, safety validation
├── db/
│   ├── schema.py           # Table definitions, init_db(), get_connection()
│   └── seed.py             # Demo data: customers, products, orders, inventory
├── eval/
│   └── harness.py          # EvalCase / EvalResult dataclasses, run_eval()
├── cli.py                  # Rich interactive + single-shot CLI
├── run_eval.py             # Batch eval runner with summary table
├── .env.example
└── requirements.txt
```

---

## Stack

| Library | Role |
|---|---|
| `anthropic` | Claude API client |
| `pydantic` | Structured output schema (`SQLResult`) |
| `sqlite3` | Built-in query engine — no server needed |
| `sqlparse` | SQL pretty-printing |
| `rich` | Terminal UI (panels, tables, syntax highlighting) |
| `python-dotenv` | `.env` loading |

---

## How It Works

1. `cli.py` takes your question and calls `generate_sql(question)` in `agent/sql_generator.py`.
2. `generate_sql` calls `client.messages.parse()` with the full DB schema in the system prompt and `output_format=SQLResult`.
3. Claude returns a validated `SQLResult(sql, explanation, confidence)` — no regex, no string parsing.
4. The SQL is checked against a safety blocklist, then formatted with `sqlparse`.
5. `cli.py` executes the SQL against the local SQLite DB and renders the results with Rich.

For a deeper walkthrough see [WALKTHROUGH.md](WALKTHROUGH.md).

---

## Model Note

`claude-sonnet-4-20250514` does not support the structured outputs API. This project uses `claude-sonnet-4-6`, the current Sonnet generation, which is a drop-in upgrade and fully supports `client.messages.parse()`.

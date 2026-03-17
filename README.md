# NL-to-SQL Agent

A natural language to SQL agent with an evaluation harness, powered by Claude and Pydantic structured outputs.

## What It Does

Ask questions in plain English about an e-commerce database and get back:
- A generated SQLite `SELECT` query (formatted with `sqlparse`)
- A plain-English explanation of what the query does
- A confidence score (0–100%)
- The actual query results displayed in a Rich table

## Project Structure

```
nl-to-sql-agent/
├── agent/
│   └── sql_generator.py   # Claude-powered SQL generation with Pydantic structured output
├── db/
│   ├── schema.py           # SQLite schema creation and connection helper
│   └── seed.py             # Realistic e-commerce seed data (25 customers, 30 products, 80 orders)
├── eval/
│   └── harness.py          # Evaluation harness with test cases and pass/fail logic
├── cli.py                  # Interactive Rich CLI
├── run_eval.py             # Batch evaluation runner with summary table
├── .env.example            # Environment variable template
└── requirements.txt
```

## Setup

**1. Clone and install dependencies**

```bash
git clone <repo>
cd nl-to-sql-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

**2. Configure your API key**

```bash
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY=sk-ant-...
```

**3. Seed the database** *(auto-runs on first CLI/eval launch)*

```bash
python -m db.seed
```

## Usage

### Interactive CLI

```bash
python cli.py
```

```
> What are the top 5 best-selling products?
> How much revenue came from California customers last month?
> Which customers haven't placed an order yet?
> exit
```

### Single question (non-interactive)

```bash
python cli.py "Show me all orders placed in the last 30 days"
```

### Run the evaluation suite

```bash
python run_eval.py
```

## Example Queries

| Question | What it tests |
|---|---|
| `List all customers from California` | Basic filtering |
| `What are the 5 most expensive products?` | ORDER BY + LIMIT |
| `How many orders are in each status?` | GROUP BY aggregation |
| `What is the total revenue by product category?` | Multi-table JOIN + aggregation |
| `Which products have fewer than 10 units in stock?` | Inventory aggregation with HAVING |
| `Show customers who placed more than 2 orders` | Subquery / HAVING |
| `What was the average order value last month?` | Date filtering + aggregation |
| `Which products have never been ordered?` | LEFT JOIN / NOT IN |

## Safety

The agent rejects any query that contains `DROP`, `DELETE`, `TRUNCATE`, `ALTER`, `INSERT`, `UPDATE`, `CREATE`, or `REPLACE`. Only `SELECT` queries are executed.

## Stack

| Library | Purpose |
|---|---|
| `anthropic` | Claude API client |
| `pydantic` | Structured output schema (`SQLResult`) |
| `sqlite3` | Built-in database engine |
| `sqlparse` | SQL formatting |
| `rich` | CLI output (tables, panels, syntax highlighting) |
| `python-dotenv` | Environment variable loading |

## Model

Uses `claude-sonnet-4-6` with Pydantic-validated structured output via `client.messages.parse()`.
(`claude-sonnet-4-20250514` does not support the structured outputs API; `claude-sonnet-4-6` is the current Sonnet generation and is a drop-in replacement.)
The full database schema is included in the system prompt so the model has complete context for every query.

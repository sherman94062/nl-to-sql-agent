"""Database connection and schema introspection — supports SQLite and PostgreSQL."""

import os
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

try:
    import psycopg2
    import psycopg2.extras
    _HAS_PSYCOPG2 = True
except ImportError:
    _HAS_PSYCOPG2 = False

_DEFAULT_DB_PATH = Path(__file__).parent / "ecommerce.db"


# ---------------------------------------------------------------------------
# Engine detection
# ---------------------------------------------------------------------------

def get_db_path() -> Path:
    return Path(os.environ.get("DB_PATH", str(_DEFAULT_DB_PATH)))


def _database_url() -> str | None:
    return os.environ.get("DATABASE_URL")


def get_engine() -> str:
    """Return 'postgresql' or 'sqlite'."""
    url = _database_url()
    if url and (url.startswith("postgres://") or url.startswith("postgresql://")):
        return "postgresql"
    return "sqlite"


def get_display_name() -> str:
    """Human-readable label shown in the CLI header."""
    if get_engine() == "postgresql":
        parsed = urlparse(_database_url())
        host = parsed.hostname or "localhost"
        port = parsed.port or 5432
        dbname = (parsed.path or "/").lstrip("/") or "(default)"
        user = f"{parsed.username}@" if parsed.username else ""
        return f"PostgreSQL · {user}{host}:{port}/{dbname}"
    return f"SQLite · {get_db_path()}"


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------

def get_connection(db_path: Path | None = None):
    """Return a DB-API 2.0 connection.

    When db_path is provided the result is always a SQLite connection (used by
    the seed script which targets the demo database regardless of DATABASE_URL).
    """
    if db_path is not None:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    if get_engine() == "postgresql":
        if not _HAS_PSYCOPG2:
            raise RuntimeError(
                "psycopg2 is not installed.\n"
                "Run: pip install psycopg2-binary"
            )
        conn = psycopg2.connect(_database_url())
        conn.autocommit = True
        return conn

    conn = sqlite3.connect(str(get_db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def execute_query(sql: str) -> list[dict]:
    """Execute a SQL query against the configured database and return rows as dicts."""
    engine = get_engine()
    conn = get_connection()
    try:
        if engine == "postgresql":
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql)
                return [dict(r) for r in cur.fetchall()]
        else:
            rows = conn.execute(sql).fetchall()
            return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema introspection
# ---------------------------------------------------------------------------

def get_schema_description() -> str:
    """Introspect the connected database and return a schema string for the prompt."""
    if get_engine() == "postgresql":
        return _postgresql_schema()
    return _sqlite_schema()


def _sqlite_schema() -> str:
    path = get_db_path()
    conn = sqlite3.connect(str(path))
    try:
        tables = [
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
        lines = [f"Database: SQLite  |  {path}\n"]
        for table in tables:
            cols = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
            fks = conn.execute(f"PRAGMA foreign_key_list('{table}')").fetchall()
            fk_map = {fk[3]: (fk[2], fk[4]) for fk in fks}  # col → (ref_table, ref_col)

            lines.append(f"Table: {table}")
            for col in cols:
                _cid, name, ctype, notnull, dflt, pk = col
                parts = [f"  - {name:<22} {ctype or 'TEXT'}"]
                if pk:
                    parts.append("PRIMARY KEY")
                elif notnull:
                    parts.append("NOT NULL")
                if dflt is not None:
                    parts.append(f"DEFAULT {dflt}")
                if name in fk_map:
                    ref_table, ref_col = fk_map[name]
                    parts.append(f"→ {ref_table}.{ref_col}")
                lines.append(" ".join(parts))
            lines.append("")
        return "\n".join(lines)
    finally:
        conn.close()


def _postgresql_schema() -> str:
    if not _HAS_PSYCOPG2:
        raise RuntimeError("psycopg2 is not installed. Run: pip install psycopg2-binary")

    conn = psycopg2.connect(_database_url())
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """)
            tables = [r["table_name"] for r in cur.fetchall()]

            cur.execute("""
                SELECT table_name, column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = 'public'
                ORDER BY table_name, ordinal_position
            """)
            cols_by_table: dict[str, list] = {}
            for row in cur.fetchall():
                cols_by_table.setdefault(row["table_name"], []).append(row)

            cur.execute("""
                SELECT kcu.table_name, kcu.column_name,
                       ccu.table_name  AS foreign_table,
                       ccu.column_name AS foreign_column
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema    = kcu.table_schema
                JOIN information_schema.constraint_column_usage AS ccu
                  ON ccu.constraint_name = tc.constraint_name
                 AND ccu.table_schema    = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema    = 'public'
            """)
            fks: dict[str, dict[str, tuple]] = {}
            for row in cur.fetchall():
                fks.setdefault(row["table_name"], {})[row["column_name"]] = (
                    row["foreign_table"], row["foreign_column"]
                )

        parsed = urlparse(_database_url())
        label = f"PostgreSQL  |  {parsed.hostname}:{parsed.port or 5432}{parsed.path}"
        lines = [f"Database: {label}\n"]

        for table in tables:
            lines.append(f"Table: {table}")
            for col in cols_by_table.get(table, []):
                name = col["column_name"]
                dtype = col["data_type"]
                nullable = col["is_nullable"] == "YES"
                dflt = col["column_default"]

                parts = [f"  - {name:<30} {dtype}"]
                if not nullable:
                    parts.append("NOT NULL")
                if dflt is not None:
                    parts.append(f"DEFAULT {dflt}")
                if table in fks and name in fks[table]:
                    ref_t, ref_c = fks[table][name]
                    parts.append(f"→ {ref_t}.{ref_c}")
                lines.append(" ".join(parts))
            lines.append("")

        return "\n".join(lines)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# SQLite demo database setup (used by db/seed.py only)
# ---------------------------------------------------------------------------

_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS customers (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    email      TEXT    UNIQUE NOT NULL,
    phone      TEXT,
    address    TEXT,
    city       TEXT,
    state      TEXT,
    country    TEXT    NOT NULL DEFAULT 'US',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT,
    category    TEXT NOT NULL,
    price       REAL NOT NULL CHECK(price >= 0),
    sku         TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS inventory (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity   INTEGER NOT NULL DEFAULT 0 CHECK(quantity >= 0),
    warehouse  TEXT    NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS orders (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id  INTEGER NOT NULL REFERENCES customers(id),
    status       TEXT    NOT NULL DEFAULT 'pending'
                         CHECK(status IN ('pending','processing','shipped','delivered','cancelled')),
    total_amount REAL    NOT NULL CHECK(total_amount >= 0),
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    shipped_at   TIMESTAMP
);

CREATE TABLE IF NOT EXISTS order_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity   INTEGER NOT NULL CHECK(quantity > 0),
    unit_price REAL    NOT NULL CHECK(unit_price >= 0)
);

CREATE INDEX IF NOT EXISTS idx_orders_customer_id   ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_status        ON orders(status);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_inventory_product_id ON inventory(product_id);
"""


def init_db(db_path: Path | None = None) -> Path:
    """Create all tables in the SQLite demo database (idempotent, SQLite-only)."""
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(_CREATE_TABLES_SQL)
        conn.commit()
    finally:
        conn.close()
    return path

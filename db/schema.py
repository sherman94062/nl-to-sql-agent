"""Database schema initialization for the e-commerce SQLite database."""

import os
import sqlite3
from pathlib import Path

_DEFAULT_DB_PATH = Path(__file__).parent / "ecommerce.db"


def get_db_path() -> Path:
    return Path(os.environ.get("DB_PATH", str(_DEFAULT_DB_PATH)))


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Return a sqlite3 connection with row_factory set to sqlite3.Row."""
    path = db_path or get_db_path()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


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
    """Create all tables (idempotent). Returns the db path."""
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with get_connection(path) as conn:
        conn.executescript(_CREATE_TABLES_SQL)
    return path

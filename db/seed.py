"""Seed the e-commerce database with realistic demo data."""

import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from db.schema import get_connection, init_db

random.seed(42)

# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

CUSTOMERS = [
    ("Alice Johnson",   "alice@example.com",   "555-0101", "123 Maple St",   "Portland",      "OR"),
    ("Bob Smith",       "bob@example.com",      "555-0102", "456 Oak Ave",    "Seattle",       "WA"),
    ("Carol White",     "carol@example.com",    "555-0103", "789 Pine Rd",    "San Francisco", "CA"),
    ("David Brown",     "david@example.com",    "555-0104", "321 Elm St",     "Austin",        "TX"),
    ("Eva Martinez",    "eva@example.com",       "555-0105", "654 Cedar Blvd", "Miami",         "FL"),
    ("Frank Lee",       "frank@example.com",    "555-0106", "987 Birch Ln",   "Chicago",       "IL"),
    ("Grace Kim",       "grace@example.com",    "555-0107", "111 Spruce Ave", "New York",      "NY"),
    ("Henry Davis",     "henry@example.com",    "555-0108", "222 Willow Dr",  "Denver",        "CO"),
    ("Irene Wilson",    "irene@example.com",    "555-0109", "333 Aspen Ct",   "Phoenix",       "AZ"),
    ("Jack Thompson",   "jack@example.com",     "555-0110", "444 Fir St",     "Boston",        "MA"),
    ("Karen Anderson",  "karen@example.com",    "555-0111", "555 Poplar Pl",  "Atlanta",       "GA"),
    ("Liam Garcia",     "liam@example.com",     "555-0112", "666 Chestnut Rd","Dallas",        "TX"),
    ("Mia Rodriguez",   "mia@example.com",      "555-0113", "777 Walnut Ave", "Los Angeles",   "CA"),
    ("Noah Harris",     "noah@example.com",     "555-0114", "888 Hickory Blvd","Nashville",    "TN"),
    ("Olivia Clark",    "olivia@example.com",   "555-0115", "999 Magnolia Dr","Charlotte",     "NC"),
    ("Paul Lewis",      "paul@example.com",     "555-0116", "101 Dogwood Ct", "Minneapolis",   "MN"),
    ("Quinn Walker",    "quinn@example.com",    "555-0117", "202 Cypress Ln", "Sacramento",    "CA"),
    ("Rachel Hall",     "rachel@example.com",   "555-0118", "303 Redwood Dr", "Salt Lake City","UT"),
    ("Sam Allen",       "sam@example.com",      "555-0119", "404 Sequoia Ave","Portland",      "OR"),
    ("Tina Young",      "tina@example.com",     "555-0120", "505 Bamboo Blvd","Las Vegas",     "NV"),
    ("Ursula King",     "ursula@example.com",   "555-0121", "606 Sycamore St","Raleigh",       "NC"),
    ("Victor Scott",    "victor@example.com",   "555-0122", "707 Mulberry Rd","Philadelphia",  "PA"),
    ("Wendy Adams",     "wendy@example.com",    "555-0123", "808 Hawthorn Ln","Kansas City",   "MO"),
    ("Xander Baker",    "xander@example.com",   "555-0124", "909 Linden Ave", "St. Louis",     "MO"),
    ("Yara Gonzalez",   "yara@example.com",     "555-0125", "1010 Jasmine Ct","San Diego",     "CA"),
]

# (name, description, category, price, sku)
PRODUCTS = [
    # Electronics
    ("Wireless Headphones",   "Noise-cancelling Bluetooth headphones",          "Electronics",  89.99, "ELEC-001"),
    ("USB-C Hub",             "7-in-1 USB-C hub with HDMI and card reader",     "Electronics",  34.99, "ELEC-002"),
    ("Mechanical Keyboard",   "Tenkeyless mechanical keyboard, Cherry MX Red",  "Electronics", 119.99, "ELEC-003"),
    ("Webcam 1080p",          "Full HD webcam with built-in microphone",         "Electronics",  59.99, "ELEC-004"),
    ("LED Desk Lamp",         "Adjustable color temperature LED desk lamp",      "Electronics",  44.99, "ELEC-005"),
    ("Portable Charger",      "20,000mAh power bank with fast charging",        "Electronics",  49.99, "ELEC-006"),
    ("Wireless Mouse",        "Ergonomic silent wireless mouse",                 "Electronics",  29.99, "ELEC-007"),
    ("Monitor Stand",         "Adjustable aluminum monitor stand with storage",  "Electronics",  39.99, "ELEC-008"),
    # Books
    ("Clean Code",            "A Handbook of Agile Software Craftsmanship",      "Books",        35.99, "BOOK-001"),
    ("Designing Data Systems","Principles behind reliable, scalable systems",    "Books",        49.99, "BOOK-002"),
    ("The Pragmatic Programmer","Your journey to mastery",                       "Books",        39.99, "BOOK-003"),
    ("Python Crash Course",   "A hands-on, project-based intro to Python",      "Books",        29.99, "BOOK-004"),
    ("Atomic Habits",         "Tiny changes, remarkable results",                "Books",        18.99, "BOOK-005"),
    ("Deep Work",             "Rules for focused success in a distracted world", "Books",        16.99, "BOOK-006"),
    # Office Supplies
    ("Standing Desk Mat",     "Anti-fatigue standing desk mat, 3/4 inch",       "Office",       45.99, "OFFC-001"),
    ("Whiteboard A3",         "Dry-erase whiteboard for desk use",               "Office",       19.99, "OFFC-002"),
    ("Sticky Notes Pack",     "Assorted color sticky notes, 12 pads",            "Office",        9.99, "OFFC-003"),
    ("Desk Organizer",        "Bamboo 5-compartment desk organizer",             "Office",       22.99, "OFFC-004"),
    ("Cable Management Kit",  "Velcro cable ties and clips bundle",              "Office",       14.99, "OFFC-005"),
    ("Ergonomic Wrist Rest",  "Memory foam wrist rest for keyboard",             "Office",       17.99, "OFFC-006"),
    # Clothing
    ("Tech Hoodie",           "Soft fleece hoodie with kangaroo pocket",         "Clothing",     54.99, "CLTH-001"),
    ("Dev T-Shirt",           "100% cotton programmer humor tee",                "Clothing",     24.99, "CLTH-002"),
    ("Laptop Backpack",       "Water-resistant 15\" laptop backpack",           "Bags",         69.99, "BAGS-001"),
    ("Tote Bag",              "Canvas tote bag with interior pocket",            "Bags",         19.99, "BAGS-002"),
    # Health & Fitness
    ("Blue Light Glasses",    "Anti-blue light glasses for screen use",          "Health",       29.99, "HLTH-001"),
    ("Desk Exercise Bike",    "Under-desk pedal exerciser with display",         "Health",       89.99, "HLTH-002"),
    ("Posture Corrector",     "Adjustable back brace for posture support",       "Health",       34.99, "HLTH-003"),
    ("Noise-Cancel Earplugs", "High-fidelity silicone ear protection",           "Health",       12.99, "HLTH-004"),
    # Food & Drink
    ("Insulated Water Bottle","32oz stainless steel insulated water bottle",    "Kitchen",      27.99, "KTCH-001"),
    ("Pour-Over Coffee Kit",  "Glass pour-over dripper with filters",            "Kitchen",      32.99, "KTCH-002"),
]

WAREHOUSES = ["East", "West", "Central"]
ORDER_STATUSES = ["pending", "processing", "shipped", "delivered", "cancelled"]
STATUS_WEIGHTS = [0.05, 0.10, 0.20, 0.55, 0.10]


def _random_date(start_days_ago: int, end_days_ago: int = 0) -> str:
    delta = random.randint(end_days_ago, start_days_ago)
    dt = datetime.now() - timedelta(days=delta)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def seed_db(db_path: Path | None = None, force: bool = False) -> None:
    """Populate the database with demo data.

    Args:
        db_path: Override default DB path.
        force: If True, clear existing data before seeding.
    """
    path = init_db(db_path)
    conn = get_connection(path)

    with conn:
        if force:
            conn.executescript("""
                DELETE FROM order_items;
                DELETE FROM orders;
                DELETE FROM inventory;
                DELETE FROM products;
                DELETE FROM customers;
            """)

        # Skip if already seeded
        existing = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        if existing > 0 and not force:
            return

        # --- Customers ---
        conn.executemany(
            "INSERT OR IGNORE INTO customers (name,email,phone,address,city,state,country) "
            "VALUES (?,?,?,?,?,?,'US')",
            CUSTOMERS,
        )

        # --- Products ---
        conn.executemany(
            "INSERT OR IGNORE INTO products (name,description,category,price,sku) VALUES (?,?,?,?,?)",
            PRODUCTS,
        )

        # --- Inventory (1–3 warehouse entries per product) ---
        product_ids = [r[0] for r in conn.execute("SELECT id FROM products").fetchall()]
        inventory_rows = []
        for pid in product_ids:
            warehouses = random.sample(WAREHOUSES, k=random.randint(1, 3))
            for wh in warehouses:
                qty = random.randint(0, 200)
                inventory_rows.append((pid, qty, wh))
        conn.executemany(
            "INSERT INTO inventory (product_id,quantity,warehouse) VALUES (?,?,?)",
            inventory_rows,
        )

        # --- Orders + order_items ---
        customer_ids = [r[0] for r in conn.execute("SELECT id FROM customers").fetchall()]

        for _ in range(80):
            cust_id = random.choice(customer_ids)
            status = random.choices(ORDER_STATUSES, weights=STATUS_WEIGHTS)[0]
            created = _random_date(365)
            shipped = None
            if status in ("shipped", "delivered"):
                shipped = _random_date(30, 1)

            # Pick 1–5 products for this order
            items = random.sample(product_ids, k=random.randint(1, 5))
            total = 0.0
            item_rows = []
            for pid in items:
                price = conn.execute("SELECT price FROM products WHERE id=?", (pid,)).fetchone()[0]
                qty = random.randint(1, 4)
                total += price * qty
                item_rows.append((pid, qty, price))

            cur = conn.execute(
                "INSERT INTO orders (customer_id,status,total_amount,created_at,shipped_at) "
                "VALUES (?,?,?,?,?)",
                (cust_id, status, round(total, 2), created, shipped),
            )
            order_id = cur.lastrowid
            conn.executemany(
                "INSERT INTO order_items (order_id,product_id,quantity,unit_price) VALUES (?,?,?,?)",
                [(order_id, pid, qty, price) for pid, qty, price in item_rows],
            )

    conn.close()
    print(f"Database seeded at: {path}")


if __name__ == "__main__":
    seed_db(force=True)

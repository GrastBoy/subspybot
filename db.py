import os
import sys
import sqlite3
import logging
import atexit
import signal
from typing import Iterable

# ================== Configuration ==================

# Prefer environment variables for secrets.
BOT_TOKEN = os.getenv("BOT_TOKEN", "8303921633:AAFu3nvim6qggmkIq2ghg5EMrT-8RhjoP50")
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", "-4930176305"))

# Support multiple admins via env "ADMIN_IDS"="123,456"; fallback to single ADMIN_ID
_admin_ids_env = os.getenv("ADMIN_IDS")
if _admin_ids_env:
    ADMIN_IDS = {int(x.strip()) for x in _admin_ids_env.split(",") if x.strip().isdigit()}
else:
    ADMIN_IDS = {int(os.getenv("ADMIN_ID", "7797088374"))}

# Backward compatibility alias for legacy imports: from db import ADMIN_ID
# Pick a deterministic single admin (smallest) from the set
ADMIN_ID = min(ADMIN_IDS) if ADMIN_IDS else None

LOCK_FILE = os.getenv("LOCK_FILE", "bot.lock")
DB_FILE = os.getenv("DB_FILE", "orders.db")

# ================== Logging ==================

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================== Lock file (single instance guard) ==================

def _cleanup_lock():
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
            logger.info("Lock file removed: %s", LOCK_FILE)
    except Exception as e:
        logger.warning("Failed to remove lock file: %s", e)

def _signal_handler(signum, frame):
    logger.info("Received signal %s; cleaning up and exiting.", signum)
    _cleanup_lock()
    try:
        conn.close()
    except Exception:
        pass
    sys.exit(0)

# Abort if another instance appears running
if os.path.exists(LOCK_FILE):
    print("⚠️ bot.lock виявлено — ймовірно бот вже запущений. Завершую роботу.")
    sys.exit(1)
# Create lock and ensure cleanup on exit/signals
open(LOCK_FILE, "w").close()
atexit.register(_cleanup_lock)
for sig in (signal.SIGINT, signal.SIGTERM):
    try:
        signal.signal(sig, _signal_handler)
    except Exception:
        pass

# ================== Database connection ==================

conn = sqlite3.connect(DB_FILE, check_same_thread=False)
conn.execute("PRAGMA foreign_keys = ON")
conn.execute("PRAGMA journal_mode = WAL")
conn.execute("PRAGMA synchronous = NORMAL")
conn.execute("PRAGMA busy_timeout = 5000")
cursor = conn.cursor()

# ================== Schema ==================

def _executescript(script: str):
    cursor.executescript(script)
    conn.commit()

def _ensure_columns(table: str, required_cols: Iterable[str], add_stmts: dict):
    cursor.execute(f"PRAGMA table_info('{table}')")
    existing = {row[1] for row in cursor.fetchall()}
    for col in required_cols:
        if col not in existing:
            stmt = add_stmts.get(col)
            if stmt:
                try:
                    cursor.execute(stmt)
                    conn.commit()
                    logger.info("Added column %s to %s", col, table)
                except Exception as e:
                    logger.warning("Failed adding column %s to %s: %s", col, table, e)

def _ensure_indexes():
    try:
        cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_order_photos_unique
        ON order_photos(order_id, stage, file_unique_id)
        """)
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS ix_order_photos_active
        ON order_photos(order_id, stage, active)
        """)
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS ix_order_photos_order_stage
        ON order_photos(order_id, stage)
        """)
        conn.commit()
    except Exception as e:
        logger.warning("Index creation warning: %s", e)

def ensure_schema():
    # orders
    _executescript("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        bank TEXT,
        action TEXT,
        stage INTEGER DEFAULT 0,
        status TEXT,
        group_id INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # order_photos
    _executescript("""
    CREATE TABLE IF NOT EXISTS order_photos (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      order_id INTEGER NOT NULL,
      stage INTEGER NOT NULL,
      file_id TEXT NOT NULL,
      file_unique_id TEXT NOT NULL,
      confirmed INTEGER NOT NULL DEFAULT 0 CHECK (confirmed IN (-1,0,1)),
      active INTEGER NOT NULL DEFAULT 1,
      reason TEXT,
      replace_of INTEGER,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
    );
    """)

    # Migrations for existing DBs
    _ensure_columns(
        "order_photos",
        required_cols=[
            "file_unique_id", "active", "reason", "replace_of", "created_at"
        ],
        add_stmts={
            "file_unique_id": "ALTER TABLE order_photos ADD COLUMN file_unique_id TEXT",
            "active": "ALTER TABLE order_photos ADD COLUMN active INTEGER NOT NULL DEFAULT 1",
            "reason": "ALTER TABLE order_photos ADD COLUMN reason TEXT",
            "replace_of": "ALTER TABLE order_photos ADD COLUMN replace_of INTEGER",
            "created_at": "ALTER TABLE order_photos ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP",
        }
    )

    _ensure_indexes()

    # cooperation_requests
    _executescript("""
    CREATE TABLE IF NOT EXISTS cooperation_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        text TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # manager_groups
    _executescript("""
    CREATE TABLE IF NOT EXISTS manager_groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER UNIQUE,
        name TEXT,
        busy INTEGER DEFAULT 0
    );
    """)

    # queue
    _executescript("""
    CREATE TABLE IF NOT EXISTS queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        bank TEXT,
        action TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

ensure_schema()

# ================== Utilities ==================

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def get_db():
    return conn, cursor

def close_db():
    try:
        conn.close()
    except Exception:
        pass
    _cleanup_lock()

# ================== Sanity logs ==================

logger.info("Database initialized at %s", os.path.abspath(DB_FILE))
logger.info(
    "Foreign keys: ON | WAL mode enabled | Admin group: %s | Admin IDs: %s",
    ADMIN_GROUP_ID, sorted(ADMIN_IDS)
)
if not BOT_TOKEN or BOT_TOKEN.strip() == "":
    logger.error("BOT_TOKEN is not set. Please set the BOT_TOKEN environment variable.")
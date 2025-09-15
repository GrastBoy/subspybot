import os
import sys
import sqlite3
import logging
import atexit
import signal
from typing import Iterable, Optional, List, Tuple

BOT_TOKEN = os.getenv("BOT_TOKEN", "8303921633:AAFu3nvim6qggmkIq2ghg5EMrT-8RhjoP50")
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", "-4930176305"))

_admin_ids_env = os.getenv("ADMIN_IDS")
if _admin_ids_env:
    ADMIN_IDS = {int(x.strip()) for x in _admin_ids_env.split(",") if x.strip().isdigit()}
else:
    ADMIN_IDS = {int(os.getenv("ADMIN_ID", "7797088374"))}
ADMIN_ID = min(ADMIN_IDS) if ADMIN_IDS else None

LOCK_FILE = os.getenv("LOCK_FILE", "bot.lock")
DB_FILE = os.getenv("DB_FILE", "orders.db")

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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

if os.path.exists(LOCK_FILE):
    print("⚠️ bot.lock виявлено — ймовірно бот вже запущений. Завершую роботу.")
    sys.exit(1)
open(LOCK_FILE, "w").close()
atexit.register(_cleanup_lock)
for sig in (signal.SIGINT, signal.SIGTERM):
    try:
        signal.signal(sig, _signal_handler)
    except Exception:
        pass

conn = sqlite3.connect(DB_FILE, check_same_thread=False)
conn.execute("PRAGMA foreign_keys = ON")
conn.execute("PRAGMA journal_mode = WAL")
conn.execute("PRAGMA synchronous = NORMAL")
conn.execute("PRAGMA busy_timeout = 5000")
cursor = conn.cursor()

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
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS ix_actions_order_created
        ON order_actions_log(order_id, created_at)
        """)
        conn.commit()
    except Exception as e:
        logger.warning("Index creation warning: %s", e)

def ensure_schema():
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
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        -- Stage2 meta (may be NULL on older rows; added via migrations)
        phone_number TEXT,
        email TEXT,
        phone_verified INTEGER DEFAULT 0,
        email_verified INTEGER DEFAULT 0,
        phone_code_status TEXT DEFAULT 'none',
        phone_code_session INTEGER DEFAULT 0,
        phone_code_last_sent_at DATETIME,
        phone_code_attempts INTEGER DEFAULT 0,
        stage2_status TEXT DEFAULT 'idle',
        stage2_restart_count INTEGER DEFAULT 0,
        stage2_complete INTEGER DEFAULT 0
    );
    """)
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
    # action log
    _executescript("""
    CREATE TABLE IF NOT EXISTS order_actions_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        actor TEXT NOT NULL,
        action_type TEXT NOT NULL,
        payload TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
    );
    """)
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
        busy INTEGER DEFAULT 0,
        bank TEXT,
        is_admin_group INTEGER DEFAULT 0
    );
    """)
    # group_active_orders - tracks multiple active orders per group
    _executescript("""
    CREATE TABLE IF NOT EXISTS group_active_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL,
        order_id INTEGER NOT NULL,
        is_current INTEGER DEFAULT 0,
        assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE,
        FOREIGN KEY(group_id) REFERENCES manager_groups(group_id) ON DELETE CASCADE,
        UNIQUE(group_id, order_id)
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
    # Migrations (ensure missing columns if old DB)
    _ensure_columns("orders",
        [
            "phone_number","email","phone_verified","email_verified","phone_code_status","phone_code_session",
            "phone_code_last_sent_at","phone_code_attempts","stage2_status","stage2_restart_count","stage2_complete"
        ],
        {
            "phone_number": "ALTER TABLE orders ADD COLUMN phone_number TEXT",
            "email": "ALTER TABLE orders ADD COLUMN email TEXT",
            "phone_verified": "ALTER TABLE orders ADD COLUMN phone_verified INTEGER DEFAULT 0",
            "email_verified": "ALTER TABLE orders ADD COLUMN email_verified INTEGER DEFAULT 0",
            "phone_code_status": "ALTER TABLE orders ADD COLUMN phone_code_status TEXT DEFAULT 'none'",
            "phone_code_session": "ALTER TABLE orders ADD COLUMN phone_code_session INTEGER DEFAULT 0",
            "phone_code_last_sent_at": "ALTER TABLE orders ADD COLUMN phone_code_last_sent_at DATETIME",
            "phone_code_attempts": "ALTER TABLE orders ADD COLUMN phone_code_attempts INTEGER DEFAULT 0",
            "stage2_status": "ALTER TABLE orders ADD COLUMN stage2_status TEXT DEFAULT 'idle'",
            "stage2_restart_count": "ALTER TABLE orders ADD COLUMN stage2_restart_count INTEGER DEFAULT 0",
            "stage2_complete": "ALTER TABLE orders ADD COLUMN stage2_complete INTEGER DEFAULT 0"
        }
    )
    # Ensure new columns for manager_groups
    _ensure_columns("manager_groups",
        ["bank", "is_admin_group"],
        {
            "bank": "ALTER TABLE manager_groups ADD COLUMN bank TEXT",
            "is_admin_group": "ALTER TABLE manager_groups ADD COLUMN is_admin_group INTEGER DEFAULT 0"
        }
    )
    _ensure_indexes()

ensure_schema()

def log_action(order_id: int, actor: str, action_type: str, payload: str = None):
    try:
        cursor.execute("INSERT INTO order_actions_log (order_id, actor, action_type, payload) VALUES (?,?,?,?)",
                       (order_id, actor, action_type, payload))
        conn.commit()
    except Exception as e:
        logger.warning("log_action failed: %s", e)

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

# ================ Bank Group Management Helpers ================

def get_bank_group(bank: str) -> Optional[int]:
    """Get the group_id assigned to handle orders for a specific bank"""
    cursor.execute("SELECT group_id FROM manager_groups WHERE bank=? AND is_admin_group=0 LIMIT 1", (bank,))
    row = cursor.fetchone()
    return row[0] if row else None

def get_admin_groups() -> List[int]:
    """Get all admin groups that can see orders from all banks"""
    cursor.execute("SELECT group_id FROM manager_groups WHERE is_admin_group=1")
    return [row[0] for row in cursor.fetchall()]

def add_active_order_to_group(group_id: int, order_id: int, set_as_current: bool = True) -> bool:
    """Add an order to group's active orders list"""
    try:
        # Reset current flag if setting as current
        if set_as_current:
            cursor.execute("UPDATE group_active_orders SET is_current=0 WHERE group_id=?", (group_id,))
        
        cursor.execute("""
            INSERT OR IGNORE INTO group_active_orders (group_id, order_id, is_current) 
            VALUES (?, ?, ?)
        """, (group_id, order_id, 1 if set_as_current else 0))
        conn.commit()
        return True
    except Exception as e:
        logger.warning("Failed to add active order to group: %s", e)
        return False

def remove_active_order_from_group(group_id: int, order_id: int) -> bool:
    """Remove an order from group's active orders list"""
    try:
        cursor.execute("DELETE FROM group_active_orders WHERE group_id=? AND order_id=?", (group_id, order_id))
        conn.commit()
        return True
    except Exception as e:
        logger.warning("Failed to remove active order from group: %s", e)
        return False

def get_group_active_orders(group_id: int) -> List[Tuple[int, bool]]:
    """Get all active orders for a group, returns list of (order_id, is_current)"""
    cursor.execute("""
        SELECT order_id, is_current FROM group_active_orders 
        WHERE group_id=? ORDER BY is_current DESC, assigned_at ASC
    """, (group_id,))
    return cursor.fetchall()

def get_current_order_for_group(group_id: int) -> Optional[int]:
    """Get the current active order for a group"""
    cursor.execute("SELECT order_id FROM group_active_orders WHERE group_id=? AND is_current=1", (group_id,))
    row = cursor.fetchone()
    return row[0] if row else None

def set_current_order_for_group(group_id: int, order_id: int) -> bool:
    """Set an order as the current one for a group"""
    try:
        # Reset all current flags for this group
        cursor.execute("UPDATE group_active_orders SET is_current=0 WHERE group_id=?", (group_id,))
        # Set the specified order as current
        cursor.execute("UPDATE group_active_orders SET is_current=1 WHERE group_id=? AND order_id=?", (group_id, order_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.warning("Failed to set current order for group: %s", e)
        return False

logger.info("Database initialized at %s", os.path.abspath(DB_FILE))
logger.info(
    "Foreign keys: ON | WAL mode enabled | Admin group: %s | Admin IDs: %s",
    ADMIN_GROUP_ID, sorted(ADMIN_IDS)
)
if not BOT_TOKEN or BOT_TOKEN.strip() == "":
    logger.error("BOT_TOKEN is not set. Please set the BOT_TOKEN environment variable.")
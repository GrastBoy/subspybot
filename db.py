import atexit
import logging
import os
import signal
import sqlite3
import sys
from typing import Iterable

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", "0"))

_admin_ids_env = os.getenv("ADMIN_IDS")
if _admin_ids_env:
    ADMIN_IDS = {int(x.strip()) for x in _admin_ids_env.split(",") if x.strip().isdigit()}
else:
    ADMIN_IDS = set()  # No default admin IDs for security
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
        # New indexes for enhanced functionality
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS ix_bank_data_usage_bank_phone
        ON bank_data_usage(bank, phone_number)
        """)
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS ix_bank_data_usage_bank_email
        ON bank_data_usage(bank, email)
        """)
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS ix_manager_active_orders_group
        ON manager_active_orders(group_id, is_primary)
        """)
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS ix_manager_groups_bank
        ON manager_groups(bank, is_admin_group)
        """)
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS ix_bank_instructions_bank_action
        ON bank_instructions(bank_name, action, step_number)
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
    # manager_groups - extended to support bank-specific groups
    _executescript("""
    CREATE TABLE IF NOT EXISTS manager_groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER UNIQUE,
        name TEXT,
        busy INTEGER DEFAULT 0,
        bank TEXT,  -- NULL for admin groups, specific bank name for bank groups
        is_admin_group INTEGER DEFAULT 0  -- 1 for admin groups that can see all orders
    );
    """)
    _executescript("""
    CREATE TABLE IF NOT EXISTS bank_visibility (
        bank TEXT PRIMARY KEY,
        show_register INTEGER NOT NULL DEFAULT 1,
        show_change INTEGER NOT NULL DEFAULT 1
    );
    """)
    # bank data uniqueness tracking
    _executescript("""
    CREATE TABLE IF NOT EXISTS bank_data_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bank TEXT NOT NULL,
        phone_number TEXT,
        email TEXT,
        order_id INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
    );
    """)
    # order forms/questionnaires
    _executescript("""
    CREATE TABLE IF NOT EXISTS order_forms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        form_data TEXT,  -- JSON with all form information
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
    );
    """)
    # bank form templates
    _executescript("""
    CREATE TABLE IF NOT EXISTS bank_form_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bank_name TEXT NOT NULL,
        template_data TEXT,  -- JSON with form template fields
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(bank_name) REFERENCES banks(name) ON DELETE CASCADE
    );
    """)
    # active order tracking for managers
    _executescript("""
    CREATE TABLE IF NOT EXISTS manager_active_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL,
        order_id INTEGER NOT NULL,
        is_primary INTEGER DEFAULT 0,  -- 1 for primary active order
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
    );
    """)
    # bank management table
    _executescript("""
    CREATE TABLE IF NOT EXISTS banks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        is_active INTEGER DEFAULT 1,
        register_enabled INTEGER DEFAULT 1,
        change_enabled INTEGER DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)
    # bank instructions table
    _executescript("""
    CREATE TABLE IF NOT EXISTS bank_instructions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bank_name TEXT NOT NULL,
        action TEXT NOT NULL,  -- 'register' or 'change'
        step_number INTEGER NOT NULL,
        instruction_text TEXT,
        instruction_images TEXT,  -- JSON array of image URLs/IDs
        age_requirement INTEGER,
        required_photos INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(bank_name) REFERENCES banks(name) ON DELETE CASCADE
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
                        "phone_number", "email", "phone_verified", "email_verified", "phone_code_status", "phone_code_session",
                        "phone_code_last_sent_at", "phone_code_attempts", "stage2_status", "stage2_restart_count", "stage2_complete"
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
    # Migrations for manager_groups
    _ensure_columns("manager_groups",
                    ["bank", "is_admin_group"],
        {
            "bank": "ALTER TABLE manager_groups ADD COLUMN bank TEXT",
            "is_admin_group": "ALTER TABLE manager_groups ADD COLUMN is_admin_group INTEGER DEFAULT 0"
        }
    )
    # Migrations for banks table
    _ensure_columns("banks",
                    ["price", "description"],
        {
            "price": "ALTER TABLE banks ADD COLUMN price TEXT",
            "description": "ALTER TABLE banks ADD COLUMN description TEXT"
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

# New utility functions for enhanced functionality
def check_data_uniqueness(bank: str, phone_number: str = None, email: str = None) -> tuple:
    """Check if phone/email were used for this bank before. Returns (phone_used, email_used)"""
    phone_used = False
    email_used = False

    if phone_number:
        cursor.execute("SELECT COUNT(*) FROM bank_data_usage WHERE bank=? AND phone_number=?",
                      (bank, phone_number))
        phone_used = cursor.fetchone()[0] > 0

    if email:
        cursor.execute("SELECT COUNT(*) FROM bank_data_usage WHERE bank=? AND email=?",
                      (bank, email))
        email_used = cursor.fetchone()[0] > 0

    return phone_used, email_used

def record_data_usage(order_id: int, bank: str, phone_number: str = None, email: str = None):
    """Record that phone/email were used for this bank in this order"""
    try:
        cursor.execute("INSERT INTO bank_data_usage (order_id, bank, phone_number, email) VALUES (?,?,?,?)",
                      (order_id, bank, phone_number, email))
        conn.commit()
    except Exception as e:
        logger.warning("record_data_usage failed: %s", e)

def add_manager_group(group_id: int, name: str, bank: str = None, is_admin: bool = False) -> bool:
    """Add a new manager group"""
    try:
        cursor.execute("INSERT INTO manager_groups (group_id, name, bank, is_admin_group) VALUES (?,?,?,?)",
                      (group_id, name, bank, 1 if is_admin else 0))
        conn.commit()
        return True
    except Exception as e:
        logger.warning("add_manager_group failed: %s", e)
        return False

def get_bank_groups(bank: str = None):
    """Get manager groups for a specific bank or all groups if bank is None"""
    if bank:
        cursor.execute("SELECT group_id, name FROM manager_groups WHERE bank=? OR is_admin_group=1", (bank,))
    else:
        cursor.execute("SELECT group_id, name, bank, is_admin_group FROM manager_groups")
    return cursor.fetchall()

def set_active_order_for_group(group_id: int, order_id: int, is_primary: bool = True):
    """Set an active order for a manager group"""
    try:
        if is_primary:
            # Clear other primary orders for this group
            cursor.execute("UPDATE manager_active_orders SET is_primary=0 WHERE group_id=?", (group_id,))

        # Check if this order is already active for this group
        cursor.execute("SELECT id FROM manager_active_orders WHERE group_id=? AND order_id=?",
                      (group_id, order_id))
        if cursor.fetchone():
            cursor.execute("UPDATE manager_active_orders SET is_primary=? WHERE group_id=? AND order_id=?",
                          (1 if is_primary else 0, group_id, order_id))
        else:
            cursor.execute("INSERT INTO manager_active_orders (group_id, order_id, is_primary) VALUES (?,?,?)",
                          (group_id, order_id, 1 if is_primary else 0))
        conn.commit()
    except Exception as e:
        logger.warning("set_active_order_for_group failed: %s", e)

def get_active_orders_for_group(group_id: int):
    """Get all active orders for a manager group"""
    cursor.execute("""
        SELECT mao.order_id, mao.is_primary, o.user_id, o.username, o.bank, o.action, o.status
        FROM manager_active_orders mao
        JOIN orders o ON mao.order_id = o.id
        WHERE mao.group_id = ?
        ORDER BY mao.is_primary DESC, mao.created_at DESC
    """, (group_id,))
    return cursor.fetchall()

def create_order_form(order_id: int, form_data: dict):
    """Create order form/questionnaire"""
    import json
    try:
        cursor.execute("INSERT INTO order_forms (order_id, form_data) VALUES (?,?)",
                      (order_id, json.dumps(form_data, ensure_ascii=False)))
        conn.commit()
    except Exception as e:
        logger.warning("create_order_form failed: %s", e)

def add_bank(name: str, register_enabled: bool = True, change_enabled: bool = True, price: str = None, description: str = None) -> bool:
    """Add a new bank"""
    try:
        cursor.execute("INSERT INTO banks (name, register_enabled, change_enabled, price, description) VALUES (?,?,?,?,?)",
                      (name, 1 if register_enabled else 0, 1 if change_enabled else 0, price, description))
        conn.commit()
        return True
    except Exception as e:
        logger.warning("add_bank failed: %s", e)
        return False

def update_bank(name: str, register_enabled: bool = None, change_enabled: bool = None, is_active: bool = None, price: str = None, description: str = None) -> bool:
    """Update bank settings"""
    try:
        updates = []
        params = []
        if register_enabled is not None:
            updates.append("register_enabled=?")
            params.append(1 if register_enabled else 0)
        if change_enabled is not None:
            updates.append("change_enabled=?")
            params.append(1 if change_enabled else 0)
        if is_active is not None:
            updates.append("is_active=?")
            params.append(1 if is_active else 0)
        if price is not None:
            updates.append("price=?")
            params.append(price)
        if description is not None:
            updates.append("description=?")
            params.append(description)

        if updates:
            params.append(name)
            cursor.execute(f"UPDATE banks SET {','.join(updates)} WHERE name=?", params)
            conn.commit()
            return True
        return False
    except Exception as e:
        logger.warning("update_bank failed: %s", e)
        return False

def delete_bank(name: str) -> bool:
    """Delete a bank (and its instructions)"""
    try:
        cursor.execute("DELETE FROM bank_instructions WHERE bank_name=?", (name,))
        cursor.execute("DELETE FROM banks WHERE name=?", (name,))
        conn.commit()
        return True
    except Exception as e:
        logger.warning("delete_bank failed: %s", e)
        return False

def add_bank_instruction(bank_name: str, action: str, step_number: int,
                        instruction_text: str = None, instruction_images: list = None,
                        age_requirement: int = None, required_photos: int = None) -> bool:
    """Add bank instruction"""
    import json
    try:
        images_json = json.dumps(instruction_images or [])
        cursor.execute("""
            INSERT INTO bank_instructions
            (bank_name, action, step_number, instruction_text, instruction_images, age_requirement, required_photos)
            VALUES (?,?,?,?,?,?,?)
        """, (bank_name, action, step_number, instruction_text, images_json, age_requirement, required_photos))
        conn.commit()
        return True
    except Exception as e:
        logger.warning("add_bank_instruction failed: %s", e)
        return False

def get_banks():
    """Get all banks"""
    cursor.execute("SELECT name, is_active, register_enabled, change_enabled, price, description FROM banks ORDER BY name")
    return cursor.fetchall()

def get_bank_instructions(bank_name: str, action: str = None):
    """Get instructions for a bank"""
    if action:
        cursor.execute("""
            SELECT step_number, instruction_text, instruction_images, age_requirement, required_photos
            FROM bank_instructions WHERE bank_name=? AND action=? ORDER BY step_number
        """, (bank_name, action))
    else:
        cursor.execute("""
            SELECT action, step_number, instruction_text, instruction_images, age_requirement, required_photos
            FROM bank_instructions WHERE bank_name=? ORDER BY action, step_number
        """, (bank_name,))
    return cursor.fetchall()

def get_bank_form_template(bank_name: str):
    """Get form template for a bank"""
    cursor.execute("SELECT template_data FROM bank_form_templates WHERE bank_name=?", (bank_name,))
    row = cursor.fetchone()
    if row:
        import json
        return json.loads(row[0]) if row[0] else None
    return None

def set_bank_form_template(bank_name: str, template_data: dict) -> bool:
    """Set form template for a bank"""
    import json
    try:
        template_json = json.dumps(template_data, ensure_ascii=False)
        # Check if template exists
        cursor.execute("SELECT id FROM bank_form_templates WHERE bank_name=?", (bank_name,))
        if cursor.fetchone():
            # Update existing
            cursor.execute("UPDATE bank_form_templates SET template_data=?, updated_at=CURRENT_TIMESTAMP WHERE bank_name=?",
                         (template_json, bank_name))
        else:
            # Insert new
            cursor.execute("INSERT INTO bank_form_templates (bank_name, template_data) VALUES (?,?)",
                         (bank_name, template_json))
        conn.commit()
        return True
    except Exception as e:
        logger.warning("set_bank_form_template failed: %s", e)
        return False

def delete_bank_form_template(bank_name: str) -> bool:
    """Delete form template for a bank"""
    try:
        cursor.execute("DELETE FROM bank_form_templates WHERE bank_name=?", (bank_name,))
        conn.commit()
        return True
    except Exception as e:
        logger.warning("delete_bank_form_template failed: %s", e)
        return False

def get_db():
    return conn, cursor

def close_db():
    try:
        conn.close()
    except Exception:
        pass
    _cleanup_lock()

logger.info("Database initialized at %s", os.path.abspath(DB_FILE))
logger.info(
    "Foreign keys: ON | WAL mode enabled | Admin group: %s | Admin IDs: %s",
    ADMIN_GROUP_ID, sorted(ADMIN_IDS)
)
if not BOT_TOKEN or BOT_TOKEN.strip() == "":
    logger.error("BOT_TOKEN is not set. Please set the BOT_TOKEN environment variable.")

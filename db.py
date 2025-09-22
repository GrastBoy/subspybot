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
    # admins table for unified admin authorization
    _executescript("""
    CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER PRIMARY KEY,
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
                    ["price", "description", "min_age", "register_price", "change_price", "register_min_age", "change_min_age"],
        {
            "price": "ALTER TABLE banks ADD COLUMN price TEXT",
            "description": "ALTER TABLE banks ADD COLUMN description TEXT",
            "min_age": "ALTER TABLE banks ADD COLUMN min_age INTEGER DEFAULT 18",
            "register_price": "ALTER TABLE banks ADD COLUMN register_price TEXT",
            "change_price": "ALTER TABLE banks ADD COLUMN change_price TEXT", 
            "register_min_age": "ALTER TABLE banks ADD COLUMN register_min_age INTEGER DEFAULT 18",
            "change_min_age": "ALTER TABLE banks ADD COLUMN change_min_age INTEGER DEFAULT 18"
        }
    )
    # Migrations for bank_instructions table to support stage types
    _ensure_columns("bank_instructions",
                    ["step_type", "step_data", "step_order"],
        {
            "step_type": "ALTER TABLE bank_instructions ADD COLUMN step_type TEXT DEFAULT 'text_screenshots'",
            "step_data": "ALTER TABLE bank_instructions ADD COLUMN step_data TEXT",  # JSON for stage-specific config
            "step_order": "ALTER TABLE bank_instructions ADD COLUMN step_order INTEGER DEFAULT 0"
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
    """Check if user is admin by checking the database (with env fallback for safety)"""
    try:
        cursor.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
        if cursor.fetchone():
            return True
    except Exception as e:
        logger.warning("Admin DB lookup failed: %s", e)
    
    # Fallback to environment for safety during migration
    return user_id in ADMIN_IDS

def add_admin_db(user_id: int) -> bool:
    """Add admin to database. Returns True if added, False if already exists."""
    try:
        cursor.execute("INSERT INTO admins (user_id) VALUES (?)", (user_id,))
        conn.commit()
        logger.info("Added admin to DB: %s", user_id)
        return True
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            return False  # Already exists
        logger.warning("add_admin_db failed: %s", e)
        return False

def remove_admin_db(user_id: int) -> bool:
    """Remove admin from database. Returns True if removed, False if not found."""
    try:
        cursor.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        removed = cursor.rowcount > 0
        conn.commit()
        if removed:
            logger.info("Removed admin from DB: %s", user_id)
        return removed
    except Exception as e:
        logger.warning("remove_admin_db failed: %s", e)
        return False

def list_admins_db() -> list[int]:
    """Get list of all admin user IDs from database."""
    try:
        cursor.execute("SELECT user_id FROM admins ORDER BY user_id")
        return [row[0] for row in cursor.fetchall()]
    except Exception as e:
        logger.warning("list_admins_db failed: %s", e)
        return []

def seed_admins_from_env():
    """Seed admins table from ADMIN_IDS environment variable if table is empty or missing IDs."""
    try:
        if not ADMIN_IDS:
            logger.info("No ADMIN_IDS in environment, skipping admin seeding")
            return
            
        # Get current admins from DB
        current_admins = set(list_admins_db())
        
        # Add any missing admins from environment
        added_count = 0
        for admin_id in ADMIN_IDS:
            if admin_id not in current_admins:
                if add_admin_db(admin_id):
                    added_count += 1
                    
        if added_count > 0:
            logger.info("Seeded %d admins from environment to database", added_count)
        else:
            logger.info("All environment admins already in database")
            
    except Exception as e:
        logger.warning("seed_admins_from_env failed: %s", e)

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

def add_bank(name: str, register_enabled: bool = True, change_enabled: bool = True, 
             price: str = None, description: str = None, min_age: int = 18,
             register_price: str = None, change_price: str = None,
             register_min_age: int = None, change_min_age: int = None) -> bool:
    """Add a new bank with optional action-specific pricing"""
    try:
        cursor.execute("""
            INSERT INTO banks (name, register_enabled, change_enabled, price, description, min_age, 
                             register_price, change_price, register_min_age, change_min_age) 
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (name, 1 if register_enabled else 0, 1 if change_enabled else 0, price, description, min_age,
              register_price, change_price, register_min_age, change_min_age))
        conn.commit()
        return True
    except Exception as e:
        logger.warning("add_bank failed: %s", e)
        return False

def update_bank(name: str, register_enabled: bool = None, change_enabled: bool = None, 
                is_active: bool = None, price: str = None, description: str = None, 
                min_age: int = None, register_price: str = None, change_price: str = None,
                register_min_age: int = None, change_min_age: int = None) -> bool:
    """Update bank settings with optional action-specific pricing"""
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
        if min_age is not None:
            updates.append("min_age=?")
            params.append(min_age)
        if register_price is not None:
            updates.append("register_price=?")
            params.append(register_price)
        if change_price is not None:
            updates.append("change_price=?")
            params.append(change_price)
        if register_min_age is not None:
            updates.append("register_min_age=?")
            params.append(register_min_age)
        if change_min_age is not None:
            updates.append("change_min_age=?")
            params.append(change_min_age)

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
                        age_requirement: int = None, required_photos: int = None,
                        step_type: str = "text_screenshots", step_data: dict = None,
                        step_order: int = None) -> bool:
    """Add bank instruction with enhanced stage support"""
    import json
    try:
        images_json = json.dumps(instruction_images or [])
        step_data_json = json.dumps(step_data or {})
        
        # If step_order is not provided, set it to step_number for backward compatibility
        if step_order is None:
            step_order = step_number
        
        cursor.execute("""
            INSERT INTO bank_instructions
            (bank_name, action, step_number, instruction_text, instruction_images, age_requirement, required_photos, step_type, step_data, step_order)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (bank_name, action, step_number, instruction_text, images_json, age_requirement, required_photos, step_type, step_data_json, step_order))
        conn.commit()
        return True
    except Exception as e:
        logger.warning("add_bank_instruction failed: %s", e)
        return False
    except Exception as e:
        logger.warning("add_bank_instruction failed: %s", e)
        return False

def get_banks():
    """Get all banks"""
    cursor.execute("SELECT name, is_active, register_enabled, change_enabled, price, description, min_age, register_price, change_price, register_min_age, change_min_age FROM banks ORDER BY name")
    return cursor.fetchall()

def get_bank_details(bank_name: str, action: str = None):
    """Get specific bank details (price, description, min_age) - optionally action-specific"""
    cursor.execute("SELECT price, description, min_age, register_price, change_price, register_min_age, change_min_age FROM banks WHERE name=?", (bank_name,))
    result = cursor.fetchone()
    if result:
        price, description, min_age, register_price, change_price, register_min_age, change_min_age = result
        
        # If action is specified, use action-specific values, fall back to general values
        if action == "register":
            final_price = register_price or price
            final_min_age = register_min_age or min_age or 18
        elif action == "change":
            final_price = change_price or price
            final_min_age = change_min_age or min_age or 18
        else:
            # No action specified, use general values
            final_price = price
            final_min_age = min_age or 18
            
        return {
            'price': final_price,
            'description': description,
            'min_age': final_min_age
        }
    return None

def get_bank_instructions(bank_name: str, action: str = None):
    """Get instructions for a bank with enhanced stage support"""
    if action:
        cursor.execute("""
            SELECT step_number, instruction_text, instruction_images, age_requirement, required_photos, step_type, step_data, step_order
            FROM bank_instructions WHERE bank_name=? AND action=? ORDER BY step_order, step_number
        """, (bank_name, action))
    else:
        cursor.execute("""
            SELECT action, step_number, instruction_text, instruction_images, age_requirement, required_photos, step_type, step_data, step_order
            FROM bank_instructions WHERE bank_name=? ORDER BY action, step_order, step_number
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

def generate_order_questionnaire(order_id: int, bank_name: str) -> str:
    """Generate final questionnaire for manager from order and template"""
    import json
    from datetime import datetime
    
    try:
        # Get order details
        cursor.execute("""
            SELECT id, user_id, username, bank, action, stage, status, 
                   phone_number, email, created_at
            FROM orders 
            WHERE id = ?
        """, (order_id,))
        order_data = cursor.fetchone()
        
        if not order_data:
            return f"❌ Замовлення #{order_id} не знайдено"
            
        (oid, user_id, username, bank, action, stage, status, phone_number, 
         email, created_at) = order_data
        
        # Get form template
        template = get_bank_form_template(bank_name)
        if not template:
            return f"❌ Шаблон анкети для банку '{bank_name}' не знайдено"
        
        # Get order photos
        cursor.execute("""
            SELECT stage, file_unique_id, created_at 
            FROM order_photos 
            WHERE order_id = ? AND active = 1 
            ORDER BY stage, created_at
        """, (order_id,))
        photos = cursor.fetchall()
        
        # Build questionnaire
        questionnaire = f"📋 <b>Анкета замовлення #{order_id}</b>\n"
        questionnaire += f"🏦 Банк: {bank_name}\n"
        questionnaire += f"🔄 Дія: {action}\n"
        questionnaire += f"📅 Створено: {created_at}\n"
        questionnaire += f"📊 Статус: {status}\n\n"
        
        questionnaire += "<b>📝 Дані анкети:</b>\n"
        
        # Process template fields
        for field in template.get('fields', []):
            field_name = field.get('name', 'Невідоме поле')
            field_type = field.get('type', 'text')
            
            if field_name == 'ФІО':
                # Use username as full name fallback
                full_name = username or f"user_{user_id}"
                questionnaire += f"• {field_name}: {full_name}\n"
            elif 'номер користувача' in field_name.lower():
                questionnaire += f"• {field_name}: {phone_number or 'Не вказано'}\n"
            elif 'пошта' in field_name.lower() and 'менеджер' in field_name.lower():
                questionnaire += f"• {field_name}: {email or 'Не вказано'}\n"
            elif 'телеграм' in field_name.lower():
                questionnaire += f"• {field_name}: @{username or user_id}\n"
            elif 'час створення' in field_name.lower():
                questionnaire += f"• {field_name}: {created_at}\n"
            else:
                # For fields like manager phone, bank password - these would be filled during order processing
                questionnaire += f"• {field_name}: [Буде заповнено менеджером]\n"
        
        # Add photos section
        if photos:
            questionnaire += f"\n<b>📸 Скріни ({len(photos)} шт.):</b>\n"
            stages = {}
            for stage_num, file_id, photo_time in photos:
                if stage_num not in stages:
                    stages[stage_num] = []
                stages[stage_num].append((file_id, photo_time))
            
            for stage_num in sorted(stages.keys()):
                questionnaire += f"Етап {stage_num + 1}: {len(stages[stage_num])} фото\n"
        else:
            questionnaire += "\n📸 Скріни: Немає прикріплених фото\n"
            
        return questionnaire
        
    except Exception as e:
        logger.warning("generate_order_questionnaire failed: %s", e)
        return f"❌ Помилка при генерації анкети: {e}"

def get_db():
    return conn, cursor

def close_db():
    try:
        conn.close()
    except Exception:
        pass
    _cleanup_lock()


# Enhanced instruction management functions for stage-based system

def get_stage_types():
    """Get available stage types"""
    return {
        'text_screenshots': {
            'name': 'Текст + скріни',
            'description': 'Етап з текстовим поясненням та прикладами скріншотів. Користувач отримує інструкцію з поясненням що робити та приклади скрінів.',
            'fields': ['text', 'example_images']
        },
        'data_delivery': {
            'name': 'Видача даних (через менеджера)',
            'description': 'Етап автоматичної координації з менеджером для отримання номеру телефону та email. Користувач натискає кнопку запиту даних, менеджер видає коди.',
            'fields': ['phone_required', 'email_required']
        },
        'user_data_request': {
            'name': 'Запит даних від користувача',
            'description': 'Етап збору персональних даних від користувача (телефон, пошта, ПІБ, нік Telegram тощо). Менеджер налаштовує які поля потрібно зібрати.',
            'fields': ['data_fields']
        },
        'requisites_request': {
            'name': 'Запит реквізитів для переказу',
            'description': 'Фінальний етап для всіх інструкцій - користувач надає реквізити куди потрібно перерахувати кошти після завершення реєстрації.',
            'fields': ['requisites_text', 'required_requisites']
        }
    }

def update_bank_instruction(bank_name: str, action: str, step_number: int, **kwargs) -> bool:
    """Update existing bank instruction"""
    import json
    try:
        updates = []
        params = []
        
        allowed_fields = ['instruction_text', 'instruction_images', 'age_requirement', 
                         'required_photos', 'step_type', 'step_data', 'step_order']
        
        for field, value in kwargs.items():
            if field in allowed_fields:
                if field in ['instruction_images', 'step_data'] and isinstance(value, (list, dict)):
                    value = json.dumps(value)
                updates.append(f"{field}=?")
                params.append(value)
        
        if updates:
            params.extend([bank_name, action, step_number])
            cursor.execute(
                f"UPDATE bank_instructions SET {','.join(updates)} WHERE bank_name=? AND action=? AND step_number=?", 
                params
            )
            conn.commit()
            return True
        return False
    except Exception as e:
        logger.warning("update_bank_instruction failed: %s", e)
        return False

def delete_bank_instruction(bank_name: str, action: str, step_number: int) -> bool:
    """Delete bank instruction"""
    try:
        cursor.execute("DELETE FROM bank_instructions WHERE bank_name=? AND action=? AND step_number=?",
                      (bank_name, action, step_number))
        conn.commit()
        return True
    except Exception as e:
        logger.warning("delete_bank_instruction failed: %s", e)
        return False

def reorder_bank_instructions(bank_name: str, action: str, new_order: list) -> bool:
    """Reorder bank instructions. new_order is list of step_numbers in desired order"""
    try:
        for index, step_number in enumerate(new_order):
            cursor.execute(
                "UPDATE bank_instructions SET step_order=? WHERE bank_name=? AND action=? AND step_number=?",
                (index + 1, bank_name, action, step_number)
            )
        conn.commit()
        return True
    except Exception as e:
        logger.warning("reorder_bank_instructions failed: %s", e)
        return False

def get_bank_min_age(bank_name: str) -> int:
    """Get minimum age requirement for a bank"""
    try:
        cursor.execute("SELECT min_age FROM banks WHERE name=?", (bank_name,))
        result = cursor.fetchone()
        return result[0] if result else 18
    except Exception as e:
        logger.warning("get_bank_min_age failed: %s", e)
        return 18

def get_instruction_by_id(instruction_id: int):
    """Get single instruction by ID"""
    try:
        cursor.execute("""
            SELECT id, bank_name, action, step_number, instruction_text, instruction_images, 
                   age_requirement, required_photos, step_type, step_data, step_order
            FROM bank_instructions WHERE id=?
        """, (instruction_id,))
        return cursor.fetchone()
    except Exception as e:
        logger.warning("get_instruction_by_id failed: %s", e)
        return None

def get_instruction_by_step(bank_name: str, action: str, step_number: int):
    """Get single instruction by bank, action, and step_number"""
    try:
        cursor.execute("""
            SELECT id, bank_name, action, step_number, instruction_text, instruction_images, 
                   age_requirement, required_photos, step_type, step_data, step_order
            FROM bank_instructions WHERE bank_name=? AND action=? AND step_number=?
        """, (bank_name, action, step_number))
        return cursor.fetchone()
    except Exception as e:
        logger.warning("get_instruction_by_step failed: %s", e)
        return None

def get_next_step_number(bank_name: str, action: str) -> int:
    """Get next available step number for bank and action"""
    try:
        cursor.execute("SELECT MAX(step_number) FROM bank_instructions WHERE bank_name=? AND action=?",
                      (bank_name, action))
        result = cursor.fetchone()
        return (result[0] or 0) + 1
    except Exception as e:
        logger.warning("get_next_step_number failed: %s", e)
        return 1

def add_default_requisites_stage(bank_name: str, action: str) -> bool:
    """Add default requisites stage as final stage for a bank action"""
    try:
        # Check if requisites stage already exists
        cursor.execute("""
            SELECT id FROM bank_instructions 
            WHERE bank_name=? AND action=? AND step_type='requisites_request'
        """, (bank_name, action))
        
        if cursor.fetchone():
            return False  # Already exists, no need to add
        
        # Get next step number
        next_step = get_next_step_number(bank_name, action)
        
        # Add requisites stage
        requisites_text = "Будь ласка, надайте реквізити картки для переказу коштів після завершення реєстрації:\n\n• Номер картки\n• ПІБ власника картки"
        step_data = {
            'requisites_text': requisites_text,
            'required_requisites': ['card_number', 'card_holder_name'],
            'instruction_text': requisites_text
        }
        
        return add_bank_instruction(
            bank_name=bank_name,
            action=action,
            step_number=next_step,
            instruction_text=requisites_text,
            step_type='requisites_request',
            step_data=step_data
        )
    except Exception as e:
        logger.warning("add_default_requisites_stage failed: %s", e)
        return False

def ensure_requisites_stages_for_all_banks() -> int:
    """Ensure all active banks have requisites stages for enabled actions"""
    added_count = 0
    try:
        # Get all active banks
        cursor.execute("SELECT name, register_enabled, change_enabled FROM banks WHERE is_active=1")
        banks = cursor.fetchall()
        
        for bank_name, register_enabled, change_enabled in banks:
            if register_enabled:
                if add_default_requisites_stage(bank_name, "register"):
                    logger.info("Added requisites stage for %s register", bank_name)
                    added_count += 1
            
            if change_enabled:
                if add_default_requisites_stage(bank_name, "change"):
                    logger.info("Added requisites stage for %s change", bank_name)
                    added_count += 1
        
        return added_count
    except Exception as e:
        logger.warning("ensure_requisites_stages_for_all_banks failed: %s", e)
        return 0

logger.info("Database initialized at %s", os.path.abspath(DB_FILE))
logger.info(
    "Foreign keys: ON | WAL mode enabled | Admin group: %s | Admin IDs: %s",
    ADMIN_GROUP_ID, sorted(ADMIN_IDS)
)
if not BOT_TOKEN or BOT_TOKEN.strip() == "":
    logger.error("BOT_TOKEN is not set. Please set the BOT_TOKEN environment variable.")

# Seed admins from environment after all functions are defined
seed_admins_from_env()

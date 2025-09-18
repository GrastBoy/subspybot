import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Try to import static instructions as fallback with warning
try:
    from instructions import INSTRUCTIONS as STATIC_INSTRUCTIONS
    logger.warning("⚠️ LEGACY: Loading static instructions.py - consider migrating to database-based instructions")
except Exception:
    STATIC_INSTRUCTIONS = {}

# Import database-based cached instructions
try:
    from services.instructions_cache import get_instructions_cached
    _USE_DB_INSTRUCTIONS = True
except ImportError:
    logger.error("Failed to import instructions cache service")
    _USE_DB_INSTRUCTIONS = False

def get_instructions() -> Dict:
    """Get instructions with database cache priority over static fallback"""
    if _USE_DB_INSTRUCTIONS:
        try:
            return get_instructions_cached()
        except Exception as e:
            logger.error("Failed to load instructions from cache, falling back to static: %s", e)
    
    return STATIC_INSTRUCTIONS

# Dynamic bank lists based on cached instructions
def get_banks_register():
    """Get list of banks that support registration"""
    instructions = get_instructions()
    return [bank for bank, actions in instructions.items() if "register" in actions and actions["register"]]

def get_banks_change():
    """Get list of banks that support change/relink"""
    instructions = get_instructions()
    return [bank for bank, actions in instructions.items() if "change" in actions and actions["change"]]

# Backward compatibility - these will be dynamically populated
INSTRUCTIONS = get_instructions()
BANKS_REGISTER = get_banks_register()
BANKS_CHANGE = get_banks_change()

user_states: Dict[int, Dict[str, Any]] = {}

# Conversation states
COOPERATION_INPUT = 0
REJECT_REASON = 1
MANAGER_MESSAGE = 2
STAGE2_MANAGER_WAIT_DATA = 10
STAGE2_MANAGER_WAIT_CODE = 11
STAGE2_MANAGER_WAIT_MSG = 12   # новий стан для повідомлення користувачу (Stage2)

def find_age_requirement(bank: str, action: str) -> Optional[int]:
    instructions = get_instructions()
    steps = instructions.get(bank, {}).get(action, [])
    for step in steps:
        if isinstance(step, dict) and "age" in step:
            return step["age"]
    return None

def get_required_photos(bank: str, action: str, stage0: int) -> Optional[int]:
    """
    Повертає значення required_photos для конкретного етапу (0-based).
    Якщо поле відсутнє або індекс виходить за межі — повертає None.
    """
    try:
        instructions = get_instructions()
        steps = instructions.get(bank, {}).get(action, [])
        step = steps[stage0]
        if isinstance(step, dict):
            val = step.get("required_photos")
            if isinstance(val, int):
                return val
    except Exception:
        pass
    return None

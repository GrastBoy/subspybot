import logging
import warnings
from typing import Any, Dict, Optional

from services.instructions import get_instructions, invalidate_instructions_cache

logger = logging.getLogger(__name__)

# Legacy instructions import with warning
try:
    from instructions import INSTRUCTIONS as LEGACY_INSTRUCTIONS
    # Check if legacy instructions are non-empty
    if LEGACY_INSTRUCTIONS:
        warning_msg = "Legacy instructions.py detected. Runtime now uses DB-driven instructions; legacy file will be ignored (except for migration)."
        warnings.warn(warning_msg, UserWarning)
        logger.warning(warning_msg)
except Exception:
    LEGACY_INSTRUCTIONS = {}

# Use cached DB-driven instructions
def _get_current_instructions():
    """Get current instructions from DB cache"""
    return get_instructions()

# Dynamic properties that update with cache
def _get_banks_register():
    instructions = _get_current_instructions()
    return [bank for bank, actions in instructions.items() if "register" in actions and actions["register"]]

def _get_banks_change():
    instructions = _get_current_instructions()
    return [bank for bank, actions in instructions.items() if "change" in actions and actions["change"]]

# Legacy compatibility - these will be dynamically updated
BANKS_REGISTER = []
BANKS_CHANGE = []

# Update function to refresh bank lists
def _update_bank_lists():
    """Update BANKS_REGISTER and BANKS_CHANGE with current data"""
    global BANKS_REGISTER, BANKS_CHANGE
    BANKS_REGISTER = _get_banks_register()
    BANKS_CHANGE = _get_banks_change()

# Initialize bank lists
_update_bank_lists()

user_states: Dict[int, Dict[str, Any]] = {}

# Conversation states
COOPERATION_INPUT = 0
REJECT_REASON = 1
MANAGER_MESSAGE = 2
STAGE2_MANAGER_WAIT_DATA = 10
STAGE2_MANAGER_WAIT_CODE = 11
STAGE2_MANAGER_WAIT_MSG = 12   # новий стан для повідомлення користувачу (Stage2)

def find_age_requirement(bank: str, action: str) -> Optional[int]:
    instructions = _get_current_instructions()
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
        instructions = _get_current_instructions()
        steps = instructions.get(bank, {}).get(action, [])
        step = steps[stage0]
        if isinstance(step, dict):
            val = step.get("required_photos")
            if isinstance(val, int):
                return val
    except Exception:
        pass
    return None

def reload_instructions():
    """
    Helper to reload instructions from database and update bank lists.
    This invalidates the cache and forces a fresh load.
    """
    invalidate_instructions_cache()
    _update_bank_lists()
    logger.info("Instructions reloaded from database")

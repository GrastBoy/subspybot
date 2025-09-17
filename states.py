from typing import Any, Dict, Optional

# Dynamic instruction handling - DB is the primary source, fallback to static if needed
try:
    from services.instructions import get_instructions, find_age_requirement as db_find_age_requirement, get_required_photos as db_get_required_photos
    USE_DYNAMIC_INSTRUCTIONS = True
except Exception:
    USE_DYNAMIC_INSTRUCTIONS = False
    try:
        from instructions import INSTRUCTIONS
    except Exception:
        INSTRUCTIONS = {}

def get_instructions():
    """Get instructions from DB or fallback to static file"""
    if USE_DYNAMIC_INSTRUCTIONS:
        from services.instructions import get_instructions as _get_instructions
        return _get_instructions()
    else:
        return INSTRUCTIONS

def get_banks_for_action(action: str):
    """Get banks that support specific action"""
    if USE_DYNAMIC_INSTRUCTIONS:
        from services.instructions import get_banks_for_action
        return get_banks_for_action(action)
    else:
        instructions = get_instructions()
        return [bank for bank, actions in instructions.items() if action in actions and actions[action]]

# Backward compatibility - these are used by other modules
BANKS_REGISTER = get_banks_for_action("register")
BANKS_CHANGE = get_banks_for_action("change")

user_states: Dict[int, Dict[str, Any]] = {}

# Conversation states
COOPERATION_INPUT = 0
REJECT_REASON = 1
MANAGER_MESSAGE = 2
STAGE2_MANAGER_WAIT_DATA = 10
STAGE2_MANAGER_WAIT_CODE = 11
STAGE2_MANAGER_WAIT_MSG = 12   # новий стан для повідомлення користувачу (Stage2)

def find_age_requirement(bank: str, action: str) -> Optional[int]:
    """Find age requirement for bank and action using dynamic DB lookup"""
    if USE_DYNAMIC_INSTRUCTIONS:
        return db_find_age_requirement(bank, action)
    else:
        steps = INSTRUCTIONS.get(bank, {}).get(action, [])
        for step in steps:
            if isinstance(step, dict) and "age" in step:
                return step["age"]
        return None

def get_required_photos(bank: str, action: str, stage0: int) -> Optional[int]:
    """
    Get required_photos value for specific stage using dynamic DB lookup.
    Falls back to static instructions if dynamic lookup fails.
    """
    if USE_DYNAMIC_INSTRUCTIONS:
        return db_get_required_photos(bank, action, stage0)
    else:
        try:
            steps = INSTRUCTIONS.get(bank, {}).get(action, [])
            step = steps[stage0]
            if isinstance(step, dict):
                val = step.get("required_photos")
                if isinstance(val, int):
                    return val
        except Exception:
            pass
        return None

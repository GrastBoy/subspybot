from typing import Any, Dict, Optional

try:
    from instructions import INSTRUCTIONS
except Exception:
    INSTRUCTIONS = {}

BANKS_REGISTER = [bank for bank, actions in INSTRUCTIONS.items() if "register" in actions and actions["register"]]
BANKS_CHANGE = [bank for bank, actions in INSTRUCTIONS.items() if "change" in actions and actions["change"]]

user_states: Dict[int, Dict[str, Any]] = {}

# Conversation states
COOPERATION_INPUT = 0
REJECT_REASON = 1
MANAGER_MESSAGE = 2
STAGE2_MANAGER_WAIT_DATA = 10
STAGE2_MANAGER_WAIT_CODE = 11
STAGE2_MANAGER_WAIT_MSG = 12   # новий стан для повідомлення користувачу (Stage2)

def find_age_requirement(bank: str, action: str) -> Optional[int]:
    steps = INSTRUCTIONS.get(bank, {}).get(action, [])
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
        steps = INSTRUCTIONS.get(bank, {}).get(action, [])
        step = steps[stage0]
        if isinstance(step, dict):
            val = step.get("required_photos")
            if isinstance(val, int):
                return val
    except Exception:
        pass
    return None

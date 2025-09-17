from typing import Any, Dict, Optional

# Import dynamic instruction loading services
from services.instructions import (
    get_instructions, 
    find_age_requirement_dynamic, 
    get_required_photos_dynamic,
    get_banks_for_action
)

# For backward compatibility, provide INSTRUCTIONS that loads from DB
# Note: This loads once at module import time. For real-time updates use get_instructions()
INSTRUCTIONS = get_instructions()

# Dynamic bank lists - computed from DB data
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
    """Find age requirement for a bank and action using dynamic DB data"""
    return find_age_requirement_dynamic(bank, action)

def get_required_photos(bank: str, action: str, stage0: int) -> Optional[int]:
    """
    Повертає значення required_photos для конкретного етапу (0-based) using dynamic DB data.
    Якщо поле відсутнє або індекс виходить за межі — повертає None.
    """
    return get_required_photos_dynamic(bank, action, stage0)

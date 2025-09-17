from typing import Any, Dict, Optional

try:
    from instructions import INSTRUCTIONS
except Exception:
    INSTRUCTIONS = {}

def get_banks_for_action(action: str):
    """Get banks that support the specified action from database"""
    from db import get_banks
    
    try:
        banks = get_banks()
        result = []
        
        for name, is_active, register_enabled, change_enabled, price, description in banks:
            if not is_active:  # Skip inactive banks
                continue
                
            if action == "register" and register_enabled:
                result.append(name)
            elif action == "change" and change_enabled:
                result.append(name)
        
        return result
    except Exception:
        # Fallback to instructions.py if database is not available
        return [bank for bank, actions in INSTRUCTIONS.items() if action in actions and actions[action]]

# For backward compatibility, provide functions instead of static lists
def get_banks_register():
    return get_banks_for_action("register")

def get_banks_change():
    return get_banks_for_action("change")

# For immediate compatibility - these will be empty initially but functions above should be used
BANKS_REGISTER = []
BANKS_CHANGE = []

user_states: Dict[int, Dict[str, Any]] = {}

# Conversation states
COOPERATION_INPUT = 0
REJECT_REASON = 1
MANAGER_MESSAGE = 2
STAGE2_MANAGER_WAIT_DATA = 10
STAGE2_MANAGER_WAIT_CODE = 11
STAGE2_MANAGER_WAIT_MSG = 12   # новий стан для повідомлення користувачу (Stage2)

def find_age_requirement(bank: str, action: str) -> Optional[int]:
    """Find age requirement for bank action from database"""
    from db import get_bank_instructions
    
    try:
        instructions = get_bank_instructions(bank, action)
        for instruction in instructions:
            # instruction format: (step_number, instruction_text, instruction_images, age_requirement, required_photos)
            if len(instruction) > 3 and instruction[3] is not None:
                return instruction[3]
    except Exception:
        pass
    
    return None

def get_required_photos(bank: str, action: str, stage0: int) -> Optional[int]:
    """
    Повертає значення required_photos для конкретного етапу (0-based).
    Якщо поле відсутнє або індекс виходить за межі — повертає None.
    """
    from db import get_bank_instructions
    
    try:
        instructions = get_bank_instructions(bank, action)
        if stage0 < len(instructions):
            instruction = instructions[stage0]
            # instruction format: (step_number, instruction_text, instruction_images, age_requirement, required_photos)
            if len(instruction) > 4 and instruction[4] is not None:
                return instruction[4]
    except Exception:
        pass
    
    return None

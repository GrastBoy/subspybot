"""
Dynamic instruction loading service.
Loads bank instructions and metadata from database instead of static files.
"""
import json
from typing import Dict, Any, List, Optional
from db import cursor, get_banks, get_bank_instructions


def load_instructions_from_db() -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    """
    Load instructions from database in the same format as static INSTRUCTIONS dict.
    
    Returns:
        Dict with bank names as keys, containing action dicts (register/change) 
        with lists of step instructions containing text, images, age, required_photos etc.
    """
    instructions = {}
    
    try:
        # Get all active banks
        banks = get_banks()
        
        for bank_data in banks:
            bank_name = bank_data[0]
            is_active = bank_data[1]
            register_enabled = bank_data[2] 
            change_enabled = bank_data[3]
            
            # Skip inactive banks
            if not is_active:
                continue
            
            bank_instructions = {}
            
            # Load register instructions if enabled
            if register_enabled:
                register_steps = get_bank_instructions(bank_name, "register")
                if register_steps:
                    bank_instructions["register"] = _convert_db_steps_to_instructions(register_steps)
            
            # Load change instructions if enabled  
            if change_enabled:
                change_steps = get_bank_instructions(bank_name, "change")
                if change_steps:
                    bank_instructions["change"] = _convert_db_steps_to_instructions(change_steps)
            
            # Only add bank if it has at least one action
            if bank_instructions:
                instructions[bank_name] = bank_instructions
                
    except Exception as e:
        # If DB load fails, return empty dict to avoid breaking the app
        # Log the error but don't crash
        import logging
        logging.getLogger(__name__).warning(f"Failed to load instructions from DB: {e}")
        return {}
    
    return instructions


def _convert_db_steps_to_instructions(db_steps: List[tuple]) -> List[Dict[str, Any]]:
    """
    Convert database step tuples to instruction dict format.
    
    DB format: (step_number, instruction_text, instruction_images, age_requirement, required_photos)
    Output format: [{"text": str, "images": list, "age": int, "required_photos": int}, ...]
    """
    instructions = []
    
    for step_data in db_steps:
        step_number, instruction_text, images_json, age_req, required_photos = step_data
        
        step_dict = {}
        
        # Add text
        if instruction_text:
            step_dict["text"] = instruction_text
        
        # Parse and add images
        try:
            if images_json:
                images = json.loads(images_json)
                step_dict["images"] = images if isinstance(images, list) else []
            else:
                step_dict["images"] = []
        except (json.JSONDecodeError, TypeError):
            step_dict["images"] = []
        
        # Add age requirement if present
        if age_req is not None:
            step_dict["age"] = age_req
            
        # Add required photos if present
        if required_photos is not None:
            step_dict["required_photos"] = required_photos
        
        instructions.append(step_dict)
    
    return instructions


def get_instructions() -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    """
    Main entry point for getting instructions.
    This function can be used to replace direct INSTRUCTIONS import.
    """
    return load_instructions_from_db()


def find_age_requirement_dynamic(bank: str, action: str) -> Optional[int]:
    """
    Dynamic version of find_age_requirement that reads from DB.
    """
    instructions = load_instructions_from_db()
    steps = instructions.get(bank, {}).get(action, [])
    for step in steps:
        if isinstance(step, dict) and "age" in step:
            return step["age"]
    return None


def get_required_photos_dynamic(bank: str, action: str, stage0: int) -> Optional[int]:
    """
    Dynamic version of get_required_photos that reads from DB.
    """
    try:
        instructions = load_instructions_from_db()
        steps = instructions.get(bank, {}).get(action, [])
        step = steps[stage0]
        if isinstance(step, dict):
            val = step.get("required_photos")
            if isinstance(val, int):
                return val
    except Exception:
        pass
    return None


def get_banks_for_action(action: str) -> List[str]:
    """
    Get list of banks that support a specific action (register/change).
    Replaces the BANKS_REGISTER and BANKS_CHANGE constants.
    """
    instructions = load_instructions_from_db()
    return [
        bank for bank, actions in instructions.items() 
        if action in actions and actions[action]
    ]
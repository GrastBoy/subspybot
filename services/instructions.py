"""
Dynamic instruction service for building INSTRUCTIONS-like structure from database.
This module provides the core functionality to replace static instructions.py
with dynamic DB-based instruction loading.
"""

import json
from typing import Dict, List, Optional, Any
from db import get_banks, get_bank_instructions


def get_instructions() -> Dict[str, Dict[str, Any]]:
    """
    Build INSTRUCTIONS-like structure directly from DB (banks + bank_instructions tables).
    
    Returns:
        Dict with same structure as static instructions.py:
        {
            "BankName": {
                "register": [
                    {
                        "text": "instruction text",
                        "images": ["path1", "path2"],
                        "age": 18,
                        "required_photos": 1
                    },
                    ...
                ],
                "change": [...]
            }
        }
    """
    instructions = {}
    
    try:
        # Get all active banks
        banks = get_banks()
        
        for bank_data in banks:
            bank_name, is_active, register_enabled, change_enabled = bank_data[:4]
            
            # Skip inactive banks
            if not is_active:
                continue
                
            bank_instructions = {}
            
            # Get register instructions if enabled
            if register_enabled:
                register_steps = get_bank_instructions(bank_name, "register")
                if register_steps:
                    bank_instructions["register"] = []
                    for step_data in register_steps:
                        step_number, instruction_text, instruction_images, age_requirement, required_photos = step_data
                        
                        step_dict = {"text": instruction_text or ""}
                        
                        # Parse images JSON
                        try:
                            images = json.loads(instruction_images or "[]")
                            step_dict["images"] = images if isinstance(images, list) else []
                        except (json.JSONDecodeError, TypeError):
                            step_dict["images"] = []
                        
                        # Add optional fields if present
                        if age_requirement:
                            step_dict["age"] = age_requirement
                        if required_photos:
                            step_dict["required_photos"] = required_photos
                        
                        bank_instructions["register"].append(step_dict)
            
            # Get change instructions if enabled
            if change_enabled:
                change_steps = get_bank_instructions(bank_name, "change")
                if change_steps:
                    bank_instructions["change"] = []
                    for step_data in change_steps:
                        step_number, instruction_text, instruction_images, age_requirement, required_photos = step_data
                        
                        step_dict = {"text": instruction_text or ""}
                        
                        # Parse images JSON
                        try:
                            images = json.loads(instruction_images or "[]")
                            step_dict["images"] = images if isinstance(images, list) else []
                        except (json.JSONDecodeError, TypeError):
                            step_dict["images"] = []
                        
                        # Add optional fields if present
                        if age_requirement:
                            step_dict["age"] = age_requirement
                        if required_photos:
                            step_dict["required_photos"] = required_photos
                        
                        bank_instructions["change"].append(step_dict)
            
            # Only add bank to instructions if it has at least one action
            if bank_instructions:
                instructions[bank_name] = bank_instructions
                
    except Exception as e:
        # Log error but don't fail completely - fallback to empty instructions
        import logging
        logging.warning(f"Error building dynamic instructions: {e}")
        
    return instructions


def get_banks_for_action(action: str) -> List[str]:
    """
    Get list of banks that support a specific action (register/change).
    
    Args:
        action: Either "register" or "change"
        
    Returns:
        List of bank names that support the action
    """
    instructions = get_instructions()
    return [
        bank for bank, actions in instructions.items() 
        if action in actions and actions[action]
    ]


def find_age_requirement(bank: str, action: str) -> Optional[int]:
    """
    Find age requirement for a specific bank and action.
    
    Args:
        bank: Bank name
        action: Action type ("register" or "change")
        
    Returns:
        Age requirement as integer, or None if not found
    """
    instructions = get_instructions()
    steps = instructions.get(bank, {}).get(action, [])
    
    for step in steps:
        if isinstance(step, dict) and "age" in step:
            return step["age"]
    return None


def get_required_photos(bank: str, action: str, stage0: int) -> Optional[int]:
    """
    Get required_photos value for a specific step.
    
    Args:
        bank: Bank name
        action: Action type ("register" or "change")
        stage0: Step index (0-based)
        
    Returns:
        Required photos count as integer, or None if not found
    """
    try:
        instructions = get_instructions()
        steps = instructions.get(bank, {}).get(action, [])
        
        if 0 <= stage0 < len(steps):
            step = steps[stage0]
            if isinstance(step, dict):
                val = step.get("required_photos")
                if isinstance(val, int):
                    return val
    except Exception:
        pass
    return None
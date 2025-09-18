"""
Dynamic instructions loading from database.
Provides functions to load instructions from banks and bank_instructions tables.
"""
import json
import logging
from typing import Any, Dict

from db import get_bank_instructions, get_banks

logger = logging.getLogger(__name__)


def load_instructions_from_db() -> Dict[str, Any]:
    """
    Load instructions from database and build structure identical to old INSTRUCTIONS constant.

    Returns:
        Dictionary in format:
        {
          "Bank": {
            "register": [ {text, images, age?, required_photos?}, ... ],
            "change": [...]
          },
          ...
        }
    """
    instructions = {}

    try:
        # Get all active banks
        banks = get_banks()

        for bank_name, is_active, register_enabled, change_enabled, price, description in banks:
            if not is_active:
                continue  # Skip inactive banks

            bank_instructions = {}

            # Load register instructions if enabled
            if register_enabled:
                register_steps = get_bank_instructions(bank_name, "register")
                if register_steps:
                    bank_instructions["register"] = []
                    for step_num, instr_text, images_json, age_req, req_photos in register_steps:
                        step_data = {"text": instr_text or ""}

                        # Parse images JSON
                        if images_json:
                            try:
                                step_data["images"] = json.loads(images_json)
                            except (json.JSONDecodeError, ValueError):
                                step_data["images"] = []
                        else:
                            step_data["images"] = []

                        # Add age requirement if specified
                        if age_req:
                            step_data["age"] = age_req

                        # Add required_photos if specified
                        if req_photos:
                            step_data["required_photos"] = req_photos

                        bank_instructions["register"].append(step_data)

            # Load change instructions if enabled
            if change_enabled:
                change_steps = get_bank_instructions(bank_name, "change")
                if change_steps:
                    bank_instructions["change"] = []
                    for step_num, instr_text, images_json, age_req, req_photos in change_steps:
                        step_data = {"text": instr_text or ""}

                        # Parse images JSON
                        if images_json:
                            try:
                                step_data["images"] = json.loads(images_json)
                            except (json.JSONDecodeError, ValueError):
                                step_data["images"] = []
                        else:
                            step_data["images"] = []

                        # Add age requirement if specified
                        if age_req:
                            step_data["age"] = age_req

                        # Add required_photos if specified
                        if req_photos:
                            step_data["required_photos"] = req_photos

                        bank_instructions["change"].append(step_data)

            # Only add bank if it has instructions
            if bank_instructions:
                instructions[bank_name] = bank_instructions

    except Exception as e:
        logger.warning("load_instructions_from_db failed: %s", e)

    return instructions

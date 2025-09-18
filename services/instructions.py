"""
TTL-cached instructions service for dynamic DB-based instructions
"""
import json
import logging
import os
import time
from typing import Any, Dict, Optional

from db import get_bank_instructions, get_banks

logger = logging.getLogger(__name__)

# Cache storage
_instructions_cache: Optional[Dict[str, Any]] = None
_cache_timestamp: Optional[float] = None


def _get_ttl_seconds() -> int:
    """Get TTL from environment variable, with default and validation"""
    try:
        ttl = int(os.getenv("INSTRUCTIONS_TTL", "10"))
        return max(0, ttl)  # Ensure non-negative
    except (ValueError, TypeError):
        return 10  # Default fallback


def load_instructions_from_db() -> Dict[str, Any]:
    """
    Load instructions from database with timing and logging.
    Returns instructions in the same format as legacy instructions.py
    """
    start_time = time.perf_counter()
    
    # Get all active banks
    banks = get_banks()
    instructions_data = {}
    total_steps = 0
    bank_count = 0
    
    for bank_row in banks:
        # Handle different tuple lengths for compatibility
        if len(bank_row) >= 4:
            bank_name, is_active, register_enabled, change_enabled = bank_row[:4]
        else:
            bank_name, is_active, register_enabled, change_enabled = bank_row + (1, 1)  # defaults
            
        if not is_active:
            continue
            
        bank_instructions = {}
        bank_has_instructions = False
        
        # Load register instructions
        if register_enabled:
            register_instructions = get_bank_instructions(bank_name, "register")
            if register_instructions:
                bank_instructions["register"] = []
                for step_num, instr_text, images_json, age_req, req_photos in register_instructions:
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
                        
                    # Add required photos if specified  
                    if req_photos:
                        step_data["required_photos"] = req_photos
                        
                    bank_instructions["register"].append(step_data)
                    total_steps += 1
                    
                bank_has_instructions = True
        
        # Load change instructions
        if change_enabled:
            change_instructions = get_bank_instructions(bank_name, "change")
            if change_instructions:
                bank_instructions["change"] = []
                for step_num, instr_text, images_json, age_req, req_photos in change_instructions:
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
                        
                    # Add required photos if specified
                    if req_photos:
                        step_data["required_photos"] = req_photos
                        
                    bank_instructions["change"].append(step_data)
                    total_steps += 1
                    
                bank_has_instructions = True
        
        if bank_has_instructions:
            instructions_data[bank_name] = bank_instructions
            bank_count += 1
    
    # Calculate timing
    end_time = time.perf_counter()
    duration_ms = (end_time - start_time) * 1000
    
    # Log the load operation
    ttl = _get_ttl_seconds()
    logger.info(f"Instructions cache refreshed: banks={bank_count} steps={total_steps} in {duration_ms:.1f}ms (ttl={ttl})")
    logger.debug(f"Loaded instructions timing: {duration_ms:.3f}ms for {bank_count} banks")
    
    return instructions_data


def get_instructions_cached() -> Dict[str, Any]:
    """
    Get instructions from cache or reload if TTL expired.
    Returns cached instructions or reloads from database.
    """
    global _instructions_cache, _cache_timestamp
    
    ttl_seconds = _get_ttl_seconds()
    current_time = time.time()
    
    # Check if cache is valid
    if (_instructions_cache is not None and 
        _cache_timestamp is not None and 
        ttl_seconds > 0 and
        (current_time - _cache_timestamp) < ttl_seconds):
        return _instructions_cache
    
    # Cache is invalid or TTL is 0 (disabled), reload
    _instructions_cache = load_instructions_from_db()
    _cache_timestamp = current_time
    
    return _instructions_cache


def invalidate_instructions_cache():
    """
    Manually invalidate the instructions cache.
    Next call to get_instructions_cached() will reload from database.
    """
    global _instructions_cache, _cache_timestamp
    _instructions_cache = None
    _cache_timestamp = None
    logger.debug("Instructions cache manually invalidated")


def get_instructions() -> Dict[str, Any]:
    """
    Get current instructions (cached version).
    This is the main entry point for accessing instructions.
    """
    return get_instructions_cached()
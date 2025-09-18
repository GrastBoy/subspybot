"""
TTL Cache for database-based instructions
"""
import json
import logging
import time
from typing import Dict, Optional, Tuple

from db import get_bank_instructions, get_banks

logger = logging.getLogger(__name__)

# Cache configuration
CACHE_TTL_SECONDS = 300  # 5 minutes default TTL
_instructions_cache: Optional[Dict] = None
_cache_timestamp: Optional[float] = None
_cache_stats = {"hits": 0, "misses": 0, "reloads": 0}

def _is_cache_valid() -> bool:
    """Check if cache is valid (not expired)"""
    if _instructions_cache is None or _cache_timestamp is None:
        return False
    return (time.time() - _cache_timestamp) < CACHE_TTL_SECONDS

def _load_instructions_from_db() -> Dict:
    """Load instructions from database"""
    logger.info("Loading instructions from database...")

    instructions_data = {}
    banks = get_banks()

    for bank_name, is_active, register_enabled, change_enabled, price, description in banks:
        if not is_active:
            continue

        bank_instructions = {}

        if register_enabled:
            register_instructions = get_bank_instructions(bank_name, "register")
            if register_instructions:
                bank_instructions["register"] = []
                for step_num, instr_text, images_json, age_req, req_photos in register_instructions:
                    step_data = {"text": instr_text}
                    if images_json:
                        try:
                            step_data["images"] = json.loads(images_json)
                        except (json.JSONDecodeError, ValueError):
                            step_data["images"] = []
                    else:
                        step_data["images"] = []
                    if age_req:
                        step_data["age"] = age_req
                    if req_photos:
                        step_data["required_photos"] = req_photos
                    bank_instructions["register"].append(step_data)

        if change_enabled:
            change_instructions = get_bank_instructions(bank_name, "change")
            if change_instructions:
                bank_instructions["change"] = []
                for step_num, instr_text, images_json, age_req, req_photos in change_instructions:
                    step_data = {"text": instr_text}
                    if images_json:
                        try:
                            step_data["images"] = json.loads(images_json)
                        except (json.JSONDecodeError, ValueError):
                            step_data["images"] = []
                    else:
                        step_data["images"] = []
                    if age_req:
                        step_data["age"] = age_req
                    if req_photos:
                        step_data["required_photos"] = req_photos
                    bank_instructions["change"].append(step_data)

        if bank_instructions:
            instructions_data[bank_name] = bank_instructions

    logger.info("Loaded instructions for %d banks from database", len(instructions_data))
    return instructions_data

def get_instructions_cached() -> Dict:
    """Get instructions with TTL caching"""
    global _instructions_cache, _cache_timestamp, _cache_stats

    if _is_cache_valid():
        _cache_stats["hits"] += 1
        logger.debug("Instructions cache HIT (TTL: %.1f seconds remaining)",
                     CACHE_TTL_SECONDS - (time.time() - _cache_timestamp))
        return _instructions_cache

    # Cache miss or expired - reload from database
    _cache_stats["misses"] += 1
    _cache_stats["reloads"] += 1

    _instructions_cache = _load_instructions_from_db()
    _cache_timestamp = time.time()

    logger.info("Instructions cache RELOAD (#%d) - loaded %d banks",
                _cache_stats["reloads"], len(_instructions_cache))

    return _instructions_cache

def invalidate_instructions_cache():
    """Invalidate the instructions cache"""
    global _instructions_cache, _cache_timestamp

    _instructions_cache = None
    _cache_timestamp = None

    logger.info("Instructions cache invalidated")

def reload_instructions() -> Tuple[int, int]:
    """Force reload instructions cache and return (banks_count, total_steps)"""
    invalidate_instructions_cache()
    instructions = get_instructions_cached()

    banks_count = len(instructions)
    total_steps = sum(
        len(actions.get("register", [])) + len(actions.get("change", []))
        for actions in instructions.values()
    )

    return banks_count, total_steps

def get_cache_stats() -> Dict:
    """Get cache statistics"""
    return {
        **_cache_stats,
        "cache_valid": _is_cache_valid(),
        "cache_age_seconds": time.time() - _cache_timestamp if _cache_timestamp else None,
        "ttl_seconds": CACHE_TTL_SECONDS
    }

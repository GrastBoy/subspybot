# Database Instructions Cache

This implementation consolidates PRs #20 and #21, replacing static `instructions.py` with dynamic database-based instructions that use TTL caching.

## Features

### 1. Database-Based Instructions (PR #20)
- Instructions are now loaded from the database instead of static `instructions.py`
- Automatic fallback to static instructions with warning if cache service fails
- Dynamic bank lists based on current database state

### 2. TTL Cache (PR #21)
- 5-minute TTL cache for database instructions
- Comprehensive logging of cache operations
- Cache hit/miss statistics
- Legacy import warning when falling back to static instructions

### 3. Admin Reload Command
- `/reload_instructions` command for admins only
- Forcibly invalidates and reloads the instructions cache
- Shows detailed response with banks count, steps count, TTL, and reload count

## Technical Implementation

### Cache Service (`services/instructions_cache.py`)
- `get_instructions_cached()` - Get instructions with TTL caching
- `reload_instructions()` - Force reload and return stats
- `invalidate_instructions_cache()` - Clear cache
- `get_cache_stats()` - Get cache statistics

### Updated States (`states.py`)
- `get_instructions()` - Get instructions with database priority
- `get_banks_register()` / `get_banks_change()` - Dynamic bank lists
- Backward compatibility maintained for `INSTRUCTIONS`, `BANKS_REGISTER`, `BANKS_CHANGE`

### Admin Command (`handlers/reload_instructions.py`)
- Admin-only access control using existing `is_admin()` function
- Comprehensive error handling and logging
- User-friendly Ukrainian response message

## Usage

### For Admins
Use `/reload_instructions` command to force refresh instructions cache when database changes are made.

### For Developers
The system automatically uses database instructions. Legacy `instructions.py` is only used as fallback with warning.

## Cache Behavior
- **TTL**: 5 minutes (300 seconds)
- **Auto-reload**: Cache expires and reloads on next access
- **Manual reload**: Admin command forces immediate reload
- **Statistics**: Tracks hits, misses, and reload count
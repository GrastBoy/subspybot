# SubSpyBot - Telegram Bot for Banking Registration/Change

Always reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.

SubSpyBot is a Python Telegram bot for handling banking registration and account change orders. It features a multi-stage workflow with photo uploads, admin approval, and data entry assistance through manager groups.

## Working Effectively

### Bootstrap and Setup
- Create virtual environment: `python3 -m venv venv`
- Activate environment: `source venv/bin/activate`  
- Install dependencies: `pip install python-telegram-bot --upgrade`
  - **TIMING**: 30-60 seconds when network is available
  - **NETWORK DEPENDENCY**: May fail with timeout errors if PyPI is inaccessible
  - **WORKAROUND**: If pip fails due to network issues, you can still test most functionality without telegram package
- Set environment variables (optional - defaults provided):
  ```bash
  export BOT_TOKEN="your-telegram-bot-token"
  export ADMIN_ID="your-admin-user-id"  
  export ADMIN_GROUP_ID="your-admin-group-chat-id"
  ```

### Running the Bot
- **ALWAYS** activate virtual environment first: `source venv/bin/activate`
- Run the bot: `python3 client_bot.py`
- Bot startup takes ~0.2 seconds for imports
- **EXPECTED BEHAVIOR**: Bot will fail with network error if BOT_TOKEN is invalid/missing - this is normal
- **NETWORK DEPENDENCY**: Bot requires internet access to reach Telegram API (api.telegram.org)

### Code Validation
- Test imports: `python3 -c "import client_bot; print('Import successful')"` - takes ~0.2 seconds
- Compile check: `python3 -m py_compile client_bot.py handlers/*.py` - takes ~0.1 seconds
- Database initialization: `python3 -c "import db; print('DB ready')"` - auto-creates orders.db

## Validation Scenarios

### Manual Testing Requirements
**CRITICAL**: You cannot run full end-to-end tests without a valid Telegram bot token and network access. However, validate these scenarios:

1. **Import Testing**: Test core modules that don't require telegram package
2. **Database Schema**: Confirm SQLite database initializes with proper tables  
3. **Configuration Loading**: Verify instructions.py loads bank configurations correctly
4. **Syntax Validation**: Run py_compile on all Python files

### Test Commands That Work (No Network Required)
```bash
# Test instruction loading (0.02s)
python3 -c "from instructions import INSTRUCTIONS; print(f'Banks: {list(INSTRUCTIONS.keys())[:3]}')"

# Test database initialization (0.04s)  
python3 -c "import db; print('Database initialized')"

# Syntax validation (0.06s)
python3 -m py_compile *.py handlers/*.py

# Test states module
python3 -c "from states import BANKS_REGISTER, BANKS_CHANGE; print('States loaded')"
```

### Test Commands That Require Network
```bash
# Test full imports (requires pip install python-telegram-bot)
python3 -c "import client_bot; print('Success')"

# Test bot startup (will fail without valid BOT_TOKEN - expected)
python3 client_bot.py
```

### Expected Validation Results
- **Instruction loading**: ~0.02 seconds, loads 7+ Ukrainian bank configurations
- **Database initialization**: ~0.04 seconds, creates orders.db file (~52KB) with proper schema  
- **Syntax compilation**: ~0.06 seconds, validates all Python files
- **Full import test**: Requires python-telegram-bot package, ~0.2 seconds when available
- **Bot startup**: Attempts Telegram API connection (will fail without valid token - this is expected)

## Repository Structure

### Key Files and Locations
- **Main entry**: `client_bot.py` - Bot application and handler setup
- **Database**: `db.py` - SQLite database operations and schema
- **Configuration**: `instructions.py` - Bank-specific workflows and UI text (Ukrainian)
- **State management**: `states.py` - Conversation states and bank filtering
- **Handlers**: `handlers/` directory contains:
  - `menu_handlers.py` - Main menu and navigation
  - `photo_handlers.py` - Image upload processing
  - `admin_handlers.py` - Administrative commands
  - `stage2_handlers.py` - Data entry and verification flows
  - `cooperation_handlers.py` - User cooperation requests

### Important Data Files
- `orders.db` - SQLite database (auto-generated)
- `admins.txt` - Admin user IDs (one per line)
- `templates.json` - Message templates for managers
- `images/` - Example screenshots for instructions
- `.gitignore` - Excludes venv/, __pycache__/, *.db files

### Common Tasks Patterns
- **Adding new bank**: Edit `instructions.py` INSTRUCTIONS dictionary
- **Admin commands**: Check `handlers/admin_handlers.py` for /addgroup, /delgroup, etc.
- **Stage workflows**: See `states.py` for conversation state definitions
- **Database queries**: Use patterns from `db.py` with SQLite cursor operations

## Build and Dependency Information

### Timing Expectations
- **Instruction loading**: 0.02 seconds - NEVER CANCEL
- **Database operations**: 0.04 seconds (SQLite is fast) - NEVER CANCEL  
- **Syntax compilation**: 0.06 seconds - NEVER CANCEL
- **pip install**: 30-60 seconds (when network available) - NEVER CANCEL
- **Module imports**: 0.2 seconds (with telegram package) - NEVER CANCEL
- **Bot startup**: Instant until Telegram API call

### Dependencies
- **Python 3.12+** (tested with Python 3.12.3)
- **python-telegram-bot** (22.4+) - Only external dependency, requires network access
- **SQLite** - Built into Python, no separate install needed

### No Build Process Required
- This is a pure Python application
- No compilation, bundling, or build steps
- No package.json, requirements.txt, or complex dependency management
- Simply install python-telegram-bot and run

## Troubleshooting

### Common Issues and Solutions
- **Syntax Error in admin_handlers.py**: Fixed - extra closing parenthesis was removed
- **Import failures**: 
  - For telegram package: Ensure venv is activated and python-telegram-bot is installed
  - For core modules: Can test instructions.py, states.py, db.py without external dependencies
- **pip install timeouts**: Network/firewall issue, document as "pip install -- fails due to network limitations"
- **Database errors**: orders.db auto-creates with proper schema, check file permissions
- **Network errors on startup**: Normal behavior without valid BOT_TOKEN
- **PTB UserWarnings**: Expected warnings about ConversationHandler settings, safe to ignore

### Validation Before Making Changes
1. Test core modules without external dependencies:
   - `python3 -c "from instructions import INSTRUCTIONS; print('OK')"`
   - `python3 -c "import db; print('OK')"`
2. Run py_compile to catch syntax errors: `python3 -m py_compile modified_file.py`
3. Test full imports if telegram package is available: `python3 -c "import client_bot"`
4. Test database operations if modifying db.py
5. Verify instruction loading if changing instructions.py

### Working with Ukrainian Content
- Bot UI and instructions are in Ukrainian
- Bank names: ПУМБ, А-Банк, Фрі Банк, Акорд Банк, etc.
- Stage descriptions use banking terminology (реєстрація = registration, перев'язка = change)
- Example workflows involve Дія app screenshots and bank card details

## Environment Configuration

### Required Environment Variables (Optional)
```bash
export BOT_TOKEN="your-token"      # Default: demo token provided
export ADMIN_ID="user-id"          # Default: 7797088374
export ADMIN_GROUP_ID="group-id"   # Default: -4930176305  
export ADMIN_IDS="id1,id2,id3"     # Default: uses ADMIN_ID
export DB_FILE="orders.db"         # Default: orders.db
export LOCK_FILE="bot.lock"        # Default: bot.lock
```

### File-based Configuration
- **Admin users**: Listed in `admins.txt` (one user ID per line)
- **Message templates**: Stored in `templates.json` with Ukrainian text
- **Bank workflows**: Defined in `instructions.py` INSTRUCTIONS dictionary

## Development Workflow

### Making Code Changes
1. Always activate virtual environment: `source venv/bin/activate`
2. Make minimal changes to target files
3. Test imports: `python3 -c "import client_bot"`
4. Validate syntax: `python3 -m py_compile modified_file.py`
5. Test bot startup (expect network error without valid token)
6. Check database initialization if relevant

### Key Patterns in Codebase
- **Async/await**: All Telegram handlers use async functions
- **SQLite**: Direct cursor operations, no ORM
- **State management**: Uses telegram.ext ConversationHandler
- **Logging**: Uses Python logging module with INFO level
- **Error handling**: Network errors expected and handled gracefully

### Files You Can Modify Safely
- `instructions.py` - Bank configurations and workflows
- `templates.json` - Manager message templates  
- `admins.txt` - Administrative user list
- Handler files in `handlers/` - Bot command logic
- `states.py` - Conversation state definitions

### Files to Modify Carefully
- `client_bot.py` - Main application setup, test thoroughly
- `db.py` - Database schema changes require migration consideration
- `.gitignore` - Ensure venv/ and __pycache__/ remain excluded
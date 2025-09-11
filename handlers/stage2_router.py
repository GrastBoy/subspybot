from telegram.ext import CallbackQueryHandler, ConversationHandler, MessageHandler, filters
from handlers.stage2_handlers import (
    user_stage2_callback,
    manager_stage2_callback,
    manager_enter_data,
    manager_enter_code
)
from states import STAGE2_MANAGER_WAIT_DATA, STAGE2_MANAGER_WAIT_CODE

def build_stage2_handlers():
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(user_stage2_callback, pattern=r"^s2_"),
            CallbackQueryHandler(manager_stage2_callback, pattern=r"^mgr_"),
        ],
        states={
            STAGE2_MANAGER_WAIT_DATA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, manager_enter_data)
            ],
            STAGE2_MANAGER_WAIT_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, manager_enter_code)
            ],
        },
        fallbacks=[],
        per_chat=True,
        per_message=False,
        name="stage2_conv"
    )
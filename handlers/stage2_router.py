from telegram.ext import CallbackQueryHandler, ConversationHandler, MessageHandler, filters

from db import ADMIN_GROUP_ID
from handlers.stage2_handlers import (
    manager_enter_code,
    manager_enter_data,
    manager_enter_message,
    manager_stage2_callback,
    stage2_group_text,
    user_stage2_callback,
)
from states import STAGE2_MANAGER_WAIT_CODE, STAGE2_MANAGER_WAIT_DATA, STAGE2_MANAGER_WAIT_MSG


def build_stage2_handlers():
    """
    ConversationHandler для Stage2:
      - user callbacks (s2_...)
      - manager callbacks (mgr_...)
      - manager text input (дані/код/повідомлення)
      - admin group free text: auto code + auto messages to user
    """
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(user_stage2_callback, pattern=r"^s2_"),
            CallbackQueryHandler(manager_stage2_callback, pattern=r"^mgr_"),
            MessageHandler(filters.Chat(ADMIN_GROUP_ID) & filters.TEXT & ~filters.COMMAND, stage2_group_text),
        ],
        states={
            STAGE2_MANAGER_WAIT_DATA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, manager_enter_data)
            ],
            STAGE2_MANAGER_WAIT_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, manager_enter_code)
            ],
            STAGE2_MANAGER_WAIT_MSG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, manager_enter_message)
            ],
        },
        fallbacks=[],
        per_chat=True,
        per_message=False,
        name="stage2_conv"
    )

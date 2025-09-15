from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters
)
from db import conn, logger, BOT_TOKEN, LOCK_FILE
from states import COOPERATION_INPUT, REJECT_REASON, MANAGER_MESSAGE
from handlers.menu_handlers import start, main_menu_handler, age_confirm_handler
from handlers.photo_handlers import handle_photos, handle_admin_action, reject_reason_handler, manager_message_handler
from handlers.cooperation_handlers import cooperation_start_handler, cooperation_receive, cancel
from handlers.admin_handlers import (
    history, add_group, del_group, list_groups, show_queue,
    finish_order, finish_all_orders, orders_stats,
    add_admin, remove_admin, list_admins, stage2debug, admin_help,
    tmpl_list, tmpl_set, tmpl_del, banks, bank_show, bank_hide,
    bank_management_cmd, add_bank_cmd, add_bank_group_cmd, add_admin_group_cmd,
    data_history_cmd, order_form_cmd, list_forms_cmd, active_orders_cmd
)
from handlers.status_handler import status
from handlers.stage2_router import build_stage2_handlers
from handlers.stage2_handlers import stage2_user_text, set_current_order_cmd

def main():
    if BOT_TOKEN in ("", "CHANGE_ME_PLEASE"):
        print("ERROR: BOT_TOKEN не встановлено. Задайте змінну середовища BOT_TOKEN.")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(main_menu_handler, pattern="^(menu_banks|menu_info|back_to_main|type_register|type_change|bank_.*)$"))
    app.add_handler(CallbackQueryHandler(age_confirm_handler, pattern="^age_confirm_.*$"))

    # Фото етап (Stage1)
    app.add_handler(MessageHandler(filters.PHOTO, handle_photos))
    app.add_handler(CallbackQueryHandler(handle_admin_action, pattern="^(approve|reject)_.*$"))
    
    # Data validation callbacks
    from handlers.data_validation import handle_data_reuse_confirmation
    app.add_handler(CallbackQueryHandler(handle_data_reuse_confirmation, pattern="^(confirm_reuse|cancel_reuse)_.*$"))
    
    # Multi-order management callbacks
    from handlers.multi_order_management import handle_active_order_management
    app.add_handler(CallbackQueryHandler(handle_active_order_management, 
                                       pattern="^(refresh_active_orders|switch_primary|add_active_order|remove_active_order|set_primary_|add_order_|remove_order_).*$"))

    # Stage2 handlers (user + manager flows)
    app.add_handler(build_stage2_handlers())

    # Cooperation & moderation conversations
    conv_general = ConversationHandler(
        entry_points=[CallbackQueryHandler(cooperation_start_handler, pattern="menu_coop")],
        states={
            COOPERATION_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, cooperation_receive)],
            REJECT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, reject_reason_handler)],
            MANAGER_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, manager_message_handler)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_chat=True
    )
    app.add_handler(conv_general)

    # Bank management conversation
    from handlers.bank_management import (
        banks_management_menu, list_banks_handler, add_bank_handler, 
        bank_name_input_handler, bank_settings_handler, instructions_menu_handler,
        groups_menu_handler, list_groups_handler, cancel_conversation,
        BANK_NAME_INPUT, BANK_SETTINGS_INPUT
    )
    conv_bank_management = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_bank_handler, pattern="^banks_add$")],
        states={
            BANK_NAME_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bank_name_input_handler)],
            BANK_SETTINGS_INPUT: [CallbackQueryHandler(bank_settings_handler, pattern="^(bank_reg_|bank_change_|bank_save).*$")]
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
        per_chat=True
    )
    app.add_handler(conv_bank_management)
    
    # Bank management callback handlers
    app.add_handler(CallbackQueryHandler(banks_management_menu, pattern="^banks_menu$"))
    app.add_handler(CallbackQueryHandler(list_banks_handler, pattern="^banks_list$"))
    app.add_handler(CallbackQueryHandler(instructions_menu_handler, pattern="^instructions_menu$"))
    app.add_handler(CallbackQueryHandler(groups_menu_handler, pattern="^groups_menu$"))
    app.add_handler(CallbackQueryHandler(list_groups_handler, pattern="^groups_list$"))

    # Admin/user commands
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("addgroup", add_group))
    app.add_handler(CommandHandler("delgroup", del_group))
    app.add_handler(CommandHandler("groups", list_groups))
    app.add_handler(CommandHandler("queue", show_queue))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("finish_order", finish_order))
    app.add_handler(CommandHandler("finish_all_orders", finish_all_orders))
    app.add_handler(CommandHandler("orders_stats", orders_stats))
    app.add_handler(CommandHandler("add_admin", add_admin))
    app.add_handler(CommandHandler("remove_admin", remove_admin))
    app.add_handler(CommandHandler("list_admins", list_admins))
    app.add_handler(CommandHandler("stage2debug", stage2debug))
    app.add_handler(CommandHandler("help", admin_help))

    # Templates management (admin)
    app.add_handler(CommandHandler("tmpl_list", tmpl_list))
    app.add_handler(CommandHandler("tmpl_set", tmpl_set))
    app.add_handler(CommandHandler("tmpl_del", tmpl_del))

    # Group quick switch current order: /o <id>
    app.add_handler(CommandHandler("order", set_current_order_cmd))

    # User -> managers autobridge (private text)
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, stage2_user_text))

    # Banks visibility (admin)
    app.add_handler(CommandHandler("banks", banks))
    app.add_handler(CommandHandler("bank_show", bank_show))
    app.add_handler(CommandHandler("bank_hide", bank_hide))
    
    # Enhanced bank and group management
    app.add_handler(CommandHandler("bank_management", bank_management_cmd))
    app.add_handler(CommandHandler("add_bank", add_bank_cmd))
    app.add_handler(CommandHandler("add_bank_group", add_bank_group_cmd))
    app.add_handler(CommandHandler("add_admin_group", add_admin_group_cmd))
    app.add_handler(CommandHandler("data_history", data_history_cmd))
    app.add_handler(CommandHandler("order_form", order_form_cmd))
    app.add_handler(CommandHandler("list_forms", list_forms_cmd))
    app.add_handler(CommandHandler("active_orders", active_orders_cmd))

    logger.info("Бот запущений...")
    app.run_polling()

if __name__ == "__main__":
    try:
        main()
    finally:
        try:
            import os
            if os.path.exists(LOCK_FILE):
                os.remove(LOCK_FILE)
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

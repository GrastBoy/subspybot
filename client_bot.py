from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from db import BOT_TOKEN, LOCK_FILE, conn, logger
from handlers.admin_handlers import (
    active_orders_cmd,
    add_admin,
    add_admin_group_cmd,
    add_bank_cmd,
    add_bank_group_cmd,
    add_group,
    admin_help,
    bank_hide,
    bank_management_cmd,
    bank_show,
    banks,
    data_history_cmd,
    del_group,
    finish_all_orders,
    finish_order,
    history,
    list_admins,
    list_forms_cmd,
    list_groups,
    order_form_cmd,
    orders_stats,
    remove_admin,
    show_queue,
    stage2debug,
    tmpl_del,
    tmpl_list,
    tmpl_set,
)
from handlers.cooperation_handlers import cancel, cooperation_receive, cooperation_start_handler
from handlers.menu_handlers import age_confirm_handler, main_menu_handler, start
from handlers.order_handlers import myorders
from handlers.photo_handlers import handle_admin_action, handle_photos, manager_message_handler, reject_reason_handler
from handlers.stage2_handlers import set_current_order_cmd, stage2_user_text
from handlers.stage2_router import build_stage2_handlers
from handlers.status_handler import status
from states import COOPERATION_INPUT, MANAGER_MESSAGE, REJECT_REASON

from dotenv import load_dotenv
import os

load_dotenv()


def main():
    if BOT_TOKEN in (""):
        print("ERROR: BOT_TOKEN не встановлено. Задайте змінну середовища BOT_TOKEN.")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(main_menu_handler, pattern="^(menu_banks|menu_info|back_to_main|type_register|type_change|bank_[^_]+_(register|change))$"))
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
        BANK_NAME_INPUT,
        BANK_PRICE_INPUT,
        BANK_DESCRIPTION_INPUT,
        BANK_SETTINGS_INPUT,
        add_admin_group_handler,
        add_bank_group_handler,
        add_bank_handler,
        bank_name_input_handler,
        bank_price_input_handler,
        bank_description_input_handler,
        bank_settings_handler,
        banks_management_menu,
        cancel_conversation,
        confirm_delete_bank_handler,
        confirm_delete_group_handler,
        delete_bank_handler,
        delete_group_handler,
        edit_bank_handler,
        edit_bank_settings_handler,
        final_delete_bank_handler,
        final_delete_group_handler,
        form_templates_menu_handler,
        form_templates_list_handler,
        form_templates_create_handler,
        form_templates_edit_handler,
        form_templates_delete_handler,
        create_template_handler,
        edit_template_handler_specific,
        delete_template_handler_specific,
        confirm_delete_template_handler,
        migrate_from_file_handler,
        confirm_migrate_from_file_handler,
        groups_menu_handler,
        instructions_menu_handler,
        list_banks_handler,
        list_groups_handler,
        select_bank_for_group_handler,
        toggle_bank_setting_handler,
    )
    conv_bank_management = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_bank_handler, pattern="^banks_add$")],
        states={
            BANK_NAME_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bank_name_input_handler)],
            BANK_PRICE_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bank_price_input_handler),
                CallbackQueryHandler(bank_price_input_handler, pattern="^skip_price$")
            ],
            BANK_DESCRIPTION_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bank_description_input_handler),
                CallbackQueryHandler(bank_description_input_handler, pattern="^skip_description$")
            ],
            BANK_SETTINGS_INPUT: [CallbackQueryHandler(bank_settings_handler, pattern="^(bank_reg_|bank_change_|bank_save).*$")]
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
        per_chat=True
    )
    app.add_handler(conv_bank_management)

    # Bank management callback handlers
    app.add_handler(CallbackQueryHandler(banks_management_menu, pattern="^banks_menu$"))
    app.add_handler(CallbackQueryHandler(list_banks_handler, pattern="^banks_list$"))
    app.add_handler(CallbackQueryHandler(edit_bank_handler, pattern="^banks_edit$"))
    app.add_handler(CallbackQueryHandler(delete_bank_handler, pattern="^banks_delete$"))
    app.add_handler(CallbackQueryHandler(edit_bank_settings_handler, pattern="^edit_bank_.*$"))
    app.add_handler(CallbackQueryHandler(toggle_bank_setting_handler, pattern="^(toggle_(active|register|change)|edit_(price|description))_.*$"))
    app.add_handler(CallbackQueryHandler(confirm_delete_bank_handler, pattern="^delete_bank_.*$"))
    app.add_handler(CallbackQueryHandler(final_delete_bank_handler, pattern="^confirm_delete_bank_.*$"))
    app.add_handler(CallbackQueryHandler(instructions_menu_handler, pattern="^instructions_menu$"))
    app.add_handler(CallbackQueryHandler(groups_menu_handler, pattern="^groups_menu$"))
    app.add_handler(CallbackQueryHandler(list_groups_handler, pattern="^groups_list$"))
    app.add_handler(CallbackQueryHandler(add_bank_group_handler, pattern="^groups_add_bank$"))
    app.add_handler(CallbackQueryHandler(add_admin_group_handler, pattern="^groups_add_admin$"))
    app.add_handler(CallbackQueryHandler(select_bank_for_group_handler, pattern="^select_bank_for_group_.*$"))
    app.add_handler(CallbackQueryHandler(delete_group_handler, pattern="^groups_delete$"))
    app.add_handler(CallbackQueryHandler(confirm_delete_group_handler, pattern="^delete_group_.*$"))
    app.add_handler(CallbackQueryHandler(final_delete_group_handler, pattern="^confirm_delete_group_.*$"))

    # Form template management
    app.add_handler(CallbackQueryHandler(form_templates_menu_handler, pattern="^form_templates_menu$"))
    app.add_handler(CallbackQueryHandler(form_templates_list_handler, pattern="^form_templates_list$"))
    app.add_handler(CallbackQueryHandler(form_templates_create_handler, pattern="^form_templates_create$"))
    app.add_handler(CallbackQueryHandler(form_templates_edit_handler, pattern="^form_templates_edit$"))
    app.add_handler(CallbackQueryHandler(form_templates_delete_handler, pattern="^form_templates_delete$"))
    
    # Specific template operations
    app.add_handler(CallbackQueryHandler(create_template_handler, pattern="^create_template_.*$"))
    app.add_handler(CallbackQueryHandler(edit_template_handler_specific, pattern="^edit_template_.*$"))
    app.add_handler(CallbackQueryHandler(delete_template_handler_specific, pattern="^delete_template_.*$"))
    app.add_handler(CallbackQueryHandler(confirm_delete_template_handler, pattern="^confirm_delete_template_.*$"))
    app.add_handler(CallbackQueryHandler(migrate_from_file_handler, pattern="^migrate_from_file$"))
    app.add_handler(CallbackQueryHandler(confirm_migrate_from_file_handler, pattern="^confirm_migrate_from_file$"))

    # Instruction management conversation
    from handlers.instruction_management import (
        INSTR_ACTION_SELECT,
        INSTR_BANK_SELECT,
        INSTR_TEXT_INPUT,
        cancel_instruction_conversation,
        instruction_action_select_handler,
        instruction_add_another_handler,
        instruction_bank_select_handler,
        instruction_text_input_handler,
        instructions_add_handler,
        instructions_list_handler,
        manage_bank_instructions_cmd,
        sync_instructions_to_file_cmd,
        migrate_instructions_from_file_cmd,
    )
    conv_instruction_management = ConversationHandler(
        entry_points=[CallbackQueryHandler(instructions_add_handler, pattern="^instructions_add$")],
        states={
            INSTR_BANK_SELECT: [CallbackQueryHandler(instruction_bank_select_handler, pattern="^instr_bank_.*$")],
            INSTR_ACTION_SELECT: [CallbackQueryHandler(instruction_action_select_handler, pattern="^instr_action_.*$")],
            INSTR_TEXT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, instruction_text_input_handler)]
        },
        fallbacks=[CommandHandler("cancel", cancel_instruction_conversation)],
        per_chat=True
    )
    app.add_handler(conv_instruction_management)

    # Instruction management callbacks
    app.add_handler(CallbackQueryHandler(instructions_list_handler, pattern="^instructions_list$"))
    app.add_handler(CallbackQueryHandler(instruction_add_another_handler, pattern="^instr_add_another$"))

    # Add sync callback handler
    async def sync_callback_handler(update, context):
        query = update.callback_query
        await query.answer()
        if query.data == "sync_to_file":
            await sync_instructions_to_file_cmd(update, context)

    app.add_handler(CallbackQueryHandler(sync_callback_handler, pattern="^sync_to_file$"))

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
    app.add_handler(CommandHandler("o", set_current_order_cmd))  # Short alias for order command
    app.add_handler(CommandHandler("myorders", myorders))

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
    app.add_handler(CommandHandler("manage_instructions", manage_bank_instructions_cmd))
    app.add_handler(CommandHandler("sync_instructions", sync_instructions_to_file_cmd))
    app.add_handler(CommandHandler("migrate_instructions", migrate_instructions_from_file_cmd))

    # Unified Admin Interface
    from handlers.admin_interface import admin_interface_callback, admin_interface_menu
    app.add_handler(CommandHandler("admin", admin_interface_menu))
    app.add_handler(CallbackQueryHandler(admin_interface_callback,
                                        pattern="^(admin_|back_to_admin|groups_menu|groups_|orders_|admins_|stats_|system_|templates_).*$"))

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

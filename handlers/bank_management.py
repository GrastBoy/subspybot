"""
Bank and instruction management handlers for admin users
"""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from db import (
    add_bank,
    add_manager_group,
    delete_bank,
    get_bank_groups,
    get_banks,
    is_admin,
    log_action,
    update_bank,
)

logger = logging.getLogger(__name__)

# Conversation states
BANK_NAME_INPUT, BANK_SETTINGS_INPUT = range(2)
INSTRUCTION_BANK_SELECT, INSTRUCTION_ACTION_SELECT, INSTRUCTION_STEP_INPUT = range(3, 6)
GROUP_BANK_SELECT, GROUP_NAME_INPUT = range(6, 8)

async def banks_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main banks management menu"""
    if not is_admin(update.effective_user.id):
        # Handle both message and callback query contexts
        if update.callback_query:
            return await update.callback_query.answer("⛔ Немає доступу", show_alert=True)
        else:
            return await update.message.reply_text("⛔ Немає доступу")

    keyboard = [
        [InlineKeyboardButton("📋 Список банків", callback_data="banks_list")],
        [InlineKeyboardButton("➕ Додати банк", callback_data="banks_add")],
        [InlineKeyboardButton("✏️ Редагувати банк", callback_data="banks_edit")],
        [InlineKeyboardButton("🗑️ Видалити банк", callback_data="banks_delete")],
        [InlineKeyboardButton("📝 Управління інструкціями", callback_data="instructions_menu")],
        [InlineKeyboardButton("👥 Управління групами", callback_data="groups_menu")]
    ]

    text = "🏦 <b>Управління банками</b>\n\nОберіть дію:"
    
    # Handle both message and callback query contexts
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    elif update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    else:
        # Fallback for edge cases where neither callback_query nor message is available
        logger.warning("banks_management_menu called without valid update.callback_query or update.message")
        return

async def list_banks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all banks with their settings"""
    if not is_admin(update.effective_user.id):
        return await update.callback_query.answer("⛔ Немає доступу")

    query = update.callback_query
    await query.answer()

    banks = get_banks()

    if not banks:
        text = "📋 <b>Список банків</b>\n\n❌ Немає зареєстрованих банків"
    else:
        text = "📋 <b>Список банків</b>\n\n"
        for name, is_active, register_enabled, change_enabled in banks:
            status = "✅ Активний" if is_active else "❌ Неактивний"
            register_status = "✅" if register_enabled else "❌"
            change_status = "✅" if change_enabled else "❌"

            text += f"🏦 <b>{name}</b>\n"
            text += f"   Статус: {status}\n"
            text += f"   Реєстрація: {register_status} | Перев'язка: {change_status}\n\n"

    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="banks_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def add_bank_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start add bank conversation"""
    if not is_admin(update.effective_user.id):
        return await update.callback_query.answer("⛔ Немає доступу")

    query = update.callback_query
    await query.answer()

    text = "➕ <b>Додати новий банк</b>\n\nВведіть назву банку:"
    await query.edit_message_text(text, parse_mode='HTML')
    return BANK_NAME_INPUT

async def bank_name_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bank name input"""
    bank_name = update.message.text.strip()

    if not bank_name:
        await update.message.reply_text("❌ Назва банку не може бути пустою. Спробуйте ще раз:")
        return BANK_NAME_INPUT

    # Check if bank already exists
    existing_banks = [name for name, _, _, _ in get_banks()]
    if bank_name in existing_banks:
        await update.message.reply_text(f"❌ Банк '{bank_name}' вже існує. Введіть іншу назву:")
        return BANK_NAME_INPUT

    context.user_data['new_bank_name'] = bank_name

    keyboard = [
        [InlineKeyboardButton("✅ Реєстрація", callback_data="bank_reg_yes"),
         InlineKeyboardButton("❌ Реєстрація", callback_data="bank_reg_no")],
        [InlineKeyboardButton("✅ Перев'язка", callback_data="bank_change_yes"),
         InlineKeyboardButton("❌ Перев'язка", callback_data="bank_change_no")],
        [InlineKeyboardButton("💾 Зберегти", callback_data="bank_save")]
    ]

    text = f"🏦 <b>Налаштування банку '{bank_name}'</b>\n\n"
    text += "Реєстрація: ✅ Увімкнена\n"
    text += "Перев'язка: ✅ Увімкнена\n\n"
    text += "Змініть налаштування або збережіть банк:"

    context.user_data['bank_register_enabled'] = True
    context.user_data['bank_change_enabled'] = True

    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    return BANK_SETTINGS_INPUT

async def bank_settings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bank settings selection"""
    query = update.callback_query
    await query.answer()

    data = query.data
    bank_name = context.user_data.get('new_bank_name', 'Unknown')

    if data == "bank_reg_yes":
        context.user_data['bank_register_enabled'] = True
    elif data == "bank_reg_no":
        context.user_data['bank_register_enabled'] = False
    elif data == "bank_change_yes":
        context.user_data['bank_change_enabled'] = True
    elif data == "bank_change_no":
        context.user_data['bank_change_enabled'] = False
    elif data == "bank_save":
        # Save the bank
        register_enabled = context.user_data.get('bank_register_enabled', True)
        change_enabled = context.user_data.get('bank_change_enabled', True)

        if add_bank(bank_name, register_enabled, change_enabled):
            text = f"✅ Банк '{bank_name}' успішно додано!"
            log_action(0, f"admin_{update.effective_user.id}", "add_bank", bank_name)
        else:
            text = f"❌ Помилка при додаванні банку '{bank_name}'"

        await query.edit_message_text(text)

        # Clear user data
        context.user_data.pop('new_bank_name', None)
        context.user_data.pop('bank_register_enabled', None)
        context.user_data.pop('bank_change_enabled', None)

        return ConversationHandler.END

    # Update display
    register_status = "✅ Увімкнена" if context.user_data.get('bank_register_enabled', True) else "❌ Вимкнена"
    change_status = "✅ Увімкнена" if context.user_data.get('bank_change_enabled', True) else "❌ Вимкнена"

    text = f"🏦 <b>Налаштування банку '{bank_name}'</b>\n\n"
    text += f"Реєстрація: {register_status}\n"
    text += f"Перев'язка: {change_status}\n\n"
    text += "Змініть налаштування або збережіть банк:"

    keyboard = [
        [InlineKeyboardButton("✅ Реєстрація", callback_data="bank_reg_yes"),
         InlineKeyboardButton("❌ Реєстрація", callback_data="bank_reg_no")],
        [InlineKeyboardButton("✅ Перев'язка", callback_data="bank_change_yes"),
         InlineKeyboardButton("❌ Перев'язка", callback_data="bank_change_no")],
        [InlineKeyboardButton("💾 Зберегти", callback_data="bank_save")]
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    return BANK_SETTINGS_INPUT

async def instructions_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Instructions management menu"""
    if not is_admin(update.effective_user.id):
        return await update.callback_query.answer("⛔ Немає доступу")

    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("📋 Переглянути інструкції", callback_data="instructions_list")],
        [InlineKeyboardButton("➕ Додати інструкцію", callback_data="instructions_add")],
        [InlineKeyboardButton("🔄 Синхронізувати в файл", callback_data="sync_to_file")],
        [InlineKeyboardButton("🔙 Назад", callback_data="banks_menu")]
    ]

    text = "📝 <b>Управління інструкціями</b>\n\n"
    text += "Тут ви можете керувати інструкціями для всіх банків:\n"
    text += "• Переглянути існуючі інструкції\n"
    text += "• Додати нові кроки\n"
    text += "• Синхронізувати зміни в файл\n\n"
    text += "Оберіть дію:"

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def groups_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Groups management menu"""
    if not is_admin(update.effective_user.id):
        return await update.callback_query.answer("⛔ Немає доступу")

    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("📋 Список груп", callback_data="groups_list")],
        [InlineKeyboardButton("➕ Додати групу для банку", callback_data="groups_add_bank")],
        [InlineKeyboardButton("👨‍💼 Додати адмін групу", callback_data="groups_add_admin")],
        [InlineKeyboardButton("🗑️ Видалити групу", callback_data="groups_delete")],
        [InlineKeyboardButton("🔙 Назад", callback_data="banks_menu")]
    ]

    text = "👥 <b>Управління групами</b>\n\nОберіть дію:"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def list_groups_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all manager groups"""
    if not is_admin(update.effective_user.id):
        return await update.callback_query.answer("⛔ Немає доступу")

    query = update.callback_query
    await query.answer()

    groups = get_bank_groups()

    if not groups:
        text = "📋 <b>Список груп</b>\n\n❌ Немає зареєстрованих груп"
    else:
        text = "📋 <b>Список груп</b>\n\n"
        for group_id, name, bank, is_admin_group in groups:
            group_type = "👨‍💼 Адмін група" if is_admin_group else f"🏦 Група банку '{bank}'"
            text += f"ID: {group_id}\n"
            text += f"Назва: {name}\n"
            text += f"Тип: {group_type}\n\n"

    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="groups_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def edit_bank_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Edit bank handler - show list of banks to edit"""
    if not is_admin(update.effective_user.id):
        return await update.callback_query.answer("⛔ Немає доступу")

    query = update.callback_query
    await query.answer()

    banks = get_banks()

    if not banks:
        text = "✏️ <b>Редагувати банк</b>\n\n❌ Немає зареєстрованих банків для редагування"
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="banks_menu")]]
    else:
        text = "✏️ <b>Редагувати банк</b>\n\nОберіть банк для редагування:"
        keyboard = []
        for name, is_active, register_enabled, change_enabled in banks:
            status = "✅" if is_active else "❌"
            keyboard.append([InlineKeyboardButton(f"{status} {name}", callback_data=f"edit_bank_{name}")])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="banks_menu")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def delete_bank_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete bank handler - show list of banks to delete"""
    if not is_admin(update.effective_user.id):
        return await update.callback_query.answer("⛔ Немає доступу")

    query = update.callback_query
    await query.answer()

    banks = get_banks()

    if not banks:
        text = "🗑️ <b>Видалити банк</b>\n\n❌ Немає зареєстрованих банків для видалення"
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="banks_menu")]]
    else:
        text = "🗑️ <b>Видалити банк</b>\n\n⚠️ <b>Увага!</b> Видалення банку призведе до видалення всіх його інструкцій.\n\nОберіть банк для видалення:"
        keyboard = []
        for name, is_active, register_enabled, change_enabled in banks:
            keyboard.append([InlineKeyboardButton(f"🗑️ {name}", callback_data=f"delete_bank_{name}")])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="banks_menu")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def edit_bank_settings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle editing specific bank settings"""
    if not is_admin(update.effective_user.id):
        return await update.callback_query.answer("⛔ Немає доступу")

    query = update.callback_query
    await query.answer()

    # Extract bank name from callback data
    bank_name = query.data.replace("edit_bank_", "")
    
    # Get current bank settings
    banks = get_banks()
    bank_data = None
    for name, is_active, register_enabled, change_enabled in banks:
        if name == bank_name:
            bank_data = (is_active, register_enabled, change_enabled)
            break
    
    if not bank_data:
        await query.edit_message_text("❌ Банк не знайдено")
        return

    is_active, register_enabled, change_enabled = bank_data
    
    active_status = "✅ Активний" if is_active else "❌ Неактивний"
    register_status = "✅ Увімкнена" if register_enabled else "❌ Вимкнена"
    change_status = "✅ Увімкнена" if change_enabled else "❌ Вимкнена"

    text = f"✏️ <b>Редагування банку '{bank_name}'</b>\n\n"
    text += f"Статус: {active_status}\n"
    text += f"Реєстрація: {register_status}\n"
    text += f"Перев'язка: {change_status}\n\n"
    text += "Що бажаєте змінити?"

    keyboard = [
        [InlineKeyboardButton("🔄 Статус банку", callback_data=f"toggle_active_{bank_name}")],
        [InlineKeyboardButton("📝 Реєстрація", callback_data=f"toggle_register_{bank_name}")],
        [InlineKeyboardButton("🔗 Перев'язка", callback_data=f"toggle_change_{bank_name}")],
        [InlineKeyboardButton("🔙 Назад", callback_data="banks_edit")]
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def toggle_bank_setting_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle toggling bank settings"""
    if not is_admin(update.effective_user.id):
        return await update.callback_query.answer("⛔ Немає доступу")

    query = update.callback_query
    await query.answer()

    data = query.data
    
    if data.startswith("toggle_active_"):
        bank_name = data.replace("toggle_active_", "")
        # Get current status
        banks = get_banks()
        current_active = None
        for name, is_active, _, _ in banks:
            if name == bank_name:
                current_active = is_active
                break
        
        if current_active is not None:
            new_active = not current_active
            if update_bank(bank_name, is_active=new_active):
                status = "активовано" if new_active else "деактивовано"
                await query.edit_message_text(f"✅ Банк '{bank_name}' {status}")
                log_action(0, f"admin_{update.effective_user.id}", "toggle_bank_active", f"{bank_name}:{status}")
            else:
                await query.edit_message_text(f"❌ Помилка при зміні статусу банку '{bank_name}'")
    
    elif data.startswith("toggle_register_"):
        bank_name = data.replace("toggle_register_", "")
        # Get current status
        banks = get_banks()
        current_register = None
        for name, _, register_enabled, _ in banks:
            if name == bank_name:
                current_register = register_enabled
                break
        
        if current_register is not None:
            new_register = not current_register
            if update_bank(bank_name, register_enabled=new_register):
                status = "увімкнено" if new_register else "вимкнено"
                await query.edit_message_text(f"✅ Реєстрацію для банку '{bank_name}' {status}")
                log_action(0, f"admin_{update.effective_user.id}", "toggle_bank_register", f"{bank_name}:{status}")
            else:
                await query.edit_message_text(f"❌ Помилка при зміні налаштувань реєстрації для банку '{bank_name}'")
    
    elif data.startswith("toggle_change_"):
        bank_name = data.replace("toggle_change_", "")
        # Get current status
        banks = get_banks()
        current_change = None
        for name, _, _, change_enabled in banks:
            if name == bank_name:
                current_change = change_enabled
                break
        
        if current_change is not None:
            new_change = not current_change
            if update_bank(bank_name, change_enabled=new_change):
                status = "увімкнено" if new_change else "вимкнено"
                await query.edit_message_text(f"✅ Перев'язку для банку '{bank_name}' {status}")
                log_action(0, f"admin_{update.effective_user.id}", "toggle_bank_change", f"{bank_name}:{status}")
            else:
                await query.edit_message_text(f"❌ Помилка при зміні налаштувань перев'язки для банку '{bank_name}'")

async def confirm_delete_bank_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bank deletion confirmation"""
    if not is_admin(update.effective_user.id):
        return await update.callback_query.answer("⛔ Немає доступу")

    query = update.callback_query
    await query.answer()

    # Extract bank name from callback data
    bank_name = query.data.replace("delete_bank_", "")

    text = f"🗑️ <b>Видалення банку</b>\n\n"
    text += f"⚠️ <b>Увага!</b> Ви дійсно хочете видалити банк '<b>{bank_name}</b>'?\n\n"
    text += "Це призведе до:\n"
    text += "• Видалення банку з системи\n"
    text += "• Видалення всіх інструкцій банку\n"
    text += "• Неможливості відновлення\n\n"
    text += "Підтвердіть дію:"

    keyboard = [
        [InlineKeyboardButton("✅ Так, видалити", callback_data=f"confirm_delete_bank_{bank_name}")],
        [InlineKeyboardButton("❌ Скасувати", callback_data="banks_delete")]
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def final_delete_bank_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Final bank deletion handler"""
    if not is_admin(update.effective_user.id):
        return await update.callback_query.answer("⛔ Немає доступу")

    query = update.callback_query
    await query.answer()

    # Extract bank name from callback data
    bank_name = query.data.replace("confirm_delete_bank_", "")

    if delete_bank(bank_name):
        text = f"✅ Банк '{bank_name}' та всі його інструкції успішно видалено"
        log_action(0, f"admin_{update.effective_user.id}", "delete_bank", bank_name)
    else:
        text = f"❌ Помилка при видаленні банку '{bank_name}'"

    await query.edit_message_text(text)

async def add_bank_group_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add bank group handler - show list of banks to select"""
    if not is_admin(update.effective_user.id):
        return await update.callback_query.answer("⛔ Немає доступу")

    query = update.callback_query
    await query.answer()

    banks = get_banks()

    if not banks:
        text = "➕ <b>Додати групу для банку</b>\n\n❌ Немає зареєстрованих банків.\nСпочатку додайте банк."
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="groups_menu")]]
    else:
        text = "➕ <b>Додати групу для банку</b>\n\nОберіть банк для якого додати групу:"
        keyboard = []
        for name, is_active, _, _ in banks:
            if is_active:  # Only show active banks
                keyboard.append([InlineKeyboardButton(f"🏦 {name}", callback_data=f"select_bank_for_group_{name}")])
        
        if not any(is_active for _, is_active, _, _ in banks):
            text = "➕ <b>Додати групу для банку</b>\n\n❌ Немає активних банків.\nСпочатку активуйте хоча б один банк."
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="groups_menu")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def add_admin_group_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add admin group handler"""
    if not is_admin(update.effective_user.id):
        return await update.callback_query.answer("⛔ Немає доступу")

    query = update.callback_query
    await query.answer()

    text = "👨‍💼 <b>Додати адмін групу</b>\n\n"
    text += "Для додавання адмін групи використовуйте команду:\n"
    text += "<code>/add_admin_group &lt;group_id&gt; &lt;назва&gt;</code>\n\n"
    text += "<b>Приклад:</b>\n"
    text += "<code>/add_admin_group -1001234567890 Адміністрація</code>\n\n"
    text += "Де:\n"
    text += "• <code>group_id</code> - ID групи (отримати можна переслав повідомлення з групи в @userinfobot)\n"
    text += "• <code>назва</code> - читабельна назва групи"

    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="groups_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def select_bank_for_group_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bank selection for group creation"""
    if not is_admin(update.effective_user.id):
        return await update.callback_query.answer("⛔ Немає доступу")

    query = update.callback_query
    await query.answer()

    # Extract bank name from callback data
    bank_name = query.data.replace("select_bank_for_group_", "")

    text = f"➕ <b>Додати групу для банку '{bank_name}'</b>\n\n"
    text += "Для додавання групи банку використовуйте команду:\n"
    text += f"<code>/add_bank_group &lt;group_id&gt; {bank_name} &lt;назва&gt;</code>\n\n"
    text += "<b>Приклад:</b>\n"
    text += f"<code>/add_bank_group -1001234567890 {bank_name} Менеджери {bank_name}</code>\n\n"
    text += "Де:\n"
    text += "• <code>group_id</code> - ID групи (отримати можна переслав повідомлення з групи в @userinfobot)\n"
    text += f"• <code>{bank_name}</code> - назва банку (вже вказана)\n"
    text += "• <code>назва</code> - читабельна назва групи"

    keyboard = [
        [InlineKeyboardButton("🔙 Обрати інший банк", callback_data="groups_add_bank")],
        [InlineKeyboardButton("🏠 До групи", callback_data="groups_menu")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def delete_group_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete group handler - show list of groups to delete"""
    if not is_admin(update.effective_user.id):
        return await update.callback_query.answer("⛔ Немає доступу")

    query = update.callback_query
    await query.answer()

    # Import here to avoid circular imports
    from db import cursor

    # Get all groups
    cursor.execute("SELECT group_id, name, bank, is_admin_group FROM manager_groups ORDER BY name ASC")
    groups = cursor.fetchall()

    if not groups:
        text = "🗑️ <b>Видалити групу</b>\n\n❌ Немає зареєстрованих груп для видалення"
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="groups_menu")]]
    else:
        text = "🗑️ <b>Видалити групу</b>\n\n⚠️ <b>Увага!</b> Видалення групи призведе до втрати всіх налаштувань.\n\nОберіть групу для видалення:"
        keyboard = []
        for group_id, name, bank, is_admin_group in groups:
            if is_admin_group:
                display_name = f"👨‍💼 {name} (ID: {group_id})"
            else:
                display_name = f"🏦 {name} - {bank} (ID: {group_id})"
            keyboard.append([InlineKeyboardButton(f"🗑️ {display_name}", callback_data=f"delete_group_{group_id}")])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="groups_menu")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def confirm_delete_group_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle group deletion confirmation"""
    if not is_admin(update.effective_user.id):
        return await update.callback_query.answer("⛔ Немає доступу")

    query = update.callback_query
    await query.answer()

    # Extract group ID from callback data
    group_id = int(query.data.replace("delete_group_", ""))

    # Import here to avoid circular imports
    from db import cursor

    # Get group info
    cursor.execute("SELECT name, bank, is_admin_group FROM manager_groups WHERE group_id=?", (group_id,))
    group_info = cursor.fetchone()

    if not group_info:
        await query.edit_message_text("❌ Групу не знайдено")
        return

    name, bank, is_admin_group = group_info
    
    if is_admin_group:
        group_type = "адмін групу"
        group_desc = f"'{name}'"
    else:
        group_type = "групу банку"
        group_desc = f"'{name}' для банку '{bank}'"

    text = f"🗑️ <b>Видалення групи</b>\n\n"
    text += f"⚠️ <b>Увага!</b> Ви дійсно хочете видалити {group_type} {group_desc}?\n\n"
    text += f"ID групи: <code>{group_id}</code>\n\n"
    text += "Це призведе до:\n"
    text += "• Видалення групи з системи\n"
    text += "• Втрати всіх налаштувань групи\n"
    text += "• Неможливості відновлення\n\n"
    text += "Підтвердіть дію:"

    keyboard = [
        [InlineKeyboardButton("✅ Так, видалити", callback_data=f"confirm_delete_group_{group_id}")],
        [InlineKeyboardButton("❌ Скасувати", callback_data="groups_delete")]
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def final_delete_group_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Final group deletion handler"""
    if not is_admin(update.effective_user.id):
        return await update.callback_query.answer("⛔ Немає доступу")

    query = update.callback_query
    await query.answer()

    # Extract group ID from callback data
    group_id = int(query.data.replace("confirm_delete_group_", ""))

    # Import here to avoid circular imports
    from db import conn, cursor

    # Get group info before deletion
    cursor.execute("SELECT name, bank, is_admin_group FROM manager_groups WHERE group_id=?", (group_id,))
    group_info = cursor.fetchone()

    if not group_info:
        await query.edit_message_text("❌ Групу не знайдено")
        return

    name, bank, is_admin_group = group_info

    try:
        cursor.execute("DELETE FROM manager_groups WHERE group_id=?", (group_id,))
        conn.commit()
        
        if is_admin_group:
            text = f"✅ Адмін групу '{name}' (ID: {group_id}) успішно видалено"
            log_action(0, f"admin_{update.effective_user.id}", "delete_admin_group", f"{group_id}:{name}")
        else:
            text = f"✅ Групу '{name}' для банку '{bank}' (ID: {group_id}) успішно видалено"
            log_action(0, f"admin_{update.effective_user.id}", "delete_bank_group", f"{bank}:{group_id}:{name}")
            
    except Exception as e:
        text = f"❌ Помилка при видаленні групи: {e}"

    await query.edit_message_text(text)

# Utility function for handling conversation cancellation
async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel any active conversation"""
    await update.message.reply_text("❌ Операцію скасовано")
    return ConversationHandler.END

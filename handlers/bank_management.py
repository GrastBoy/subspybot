"""
Bank and instruction management handlers for admin users
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from db import (
    is_admin, add_bank, update_bank, delete_bank, get_banks,
    add_bank_instruction, get_bank_instructions, 
    add_manager_group, get_bank_groups,
    log_action, cursor, conn
)
import json
import logging

logger = logging.getLogger(__name__)

# Conversation states
BANK_NAME_INPUT, BANK_SETTINGS_INPUT = range(2)
INSTRUCTION_BANK_SELECT, INSTRUCTION_ACTION_SELECT, INSTRUCTION_STEP_INPUT = range(3, 6)
GROUP_BANK_SELECT, GROUP_NAME_INPUT = range(6, 8)

async def banks_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main banks management menu"""
    if not is_admin(update.effective_user.id):
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
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

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

# Utility function for handling conversation cancellation
async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel any active conversation"""
    await update.message.reply_text("❌ Операцію скасовано")
    return ConversationHandler.END
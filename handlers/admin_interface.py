"""
Unified Admin Interface - Complete management of all admin functions through interface
This replaces scattered command-line functions with a unified menu-driven interface
"""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from db import is_admin

logger = logging.getLogger(__name__)

# Conversation states for unified admin interface
ADMIN_MAIN_MENU = range(1)

async def admin_interface_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main admin interface menu - unified entry point for all admin functions"""
    user_id = update.effective_user.id if update.effective_user else 0

    if not is_admin(user_id):
        await update.message.reply_text("⛔ Немає доступу до адміністративних функцій")
        return

    keyboard = [
        [InlineKeyboardButton("🏦 Управління банками", callback_data="admin_banks")],
        [InlineKeyboardButton("👥 Управління групами", callback_data="admin_groups")],
        [InlineKeyboardButton("📋 Управління замовленнями", callback_data="admin_orders")],
        [InlineKeyboardButton("👨‍💼 Управління адмінами", callback_data="admin_admins")],
        [InlineKeyboardButton("📊 Статистика та звіти", callback_data="admin_stats")],
        [InlineKeyboardButton("⚙️ Системні налаштування", callback_data="admin_system")],
        [InlineKeyboardButton("📝 Шаблони та інструкції", callback_data="admin_templates")],
        [InlineKeyboardButton("❓ Довідка", callback_data="admin_help")]
    ]

    text = (
        "🔧 <b>Адміністративна панель</b>\n\n"
        "Оберіть розділ для управління:\n\n"
        "🏦 <b>Банки</b> - додавання, редагування, налаштування банків\n"
        "👥 <b>Групи</b> - менеджерські групи та адмін групи\n"
        "📋 <b>Замовлення</b> - активні замовлення, черга, історія\n"
        "👨‍💼 <b>Адміни</b> - додавання/видалення адміністраторів\n"
        "📊 <b>Статистика</b> - звіти, аналітика, метрики\n"
        "⚙️ <b>Система</b> - загальні налаштування\n"
        "📝 <b>Шаблони</b> - повідомлення та інструкції\n"
    )

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def admin_interface_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin interface callbacks"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id if update.effective_user else 0
    if not is_admin(user_id):
        await query.edit_message_text("⛔ Немає доступу")
        return

    data = query.data

    if data == "admin_banks":
        # Redirect to bank management
        from handlers.bank_management import banks_management_menu
        await banks_management_menu(update, context)

    elif data == "admin_groups":
        await admin_groups_menu(query)

    elif data == "admin_orders":
        await admin_orders_menu(query)

    elif data == "admin_admins":
        await admin_admins_menu(query)

    elif data == "admin_stats":
        await admin_stats_menu(query)

    elif data == "admin_system":
        await admin_system_menu(query)

    elif data == "admin_templates":
        await admin_templates_menu(query)

    elif data == "admin_help":
        await admin_help_menu(query)

    elif data == "back_to_admin":
        await show_admin_main_menu(query)

async def show_admin_main_menu(query):
    """Show main admin menu"""
    keyboard = [
        [InlineKeyboardButton("🏦 Управління банками", callback_data="admin_banks")],
        [InlineKeyboardButton("👥 Управління групами", callback_data="admin_groups")],
        [InlineKeyboardButton("📋 Управління замовленнями", callback_data="admin_orders")],
        [InlineKeyboardButton("👨‍💼 Управління адмінами", callback_data="admin_admins")],
        [InlineKeyboardButton("📊 Статистика та звіти", callback_data="admin_stats")],
        [InlineKeyboardButton("⚙️ Системні налаштування", callback_data="admin_system")],
        [InlineKeyboardButton("📝 Шаблони та інструкції", callback_data="admin_templates")],
        [InlineKeyboardButton("❓ Довідка", callback_data="admin_help")]
    ]

    text = (
        "🔧 <b>Адміністративна панель</b>\n\n"
        "Оберіть розділ для управління:"
    )

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def admin_groups_menu(query):
    """Groups management menu"""
    keyboard = [
        [InlineKeyboardButton("📋 Список груп", callback_data="groups_list")],
        [InlineKeyboardButton("➕ Додати групу банку", callback_data="groups_add_bank")],
        [InlineKeyboardButton("👨‍💼 Додати адмін групу", callback_data="groups_add_admin")],
        [InlineKeyboardButton("🗑️ Видалити групу", callback_data="groups_delete")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin")]
    ]

    text = "👥 <b>Управління групами</b>\n\nОберіть дію:"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def admin_orders_menu(query):
    """Orders management menu"""
    keyboard = [
        [InlineKeyboardButton("📋 Активні замовлення", callback_data="orders_active")],
        [InlineKeyboardButton("⏳ Черга замовлень", callback_data="orders_queue")],
        [InlineKeyboardButton("📊 Історія замовлень", callback_data="orders_history")],
        [InlineKeyboardButton("✅ Завершити замовлення", callback_data="orders_finish")],
        [InlineKeyboardButton("📈 Статистика замовлень", callback_data="orders_stats")],
        [InlineKeyboardButton("📄 Форми замовлень", callback_data="orders_forms")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin")]
    ]

    text = "📋 <b>Управління замовленнями</b>\n\nОберіть дію:"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def admin_admins_menu(query):
    """Admins management menu"""
    keyboard = [
        [InlineKeyboardButton("📋 Список адмінів", callback_data="admins_list")],
        [InlineKeyboardButton("➕ Додати адміна", callback_data="admins_add")],
        [InlineKeyboardButton("➖ Видалити адміна", callback_data="admins_remove")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin")]
    ]

    text = "👨‍💼 <b>Управління адміністраторами</b>\n\nОберіть дію:"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def admin_stats_menu(query):
    """Statistics menu"""
    keyboard = [
        [InlineKeyboardButton("📊 Загальна статистика", callback_data="stats_general")],
        [InlineKeyboardButton("🏦 Статистика банків", callback_data="stats_banks")],
        [InlineKeyboardButton("👥 Статистика груп", callback_data="stats_groups")],
        [InlineKeyboardButton("📈 Аналітика за період", callback_data="stats_period")],
        [InlineKeyboardButton("📋 Експорт даних", callback_data="stats_export")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin")]
    ]

    text = "📊 <b>Статистика та звіти</b>\n\nОберіть тип звіту:"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def admin_system_menu(query):
    """System settings menu"""
    keyboard = [
        [InlineKeyboardButton("🔧 Загальні налаштування", callback_data="system_general")],
        [InlineKeyboardButton("🏦 Видимість банків", callback_data="system_bank_visibility")],
        [InlineKeyboardButton("🔄 Очистка бази даних", callback_data="system_cleanup")],
        [InlineKeyboardButton("📤 Резервне копіювання", callback_data="system_backup")],
        [InlineKeyboardButton("🔄 Перезапуск бота", callback_data="system_restart")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin")]
    ]

    text = "⚙️ <b>Системні налаштування</b>\n\nОберіть дію:"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def admin_templates_menu(query):
    """Templates and instructions menu"""
    keyboard = [
        [InlineKeyboardButton("📝 Шаблони повідомлень", callback_data="templates_messages")],
        [InlineKeyboardButton("📋 Інструкції банків", callback_data="templates_instructions")],
        [InlineKeyboardButton("🔄 Синхронізація", callback_data="templates_sync")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin")]
    ]

    text = "📝 <b>Шаблони та інструкції</b>\n\nОберіть тип для управління:"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def admin_help_menu(query):
    """Admin help menu"""
    text = (
        "❓ <b>Довідка по адміністративних функціях</b>\n\n"

        "🏦 <b>Управління банками:</b>\n"
        "• Додавання нових банків\n"
        "• Налаштування реєстрації/перев'язки\n"
        "• Управління інструкціями\n\n"

        "👥 <b>Управління групами:</b>\n"
        "• Додавання груп для банків\n"
        "• Додавання адмін груп\n"
        "• Видалення груп\n\n"

        "📋 <b>Управління замовленнями:</b>\n"
        "• Перегляд активних замовлень\n"
        "• Завершення замовлень\n"
        "• Статистика\n\n"

        "👨‍💼 <b>Управління адмінами:</b>\n"
        "• Додавання/видалення адміністраторів\n"
        "• Перегляд списку адмінів\n\n"

        "📊 <b>Статистика:</b>\n"
        "• Загальна статистика бота\n"
        "• Детальна аналітика\n\n"

        "⚙️ <b>Система:</b>\n"
        "• Налаштування видимості банків\n"
        "• Резервне копіювання\n"
        "• Очистка даних\n\n"

        "📝 <b>Шаблони:</b>\n"
        "• Управління повідомленнями\n"
        "• Синхронізація інструкцій\n"
    )

    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

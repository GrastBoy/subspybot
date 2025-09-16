"""
Unified Admin Interface - Complete management of all admin functions through interface
This replaces scattered command-line functions with a unified menu-driven interface
"""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from db import is_admin, cursor, conn, list_admins_db, add_admin_db, remove_admin_db
from handlers.templates_store import list_templates

logger = logging.getLogger(__name__)

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

    # Groups management callbacks
    elif data == "groups_menu":
        # Handle groups_menu callback from bank_management
        await admin_groups_menu(query)
    elif data == "groups_list":
        await groups_list(query)
    elif data == "groups_add_bank":
        await groups_add_bank(query)
    elif data == "groups_add_admin":
        await groups_add_admin(query)
    elif data == "groups_delete":
        await groups_delete(query)

    # Orders management callbacks
    elif data == "orders_active":
        await orders_active(query)
    elif data == "orders_queue":
        await orders_queue(query)
    elif data == "orders_history":
        await orders_history(query)
    elif data == "orders_finish":
        await orders_finish(query)
    elif data == "orders_stats":
        await orders_stats(query)
    elif data == "orders_forms":
        await orders_forms(query)

    # Admins management callbacks
    elif data == "admins_list":
        await admins_list(query)
    elif data == "admins_add":
        await admins_add(query)
    elif data == "admins_remove":
        await admins_remove(query)

    # Stats callbacks
    elif data == "stats_general":
        await stats_general(query)
    elif data == "stats_banks":
        await stats_banks(query)
    elif data == "stats_groups":
        await stats_groups(query)
    elif data == "stats_period":
        await stats_period(query)
    elif data == "stats_export":
        await stats_export(query)

    # System callbacks
    elif data == "system_general":
        await system_general(query)
    elif data == "system_bank_visibility":
        await system_bank_visibility(query)
    elif data == "system_cleanup":
        await system_cleanup(query)
    elif data == "system_backup":
        await system_backup(query)
    elif data == "system_restart":
        await system_restart(query)

    # Templates callbacks
    elif data == "templates_list":
        await templates_list(query)
    elif data == "templates_set":
        await templates_set(query)
    elif data == "templates_del":
        await templates_del(query)
    elif data == "templates_messages":
        await templates_messages(query)
    elif data == "templates_instructions":
        await templates_instructions(query)
    elif data == "templates_sync":
        await templates_sync(query)

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

# ============= Groups Management Handlers =============

async def groups_list(query):
    """Show list of all groups"""
    try:
        cursor.execute("""
            SELECT group_id, name, bank, is_admin_group, busy 
            FROM manager_groups 
            ORDER BY is_admin_group DESC, bank, name
        """)
        groups = cursor.fetchall()
        
        if not groups:
            text = "👥 <b>Список груп</b>\n\n❌ Груп не знайдено"
        else:
            text = "👥 <b>Список груп</b>\n\n"
            admin_groups = [g for g in groups if g[3]]  # is_admin_group
            bank_groups = [g for g in groups if not g[3]]
            
            if admin_groups:
                text += "🛡️ <b>Адміністративні групи:</b>\n"
                for group_id, name, _, _, busy in admin_groups:
                    status = "🔴 Зайнята" if busy else "🟢 Вільна"
                    text += f"• {name} (ID: {group_id}) - {status}\n"
                text += "\n"
            
            if bank_groups:
                text += "🏦 <b>Групи банків:</b>\n"
                current_bank = None
                for group_id, name, bank, _, busy in bank_groups:
                    if bank != current_bank:
                        current_bank = bank
                        text += f"\n<b>{bank or 'Не вказано'}:</b>\n"
                    status = "🔴 Зайнята" if busy else "🟢 Вільна"
                    text += f"• {name} (ID: {group_id}) - {status}\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_groups")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        
    except Exception as e:
        logger.error("groups_list failed: %s", e)
        await query.edit_message_text(
            "❌ Помилка при отриманні списку груп",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_groups")]])
        )

async def groups_add_bank(query):
    """Show instructions for adding bank group"""
    text = (
        "➕ <b>Додавання групи банку</b>\n\n"
        "Для додавання нової групи банку використовуйте команду:\n\n"
        "<code>/addgroup &lt;group_id&gt; &lt;назва&gt;</code>\n\n"
        "<b>Приклад:</b>\n"
        "<code>/addgroup -1234567890 \"Менеджери ПриватБанку\"</code>\n\n"
        "Після додавання групи, вам потрібно буде призначити їй банк через налаштування банків."
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_groups")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def groups_add_admin(query):
    """Show instructions for adding admin group"""
    text = (
        "👨‍💼 <b>Додавання адміністративної групи</b>\n\n"
        "Для додавання нової адміністративної групи використовуйте команду:\n\n"
        "<code>/add_admin_group &lt;group_id&gt; \"&lt;назва&gt;\"</code>\n\n"
        "<b>Приклад:</b>\n"
        "<code>/add_admin_group -1234567890 \"Головні адміністратори\"</code>\n\n"
        "Адміністративні групи можуть бачити всі замовлення незалежно від банку."
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_groups")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def groups_delete(query):
    """Show instructions for deleting groups"""
    try:
        cursor.execute("SELECT group_id, name, bank, is_admin_group FROM manager_groups ORDER BY name")
        groups = cursor.fetchall()
        
        if not groups:
            text = "🗑️ <b>Видалення груп</b>\n\n❌ Груп не знайдено"
        else:
            text = (
                "🗑️ <b>Видалення груп</b>\n\n"
                "Для видалення групи використовуйте команду:\n"
                "<code>/delgroup &lt;group_id&gt;</code>\n\n"
                "<b>Доступні групи:</b>\n"
            )
            for group_id, name, bank, is_admin in groups:
                group_type = "👨‍💼 Адмін" if is_admin else f"🏦 {bank or 'Банк не вказано'}"
                text += f"• {name} (ID: <code>{group_id}</code>) - {group_type}\n"
    
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_groups")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        
    except Exception as e:
        logger.error("groups_delete failed: %s", e)
        await query.edit_message_text(
            "❌ Помилка при отриманні списку груп",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_groups")]])
        )

# ============= Orders Management Handlers =============

async def orders_active(query):
    """Show active orders"""
    try:
        cursor.execute("""
            SELECT o.id, o.user_id, o.username, o.bank, o.action, o.status, o.group_id, o.created_at,
                   mg.name as group_name
            FROM orders o
            LEFT JOIN manager_groups mg ON o.group_id = mg.group_id
            WHERE o.status != 'Завершено'
            ORDER BY o.created_at DESC
            LIMIT 20
        """)
        orders = cursor.fetchall()
        
        if not orders:
            text = "📋 <b>Активні замовлення</b>\n\n✅ Немає активних замовлень"
        else:
            text = f"📋 <b>Активні замовлення</b> ({len(orders)})\n\n"
            for order_id, user_id, username, bank, action, status, group_id, created_at, group_name in orders:
                text += f"🆔 <b>#{order_id}</b>\n"
                text += f"👤 @{username} (ID: {user_id})\n"
                text += f"🏦 {bank} - {action}\n"
                text += f"📍 {status}\n"
                if group_name:
                    text += f"👥 {group_name}\n"
                text += f"⏰ {created_at}\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_orders")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        
    except Exception as e:
        logger.error("orders_active failed: %s", e)
        await query.edit_message_text(
            "❌ Помилка при отриманні списку активних замовлень",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_orders")]])
        )

async def orders_queue(query):
    """Show order queue"""
    try:
        cursor.execute("SELECT id, user_id, username, bank, action, created_at FROM queue ORDER BY created_at")
        queue_items = cursor.fetchall()
        
        if not queue_items:
            text = "⏳ <b>Черга замовлень</b>\n\n✅ Черга порожня"
        else:
            text = f"⏳ <b>Черга замовлень</b> ({len(queue_items)})\n\n"
            for i, (queue_id, user_id, username, bank, action, created_at) in enumerate(queue_items, 1):
                text += f"{i}. 👤 @{username} (ID: {user_id})\n"
                text += f"   🏦 {bank} - {action}\n"
                text += f"   ⏰ {created_at}\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_orders")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        
    except Exception as e:
        logger.error("orders_queue failed: %s", e)
        await query.edit_message_text(
            "❌ Помилка при отриманні черги замовлень",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_orders")]])
        )

async def orders_history(query):
    """Show recent completed orders"""
    try:
        cursor.execute("""
            SELECT id, user_id, username, bank, action, status, created_at
            FROM orders
            WHERE status = 'Завершено'
            ORDER BY created_at DESC
            LIMIT 15
        """)
        orders = cursor.fetchall()
        
        if not orders:
            text = "📊 <b>Історія замовлень</b>\n\n❌ Завершених замовлень не знайдено"
        else:
            text = f"📊 <b>Історія замовлень</b> (останні {len(orders)})\n\n"
            for order_id, user_id, username, bank, action, status, created_at in orders:
                text += f"🆔 <b>#{order_id}</b> - ✅ {status}\n"
                text += f"👤 @{username}\n"
                text += f"🏦 {bank} - {action}\n"
                text += f"⏰ {created_at}\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_orders")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        
    except Exception as e:
        logger.error("orders_history failed: %s", e)
        await query.edit_message_text(
            "❌ Помилка при отриманні історії замовлень",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_orders")]])
        )

async def orders_finish(query):
    """Show instructions for finishing orders"""
    text = (
        "✅ <b>Завершення замовлень</b>\n\n"
        "Для завершення замовлення використовуйте команду:\n\n"
        "<code>/finish_order &lt;order_id&gt;</code>\n\n"
        "<b>Приклад:</b>\n"
        "<code>/finish_order 123</code>\n\n"
        "Для завершення всіх замовлень користувача:\n"
        "<code>/finish_all_orders &lt;user_id&gt;</code>\n\n"
        "Перегляньте активні замовлення, щоб дізнатися ID."
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_orders")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def orders_stats(query):
    """Show order statistics"""
    try:
        # Get various order counts
        cursor.execute("SELECT COUNT(*) FROM orders")
        total_orders = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'Завершено'")
        completed_orders = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM orders WHERE status != 'Завершено'")
        active_orders = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM queue")
        queue_count = cursor.fetchone()[0]
        
        # Get stats by bank
        cursor.execute("""
            SELECT bank, COUNT(*) as total, 
                   SUM(CASE WHEN status = 'Завершено' THEN 1 ELSE 0 END) as completed
            FROM orders 
            GROUP BY bank 
            ORDER BY total DESC
            LIMIT 10
        """)
        bank_stats = cursor.fetchall()
        
        text = (
            "📈 <b>Статистика замовлень</b>\n\n"
            f"📊 <b>Загальна статистика:</b>\n"
            f"• Всього замовлень: {total_orders}\n"
            f"• Завершено: {completed_orders}\n"
            f"• Активних: {active_orders}\n"
            f"• У черзі: {queue_count}\n\n"
        )
        
        if bank_stats:
            text += "🏦 <b>Статистика по банках:</b>\n"
            for bank, total, completed in bank_stats:
                completion_rate = (completed / total * 100) if total > 0 else 0
                text += f"• {bank}: {total} ({completed} завершено, {completion_rate:.1f}%)\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_orders")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        
    except Exception as e:
        logger.error("orders_stats failed: %s", e)
        await query.edit_message_text(
            "❌ Помилка при отриманні статистики замовлень",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_orders")]])
        )

async def orders_forms(query):
    """Show information about order forms"""
    try:
        cursor.execute("SELECT COUNT(*) FROM order_forms")
        forms_count = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT o.bank, COUNT(of.id) as forms_count
            FROM order_forms of
            JOIN orders o ON of.order_id = o.id
            GROUP BY o.bank
            ORDER BY forms_count DESC
            LIMIT 10
        """)
        forms_by_bank = cursor.fetchall()
        
        text = (
            "📄 <b>Форми замовлень</b>\n\n"
            f"📊 Всього форм: {forms_count}\n\n"
            "Для перегляду форм використовуйте команди:\n"
            "• <code>/order_forms list</code> - список форм\n"
            "• <code>/order_forms &lt;order_id&gt;</code> - форма конкретного замовлення\n\n"
        )
        
        if forms_by_bank:
            text += "🏦 <b>Форми по банках:</b>\n"
            for bank, count in forms_by_bank:
                text += f"• {bank}: {count} форм\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_orders")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        
    except Exception as e:
        logger.error("orders_forms failed: %s", e)
        await query.edit_message_text(
            "❌ Помилка при отриманні інформації про форми",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_orders")]])
        )

# ============= Admin Management Handlers =============

async def admins_list(query):
    """Show list of administrators"""
    try:
        admins = list_admins_db()
        
        if not admins:
            text = "👨‍💼 <b>Список адміністраторів</b>\n\n❌ Адміністраторів не знайдено"
        else:
            text = f"👨‍💼 <b>Список адміністраторів</b> ({len(admins)})\n\n"
            for admin_id in admins:
                text += f"• ID: <code>{admin_id}</code>\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_admins")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        
    except Exception as e:
        logger.error("admins_list failed: %s", e)
        await query.edit_message_text(
            "❌ Помилка при отриманні списку адміністраторів",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_admins")]])
        )

async def admins_add(query):
    """Show instructions for adding admin"""
    text = (
        "➕ <b>Додавання адміністратора</b>\n\n"
        "Для додавання нового адміністратора використовуйте команду:\n\n"
        "<code>/add_admin &lt;user_id&gt;</code>\n\n"
        "<b>Приклад:</b>\n"
        "<code>/add_admin 123456789</code>\n\n"
        "💡 <b>Як дізнатися User ID:</b>\n"
        "1. Попросіть користувача написати боту /start\n"
        "2. User ID відобразиться в логах\n"
        "3. Або використайте @userinfobot"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_admins")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def admins_remove(query):
    """Show instructions for removing admin"""
    try:
        admins = list_admins_db()
        
        text = (
            "➖ <b>Видалення адміністратора</b>\n\n"
            "Для видалення адміністратора використовуйте команду:\n\n"
            "<code>/remove_admin &lt;user_id&gt;</code>\n\n"
            "<b>Приклад:</b>\n"
            "<code>/remove_admin 123456789</code>\n\n"
        )
        
        if admins:
            text += "<b>Поточні адміністратори:</b>\n"
            for admin_id in admins:
                text += f"• <code>{admin_id}</code>\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_admins")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        
    except Exception as e:
        logger.error("admins_remove failed: %s", e)
        await query.edit_message_text(
            "❌ Помилка при отриманні списку адміністраторів",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_admins")]])
        )

# ============= Statistics Handlers =============

async def stats_general(query):
    """Show general statistics"""
    try:
        # Get general statistics
        cursor.execute("SELECT COUNT(*) FROM orders")
        total_orders = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'Завершено'")
        completed_orders = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM orders WHERE status != 'Завершено'")
        active_orders = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM queue")
        queue_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM manager_groups")
        groups_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM manager_groups WHERE is_admin_group = 1")
        admin_groups_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM banks")
        banks_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM admins")
        admins_count = cursor.fetchone()[0]
        
        completion_rate = (completed_orders / total_orders * 100) if total_orders > 0 else 0
        
        text = (
            "📊 <b>Загальна статистика</b>\n\n"
            "📋 <b>Замовлення:</b>\n"
            f"• Всього: {total_orders}\n"
            f"• Завершено: {completed_orders} ({completion_rate:.1f}%)\n"
            f"• Активних: {active_orders}\n"
            f"• У черзі: {queue_count}\n\n"
            "🏦 <b>Система:</b>\n"
            f"• Банків: {banks_count}\n"
            f"• Груп: {groups_count} (адмін: {admin_groups_count})\n"
            f"• Адмінів: {admins_count}\n"
        )
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_stats")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        
    except Exception as e:
        logger.error("stats_general failed: %s", e)
        await query.edit_message_text(
            "❌ Помилка при отриманні загальної статистики",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_stats")]])
        )

async def stats_banks(query):
    """Show bank statistics"""
    try:
        cursor.execute("""
            SELECT bank, 
                   COUNT(*) as total_orders,
                   SUM(CASE WHEN status = 'Завершено' THEN 1 ELSE 0 END) as completed_orders,
                   SUM(CASE WHEN status != 'Завершено' THEN 1 ELSE 0 END) as active_orders
            FROM orders 
            GROUP BY bank 
            ORDER BY total_orders DESC
        """)
        bank_stats = cursor.fetchall()
        
        if not bank_stats:
            text = "🏦 <b>Статистика банків</b>\n\n❌ Даних не знайдено"
        else:
            text = "🏦 <b>Статистика банків</b>\n\n"
            for bank, total, completed, active in bank_stats:
                completion_rate = (completed / total * 100) if total > 0 else 0
                text += f"<b>{bank}</b>\n"
                text += f"• Всього: {total}\n"
                text += f"• Завершено: {completed} ({completion_rate:.1f}%)\n"
                text += f"• Активних: {active}\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_stats")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        
    except Exception as e:
        logger.error("stats_banks failed: %s", e)
        await query.edit_message_text(
            "❌ Помилка при отриманні статистики банків",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_stats")]])
        )

async def stats_groups(query):
    """Show group statistics"""
    try:
        cursor.execute("""
            SELECT mg.name, mg.bank, mg.is_admin_group, mg.busy,
                   COUNT(o.id) as total_orders
            FROM manager_groups mg
            LEFT JOIN orders o ON mg.group_id = o.group_id
            GROUP BY mg.group_id, mg.name
            ORDER BY total_orders DESC
        """)
        group_stats = cursor.fetchall()
        
        if not group_stats:
            text = "👥 <b>Статистика груп</b>\n\n❌ Груп не знайдено"
        else:
            text = "👥 <b>Статистика груп</b>\n\n"
            for name, bank, is_admin, busy, orders_count in group_stats:
                status = "🔴 Зайнята" if busy else "🟢 Вільна"
                group_type = "👨‍💼 Адмін" if is_admin else f"🏦 {bank or 'Не вказано'}"
                text += f"<b>{name}</b> - {group_type}\n"
                text += f"• Статус: {status}\n"
                text += f"• Замовлень оброблено: {orders_count}\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_stats")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        
    except Exception as e:
        logger.error("stats_groups failed: %s", e)
        await query.edit_message_text(
            "❌ Помилка при отриманні статистики груп",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_stats")]])
        )

async def stats_period(query):
    """Show period statistics"""
    text = (
        "📈 <b>Аналітика за період</b>\n\n"
        "🚧 <b>В розробці</b>\n\n"
        "Функція буде доступна в наступних оновленнях.\n"
        "Планується додати:\n"
        "• Статистика за день/тиждень/місяць\n"
        "• Графіки активності\n"
        "• Аналіз ефективності\n"
        "• Експорт звітів"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_stats")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def stats_export(query):
    """Show export options"""
    text = (
        "📋 <b>Експорт даних</b>\n\n"
        "🚧 <b>В розробці</b>\n\n"
        "Функція буде доступна в наступних оновленнях.\n"
        "Планується додати експорт:\n"
        "• CSV файли з замовленнями\n"
        "• Звіти в Excel\n"
        "• JSON дампи даних\n"
        "• Автоматичні звіти на email"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_stats")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

# ============= System Management Handlers =============

async def system_general(query):
    """Show general system settings"""
    text = (
        "🔧 <b>Загальні налаштування</b>\n\n"
        "🚧 <b>В розробці</b>\n\n"
        "Функція буде доступна в наступних оновленнях.\n"
        "Планується додати:\n"
        "• Налаштування часових зон\n"
        "• Обмеження швидкості\n"
        "• Налаштування логування\n"
        "• Конфігурація повідомлень"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_system")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def system_bank_visibility(query):
    """Show bank visibility settings"""
    try:
        cursor.execute("SELECT bank, show_register, show_change FROM bank_visibility ORDER BY bank")
        visibility_settings = cursor.fetchall()
        
        cursor.execute("SELECT name FROM banks ORDER BY name")
        all_banks = [row[0] for row in cursor.fetchall()]
        
        text = "🏦 <b>Видимість банків</b>\n\n"
        
        if visibility_settings:
            text += "<b>Поточні налаштування:</b>\n"
            for bank, show_register, show_change in visibility_settings:
                register_status = "✅" if show_register else "❌"
                change_status = "✅" if show_change else "❌"
                text += f"<b>{bank}</b>\n"
                text += f"• Реєстрація: {register_status}\n"
                text += f"• Перев'язка: {change_status}\n\n"
        
        text += (
            "<b>Команди для управління:</b>\n"
            "• <code>/bank_show &lt;bank&gt;</code> - показати банк\n"
            "• <code>/bank_hide &lt;bank&gt;</code> - приховати банк\n\n"
            "<b>Доступні банки:</b>\n"
        )
        
        for bank in all_banks:
            text += f"• {bank}\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_system")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        
    except Exception as e:
        logger.error("system_bank_visibility failed: %s", e)
        await query.edit_message_text(
            "❌ Помилка при отриманні налаштувань видимості",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_system")]])
        )

async def system_cleanup(query):
    """Show cleanup options"""
    text = (
        "🔄 <b>Очистка бази даних</b>\n\n"
        "⚠️ <b>Увага!</b> Операції очистки незворотні!\n\n"
        "🚧 <b>В розробці</b>\n\n"
        "Планується додати:\n"
        "• Очистка старих замовлень\n"
        "• Видалення неактивних користувачів\n"
        "• Архівування даних\n"
        "• Оптимізація бази даних\n\n"
        "💡 Поки що використовуйте прямі SQL команди"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_system")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def system_backup(query):
    """Show backup options"""
    text = (
        "📤 <b>Резервне копіювання</b>\n\n"
        "🚧 <b>В розробці</b>\n\n"
        "Планується додати:\n"
        "• Автоматичне створення бекапів\n"
        "• Збереження в хмару\n"
        "• Відновлення з бекапу\n"
        "• Планування бекапів\n\n"
        "💡 Поки що створюйте копії файлу orders.db вручну"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_system")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def system_restart(query):
    """Show restart options"""
    text = (
        "🔄 <b>Перезапуск бота</b>\n\n"
        "⚠️ <b>Увага!</b> Перезапуск бота припинить всі поточні операції!\n\n"
        "🚧 <b>В розробці</b>\n\n"
        "Планується додати:\n"
        "• Безпечний перезапуск\n"
        "• Збереження стану\n"
        "• Автоматичне відновлення\n"
        "• Планований перезапуск\n\n"
        "💡 Поки що перезапускайте бота вручну через systemctl або процес-менеджер"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_system")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

# ============= Templates Management Handlers =============

async def templates_list(query):
    """Show list of templates"""
    try:
        templates = list_templates()
        
        if not templates:
            text = "📝 <b>Список шаблонів</b>\n\n❌ Шаблонів не знайдено"
        else:
            text = f"📝 <b>Список шаблонів</b> ({len(templates)})\n\n"
            for key, value in templates.items():
                preview = value[:50] + "..." if len(value) > 50 else value
                text += f"<b>{key}</b>\n{preview}\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_templates")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        
    except Exception as e:
        logger.error("templates_list failed: %s", e)
        await query.edit_message_text(
            "❌ Помилка при отриманні списку шаблонів",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_templates")]])
        )

async def templates_set(query):
    """Show instructions for setting templates"""
    text = (
        "➕ <b>Встановлення шаблону</b>\n\n"
        "Для створення або редагування шаблону використовуйте команду:\n\n"
        "<code>/tmpl_set &lt;ключ&gt; &lt;текст&gt;</code>\n\n"
        "<b>Приклад:</b>\n"
        "<code>/tmpl_set welcome Вітаємо в нашому боті!</code>\n\n"
        "<b>Стандартні ключі:</b>\n"
        "• <code>hello</code> - привітання\n"
        "• <code>wait_code</code> - очікування коду\n"
        "• <code>after_code</code> - після отримання коду\n\n"
        "💡 Ви можете створювати власні ключі для різних повідомлень"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_templates")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def templates_del(query):
    """Show instructions for deleting templates"""
    try:
        templates = list_templates()
        
        text = (
            "🗑️ <b>Видалення шаблону</b>\n\n"
            "Для видалення шаблону використовуйте команду:\n\n"
            "<code>/tmpl_del &lt;ключ&gt;</code>\n\n"
            "<b>Приклад:</b>\n"
            "<code>/tmpl_del old_template</code>\n\n"
        )
        
        if templates:
            text += "<b>Доступні шаблони:</b>\n"
            for key in templates.keys():
                text += f"• <code>{key}</code>\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_templates")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        
    except Exception as e:
        logger.error("templates_del failed: %s", e)
        await query.edit_message_text(
            "❌ Помилка при отриманні списку шаблонів",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_templates")]])
        )

async def templates_messages(query):
    """Handle templates messages submenu"""
    await templates_list(query)

async def templates_instructions(query):
    """Show bank instructions management"""
    text = (
        "📋 <b>Інструкції банків</b>\n\n"
        "🚧 <b>В розробці</b>\n\n"
        "Планується додати:\n"
        "• Редагування інструкцій через інтерфейс\n"
        "• Предперегляд інструкцій\n"
        "• Управління зображеннями\n"
        "• Версійність інструкцій\n\n"
        "💡 Поки що використовуйте команди /bank_management"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_templates")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def templates_sync(query):
    """Show sync options"""
    text = (
        "🔄 <b>Синхронізація</b>\n\n"
        "Для синхронізації інструкцій з файлом використовуйте команду:\n\n"
        "<code>/sync_to_file</code>\n\n"
        "Ця команда оновить файл instructions.py з поточними інструкціями з бази даних.\n\n"
        "⚠️ <b>Увага:</b> Це перезапише поточний файл instructions.py"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_templates")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

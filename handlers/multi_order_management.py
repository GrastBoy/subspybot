"""
Enhanced group management for multiple active orders
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from db import (
    set_active_order_for_group, get_active_orders_for_group,
    is_admin, cursor, log_action
)
import logging

logger = logging.getLogger(__name__)

async def show_active_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all active orders for the current group"""
    if update.effective_chat.type == 'private':
        await update.message.reply_text("❌ Ця команда доступна тільки в групах")
        return
    
    group_id = update.effective_chat.id
    active_orders = get_active_orders_for_group(group_id)
    
    if not active_orders:
        text = "📝 <b>Активні замовлення</b>\n\n❌ Немає активних замовлень"
    else:
        text = "📝 <b>Активні замовлення групи</b>\n\n"
        for order_id, is_primary, user_id, username, bank, action, status in active_orders:
            primary_mark = "⭐ " if is_primary else ""
            action_text = "Реєстрація" if action == "register" else "Перев'язка"
            text += f"{primary_mark}Order #{order_id}\n"
            text += f"🏦 {bank} - {action_text}\n"
            text += f"👤 @{username} (ID: {user_id})\n"
            text += f"📊 Статус: {status}\n\n"
    
    # Add management buttons
    keyboard = []
    
    if active_orders:
        keyboard.append([InlineKeyboardButton("🔄 Переключити основне", callback_data="switch_primary")])
        keyboard.append([InlineKeyboardButton("➕ Додати замовлення", callback_data="add_active_order")])
        keyboard.append([InlineKeyboardButton("➖ Видалити з активних", callback_data="remove_active_order")])
    else:
        keyboard.append([InlineKeyboardButton("➕ Додати замовлення", callback_data="add_active_order")])
    
    keyboard.append([InlineKeyboardButton("🔄 Оновити", callback_data="refresh_active_orders")])
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def handle_active_order_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle active order management callbacks"""
    query = update.callback_query
    await query.answer()
    
    group_id = update.effective_chat.id
    data = query.data
    
    if data == "refresh_active_orders":
        # Just refresh the display
        await refresh_active_orders_display(query, group_id)
    
    elif data == "switch_primary":
        await show_switch_primary_menu(query, group_id)
    
    elif data == "add_active_order":
        await show_add_order_menu(query, group_id)
    
    elif data == "remove_active_order":
        await show_remove_order_menu(query, group_id)
    
    elif data.startswith("set_primary_"):
        order_id = int(data.split("_")[2])
        await set_primary_order(query, group_id, order_id)
    
    elif data.startswith("add_order_"):
        order_id = int(data.split("_")[2])
        await add_order_to_active(query, group_id, order_id)
    
    elif data.startswith("remove_order_"):
        order_id = int(data.split("_")[2])
        await remove_order_from_active(query, group_id, order_id)

async def refresh_active_orders_display(query, group_id: int):
    """Refresh the active orders display"""
    active_orders = get_active_orders_for_group(group_id)
    
    if not active_orders:
        text = "📝 <b>Активні замовлення</b>\n\n❌ Немає активних замовлень"
    else:
        text = "📝 <b>Активні замовлення групи</b>\n\n"
        for order_id, is_primary, user_id, username, bank, action, status in active_orders:
            primary_mark = "⭐ " if is_primary else ""
            action_text = "Реєстрація" if action == "register" else "Перев'язка"
            text += f"{primary_mark}Order #{order_id}\n"
            text += f"🏦 {bank} - {action_text}\n"
            text += f"👤 @{username} (ID: {user_id})\n"
            text += f"📊 Статус: {status}\n\n"
    
    keyboard = []
    if active_orders:
        keyboard.append([InlineKeyboardButton("🔄 Переключити основне", callback_data="switch_primary")])
        keyboard.append([InlineKeyboardButton("➕ Додати замовлення", callback_data="add_active_order")])
        keyboard.append([InlineKeyboardButton("➖ Видалити з активних", callback_data="remove_active_order")])
    else:
        keyboard.append([InlineKeyboardButton("➕ Додати замовлення", callback_data="add_active_order")])
    
    keyboard.append([InlineKeyboardButton("🔄 Оновити", callback_data="refresh_active_orders")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def show_switch_primary_menu(query, group_id: int):
    """Show menu to switch primary order"""
    active_orders = get_active_orders_for_group(group_id)
    
    if not active_orders:
        await query.edit_message_text("❌ Немає активних замовлень для переключення")
        return
    
    text = "⭐ <b>Виберіть основне замовлення:</b>\n\n"
    keyboard = []
    
    for order_id, is_primary, user_id, username, bank, action, status in active_orders:
        primary_mark = "⭐ " if is_primary else ""
        action_text = "Реєстрація" if action == "register" else "Перев'язка"
        button_text = f"{primary_mark}#{order_id} - {bank} ({username})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"set_primary_{order_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="refresh_active_orders")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def show_add_order_menu(query, group_id: int):
    """Show menu to add orders to active list"""
    # Get recent orders for this group that are not active
    cursor.execute("""
        SELECT o.id, o.user_id, o.username, o.bank, o.action, o.status
        FROM orders o
        WHERE o.group_id = ? AND o.status != 'Завершено'
        AND o.id NOT IN (
            SELECT mao.order_id FROM manager_active_orders mao WHERE mao.group_id = ?
        )
        ORDER BY o.created_at DESC
        LIMIT 10
    """, (group_id, group_id))
    
    orders = cursor.fetchall()
    
    if not orders:
        text = "❌ Немає доступних замовлень для додавання"
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="refresh_active_orders")]]
    else:
        text = "➕ <b>Виберіть замовлення для додавання:</b>\n\n"
        keyboard = []
        
        for order_id, user_id, username, bank, action, status in orders:
            action_text = "Реєстрація" if action == "register" else "Перев'язка"
            button_text = f"#{order_id} - {bank} ({username})"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"add_order_{order_id}")])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="refresh_active_orders")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def show_remove_order_menu(query, group_id: int):
    """Show menu to remove orders from active list"""
    active_orders = get_active_orders_for_group(group_id)
    
    if not active_orders:
        await query.edit_message_text("❌ Немає активних замовлень для видалення")
        return
    
    text = "➖ <b>Виберіть замовлення для видалення:</b>\n\n"
    keyboard = []
    
    for order_id, is_primary, user_id, username, bank, action, status in active_orders:
        primary_mark = "⭐ " if is_primary else ""
        action_text = "Реєстрація" if action == "register" else "Перев'язка"
        button_text = f"{primary_mark}#{order_id} - {bank} ({username})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"remove_order_{order_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="refresh_active_orders")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def set_primary_order(query, group_id: int, order_id: int):
    """Set an order as primary"""
    set_active_order_for_group(group_id, order_id, is_primary=True)
    log_action(order_id, f"manager_{query.from_user.id}", "set_primary_order", f"group:{group_id}")
    
    await query.answer("✅ Основне замовлення встановлено")
    await refresh_active_orders_display(query, group_id)

async def add_order_to_active(query, group_id: int, order_id: int):
    """Add order to active list"""
    set_active_order_for_group(group_id, order_id, is_primary=False)
    log_action(order_id, f"manager_{query.from_user.id}", "add_to_active", f"group:{group_id}")
    
    await query.answer("✅ Замовлення додано до активних")
    await refresh_active_orders_display(query, group_id)

async def remove_order_from_active(query, group_id: int, order_id: int):
    """Remove order from active list"""
    try:
        cursor.execute("DELETE FROM manager_active_orders WHERE group_id=? AND order_id=?", 
                      (group_id, order_id))
        cursor.connection.commit()
        
        log_action(order_id, f"manager_{query.from_user.id}", "remove_from_active", f"group:{group_id}")
        
        await query.answer("✅ Замовлення видалено з активних")
        await refresh_active_orders_display(query, group_id)
        
    except Exception as e:
        logger.error(f"Error removing order {order_id} from active: {e}")
        await query.answer("❌ Помилка при видаленні замовлення")

async def auto_add_new_order_to_active(context: ContextTypes.DEFAULT_TYPE, order_id: int, group_id: int):
    """Automatically add new order to active list when assigned to group"""
    try:
        set_active_order_for_group(group_id, order_id, is_primary=True)
        log_action(order_id, "system", "auto_add_to_active", f"group:{group_id}")
        
        # Notify group about new active order
        try:
            await context.bot.send_message(
                chat_id=group_id,
                text=f"📝 <b>Нове активне замовлення</b>\n\nOrder #{order_id} автоматично додано до активних замовлень групи.",
                parse_mode='HTML'
            )
        except Exception as e:
            logger.warning(f"Failed to notify group about new active order: {e}")
            
    except Exception as e:
        logger.error(f"Error auto-adding order {order_id} to active: {e}")

async def quick_switch_order(update: Update, context: ContextTypes.DEFAULT_TYPE, order_id: int):
    """Quick switch to specific order (enhanced /o command)"""
    if update.effective_chat.type == 'private':
        await update.message.reply_text("❌ Ця команда доступна тільки в групах")
        return
    
    group_id = update.effective_chat.id
    
    # Check if order exists and is accessible to this group
    cursor.execute("""
        SELECT o.id, o.user_id, o.username, o.bank, o.action, o.status, o.group_id
        FROM orders o
        WHERE o.id = ? AND (o.group_id = ? OR o.status != 'Завершено')
    """, (order_id, group_id))
    
    order = cursor.fetchone()
    
    if not order:
        await update.message.reply_text(f"❌ Замовлення #{order_id} не знайдено або недоступне")
        return
    
    order_id, user_id, username, bank, action, status, order_group_id = order
    
    # Add to active orders and set as primary
    set_active_order_for_group(group_id, order_id, is_primary=True)
    
    # Update order's group if different
    if order_group_id != group_id:
        cursor.execute("UPDATE orders SET group_id=? WHERE id=?", (group_id, order_id))
        cursor.connection.commit()
        log_action(order_id, f"manager_{update.effective_user.id}", "reassign_group", f"from:{order_group_id} to:{group_id}")
    
    log_action(order_id, f"manager_{update.effective_user.id}", "quick_switch", f"group:{group_id}")
    
    action_text = "Реєстрація" if action == "register" else "Перев'язка"
    text = f"✅ <b>Активне замовлення встановлено</b>\n\n"
    text += f"📋 Order #{order_id}\n"
    text += f"🏦 {bank} - {action_text}\n"
    text += f"👤 @{username} (ID: {user_id})\n"
    text += f"📊 Статус: {status}"
    
    await update.message.reply_text(text, parse_mode='HTML')

async def get_primary_order_for_group(group_id: int) -> int:
    """Get the primary active order for a group"""
    cursor.execute("""
        SELECT order_id FROM manager_active_orders 
        WHERE group_id = ? AND is_primary = 1 
        LIMIT 1
    """, (group_id,))
    
    result = cursor.fetchone()
    return result[0] if result else None
"""
Order form generation and management
"""
from telegram import Update
from telegram.ext import ContextTypes
from db import create_order_form, cursor, log_action
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

async def generate_order_form(update: Update, context: ContextTypes.DEFAULT_TYPE, order_id: int):
    """Generate and send order form/questionnaire when order is completed"""
    try:
        # Get order details
        cursor.execute("""
            SELECT o.user_id, o.username, o.bank, o.action, o.phone_number, o.email,
                   o.created_at, o.status
            FROM orders o
            WHERE o.id = ?
        """, (order_id,))
        
        order_row = cursor.fetchone()
        if not order_row:
            logger.warning(f"Order {order_id} not found for form generation")
            return
        
        user_id, username, bank, action, phone_number, email, created_at, status = order_row
        
        # Get all approved photos for this order
        cursor.execute("""
            SELECT stage, file_id, created_at
            FROM order_photos
            WHERE order_id = ? AND confirmed = 1 AND active = 1
            ORDER BY stage, created_at
        """, (order_id,))
        
        photos = cursor.fetchall()
        
        # Get order actions log
        cursor.execute("""
            SELECT actor, action_type, payload, created_at
            FROM order_actions_log
            WHERE order_id = ?
            ORDER BY created_at
        """, (order_id,))
        
        actions_log = cursor.fetchall()
        
        # Create form data
        form_data = {
            "order_id": order_id,
            "user_data": {
                "user_id": user_id,
                "username": username,
                "created_at": created_at
            },
            "bank": bank,
            "action": action,
            "manager_data": {
                "phone_number": phone_number,
                "email": email
            },
            "photos": [
                {
                    "stage": stage,
                    "file_id": file_id,
                    "uploaded_at": uploaded_at
                }
                for stage, file_id, uploaded_at in photos
            ],
            "actions_log": [
                {
                    "actor": actor,
                    "action_type": action_type,
                    "payload": payload,
                    "timestamp": timestamp
                }
                for actor, action_type, payload, timestamp in actions_log
            ],
            "status": status,
            "form_generated_at": datetime.now().isoformat()
        }
        
        # Save form to database
        create_order_form(order_id, form_data)
        
        # Generate human-readable form
        form_text = _generate_form_text(form_data)
        
        # Send form to admin group and manager group
        await _send_form_to_groups(context, order_id, form_text, photos)
        
        log_action(order_id, "system", "form_generated", f"Generated form for completed order")
        
        logger.info(f"Generated form for order {order_id}")
        
    except Exception as e:
        logger.error(f"Error generating form for order {order_id}: {e}")

def _generate_form_text(form_data: dict) -> str:
    """Generate human-readable form text"""
    order_id = form_data["order_id"]
    user_data = form_data["user_data"]
    bank = form_data["bank"]
    action = form_data["action"]
    manager_data = form_data["manager_data"]
    photos = form_data["photos"]
    
    action_text = "Реєстрації" if action == "register" else "Перев'язки"
    
    text = f"📋 <b>АНКЕТА ЗАМОВЛЕННЯ #{order_id}</b>\n\n"
    
    # User information
    text += f"👤 <b>ІНФОРМАЦІЯ КОРИСТУВАЧА</b>\n"
    text += f"ID: {user_data['user_id']}\n"
    text += f"Username: @{user_data['username']}\n"
    text += f"Дата створення: {user_data['created_at'][:16]}\n\n"
    
    # Bank and action
    text += f"🏦 <b>БАНК ТА ДІЯ</b>\n"
    text += f"Банк: {bank}\n"
    text += f"Тип: {action_text}\n\n"
    
    # Manager data
    text += f"👨‍💼 <b>ДАНІ ВІД МЕНЕДЖЕРА</b>\n"
    if manager_data.get('phone_number'):
        text += f"📱 Номер: {manager_data['phone_number']}\n"
    if manager_data.get('email'):
        text += f"📧 Email: {manager_data['email']}\n"
    text += "\n"
    
    # Photos summary
    text += f"📸 <b>СКРІНШОТИ</b>\n"
    if photos:
        photo_count_by_stage = {}
        for photo in photos:
            stage = photo['stage']
            photo_count_by_stage[stage] = photo_count_by_stage.get(stage, 0) + 1
        
        for stage in sorted(photo_count_by_stage.keys()):
            count = photo_count_by_stage[stage]
            text += f"Етап {stage + 1}: {count} фото\n"
    else:
        text += "❌ Немає збережених фото\n"
    
    text += f"\n✅ <b>ЗАМОВЛЕННЯ ЗАВЕРШЕНО</b>\n"
    text += f"Форма створена: {form_data['form_generated_at'][:16]}"
    
    return text

async def _send_form_to_groups(context: ContextTypes.DEFAULT_TYPE, order_id: int, form_text: str, photos: list):
    """Send generated form to relevant groups"""
    from db import get_bank_groups, ADMIN_GROUP_ID
    
    try:
        # Get order details to find which bank groups to notify
        cursor.execute("SELECT bank, group_id FROM orders WHERE id = ?", (order_id,))
        order_row = cursor.fetchone()
        if not order_row:
            return
        
        bank, order_group_id = order_row
        
        # Send to admin group
        if ADMIN_GROUP_ID:
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_GROUP_ID,
                    text=form_text,
                    parse_mode='HTML'
                )
                
                # Send photos if any
                for photo in photos[:5]:  # Limit to first 5 photos to avoid spam
                    try:
                        await context.bot.send_photo(
                            chat_id=ADMIN_GROUP_ID,
                            photo=photo['file_id'],
                            caption=f"Order #{order_id} - Етап {photo['stage'] + 1}"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to send photo to admin group: {e}")
                        
            except Exception as e:
                logger.warning(f"Failed to send form to admin group: {e}")
        
        # Send to order's manager group
        if order_group_id:
            try:
                await context.bot.send_message(
                    chat_id=order_group_id,
                    text=f"📋 <b>Анкета завершеного замовлення</b>\n\n{form_text}",
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.warning(f"Failed to send form to manager group {order_group_id}: {e}")
        
        # Send to bank-specific groups
        bank_groups = get_bank_groups(bank)
        for group_id, group_name in bank_groups:
            if group_id != order_group_id:  # Don't duplicate to the same group
                try:
                    await context.bot.send_message(
                        chat_id=group_id,
                        text=f"📋 <b>Нова завершена анкета для {bank}</b>\n\n{form_text}",
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.warning(f"Failed to send form to bank group {group_id}: {e}")
                    
    except Exception as e:
        logger.error(f"Error sending form to groups: {e}")

async def get_order_form(update: Update, context: ContextTypes.DEFAULT_TYPE, order_id: int):
    """Retrieve and display order form"""
    try:
        cursor.execute("SELECT form_data FROM order_forms WHERE order_id = ?", (order_id,))
        row = cursor.fetchone()
        
        if not row:
            text = f"❌ Анкета для замовлення #{order_id} не знайдена"
        else:
            form_data = json.loads(row[0])
            text = _generate_form_text(form_data)
        
        if update.message:
            await update.message.reply_text(text, parse_mode='HTML')
        else:
            await update.callback_query.edit_message_text(text, parse_mode='HTML')
            
    except Exception as e:
        logger.error(f"Error retrieving form for order {order_id}: {e}")
        error_text = f"❌ Помилка при отриманні анкети для замовлення #{order_id}"
        if update.message:
            await update.message.reply_text(error_text)
        else:
            await update.callback_query.edit_message_text(error_text)

async def list_order_forms(update: Update, context: ContextTypes.DEFAULT_TYPE, bank: str = None, limit: int = 10):
    """List recent order forms"""
    from db import is_admin
    
    if not is_admin(update.effective_user.id):
        return
    
    try:
        if bank:
            cursor.execute("""
                SELECT of.order_id, o.bank, o.action, o.username, of.created_at
                FROM order_forms of
                JOIN orders o ON of.order_id = o.id
                WHERE o.bank = ?
                ORDER BY of.created_at DESC
                LIMIT ?
            """, (bank, limit))
        else:
            cursor.execute("""
                SELECT of.order_id, o.bank, o.action, o.username, of.created_at
                FROM order_forms of
                JOIN orders o ON of.order_id = o.id
                ORDER BY of.created_at DESC
                LIMIT ?
            """, (limit,))
        
        rows = cursor.fetchall()
        
        if not rows:
            text = "📋 <b>Список анкет</b>\n\n❌ Немає збережених анкет"
        else:
            text = "📋 <b>Останні анкети</b>\n\n"
            for order_id, bank_name, action, username, created_at in rows:
                action_text = "Реєстрація" if action == "register" else "Перев'язка"
                text += f"📄 Order #{order_id}\n"
                text += f"🏦 {bank_name} - {action_text}\n"
                text += f"👤 @{username}\n"
                text += f"📅 {created_at[:16]}\n\n"
        
        if update.message:
            await update.message.reply_text(text, parse_mode='HTML')
        else:
            await update.callback_query.edit_message_text(text, parse_mode='HTML')
            
    except Exception as e:
        logger.error(f"Error listing order forms: {e}")
        error_text = "❌ Помилка при отриманні списку анкет"
        if update.message:
            await update.message.reply_text(error_text)
        else:
            await update.callback_query.edit_message_text(error_text)
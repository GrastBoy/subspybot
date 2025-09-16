"""
Data uniqueness checking and validation handlers
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from db import check_data_uniqueness, record_data_usage, log_action, cursor
import logging

logger = logging.getLogger(__name__)

async def check_and_confirm_data_uniqueness(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                           order_id: int, bank: str, phone_number: str = None, 
                                           email: str = None) -> bool:
    """
    Check data uniqueness and ask for confirmation if data was used before.
    Returns True if data is unique or confirmed to be reused, False if user declined.
    """
    if not phone_number and not email:
        return True
    
    phone_used, email_used = check_data_uniqueness(bank, phone_number, email)
    
    if not phone_used and not email_used:
        # Data is unique, record usage and proceed
        record_data_usage(order_id, bank, phone_number, email)
        return True
    
    # Data was used before, ask for confirmation
    warning_parts = []
    if phone_used and phone_number:
        warning_parts.append(f"номер {phone_number}")
    if email_used and email:
        warning_parts.append(f"email {email}")
    
    warning_text = " та ".join(warning_parts)
    
    text = f"⚠️ <b>Увага!</b>\n\n"
    text += f"Для банку '{bank}' вже використовувався {warning_text}.\n\n"
    text += f"Ви впевнені, що хочете його знову використати?"
    
    keyboard = [
        [InlineKeyboardButton("✅ Так, використати", 
                            callback_data=f"confirm_reuse_{order_id}_{bank}")],
        [InlineKeyboardButton("❌ Ні, скасувати", 
                            callback_data=f"cancel_reuse_{order_id}")]
    ]
    
    # Store data in context for later use
    context.user_data[f'pending_data_{order_id}'] = {
        'phone_number': phone_number,
        'email': email,
        'bank': bank
    }
    
    if update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    else:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    
    return False  # Data needs confirmation

async def handle_data_reuse_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle confirmation/cancellation of data reuse"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith("confirm_reuse_"):
        # Extract order_id and bank from callback data
        parts = data.split("_")
        if len(parts) >= 4:
            order_id = int(parts[2])
            bank = "_".join(parts[3:])  # Handle bank names with underscores
            
            # Get pending data
            pending_data = context.user_data.get(f'pending_data_{order_id}')
            if pending_data:
                phone_number = pending_data.get('phone_number')
                email = pending_data.get('email')
                
                # Record the usage
                record_data_usage(order_id, bank, phone_number, email)
                log_action(order_id, f"manager_{update.effective_user.id}", "confirm_data_reuse", 
                          f"phone: {phone_number}, email: {email}")
                
                # Clean up
                context.user_data.pop(f'pending_data_{order_id}', None)
                
                await query.edit_message_text("✅ Дані підтверджено та збережено.")
                return True
    
    elif data.startswith("cancel_reuse_"):
        # Extract order_id
        parts = data.split("_")
        if len(parts) >= 3:
            order_id = int(parts[2])
            
            # Clean up
            context.user_data.pop(f'pending_data_{order_id}', None)
            
            log_action(order_id, f"manager_{update.effective_user.id}", "cancel_data_reuse", "")
            
            await query.edit_message_text("❌ Використання даних скасовано.")
            return False
    
    return False

def validate_phone_number(phone: str) -> str:
    """Validate and normalize phone number"""
    if not phone:
        return None
    
    # Remove all non-digit characters except +
    import re
    phone_clean = re.sub(r'[^\d+]', '', phone)
    
    # Handle Ukrainian phone numbers
    if phone_clean.startswith('+380'):
        return phone_clean
    elif phone_clean.startswith('380'):
        return '+' + phone_clean
    elif phone_clean.startswith('0') and len(phone_clean) == 10:
        return '+38' + phone_clean
    elif len(phone_clean) == 9:
        return '+380' + phone_clean
    
    # For other international numbers, keep as is if starts with +
    if phone_clean.startswith('+'):
        return phone_clean
    
    return None

def validate_email(email: str) -> str:
    """Validate email address"""
    if not email:
        return None
    
    import re
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if re.match(email_pattern, email.strip()):
        return email.strip().lower()
    
    return None

async def show_data_usage_history(update: Update, context: ContextTypes.DEFAULT_TYPE, bank: str):
    """Show history of data usage for a bank"""
    if not hasattr(update, 'effective_user') or not update.effective_user:
        return
    
    from db import is_admin
    if not is_admin(update.effective_user.id):
        return
    
    cursor.execute("""
        SELECT bdu.phone_number, bdu.email, bdu.created_at, o.id as order_id, o.username
        FROM bank_data_usage bdu
        LEFT JOIN orders o ON bdu.order_id = o.id
        WHERE bdu.bank = ?
        ORDER BY bdu.created_at DESC
        LIMIT 20
    """, (bank,))
    
    rows = cursor.fetchall()
    
    if not rows:
        text = f"📊 <b>Історія використання даних для '{bank}'</b>\n\n❌ Немає записів"
    else:
        text = f"📊 <b>Історія використання даних для '{bank}'</b>\n\n"
        for phone, email, created_at, order_id, username in rows:
            text += f"🕐 {created_at[:16]}\n"
            if phone:
                text += f"📱 {phone}\n"
            if email:
                text += f"📧 {email}\n"
            text += f"👤 {username or 'Unknown'} (Order #{order_id})\n\n"
    
    if update.message:
        await update.message.reply_text(text, parse_mode='HTML')
    else:
        await update.callback_query.edit_message_text(text, parse_mode='HTML')
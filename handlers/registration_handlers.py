"""
Registration flow handlers for multi-step registration process (Stages 2-5).
This module handles the registration flow that occurs after Stage 1 (screenshots) is completed.
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from db import conn, cursor, ADMIN_GROUP_ID
from states import user_states

logger = logging.getLogger(__name__)

# Registration stages constants
REG_STAGE_REQUEST_DATA = 2
REG_STAGE_PHONE_VERIFY = 3
REG_STAGE_EMAIL_VERIFY = 4
REG_STAGE_COMPLETE = 5


def update_order_registration_data(order_id: int, phone: str = None, email: str = None, 
                                 phone_verified: int = None, email_verified: int = None,
                                 registration_stage: int = None):
    """Update registration-related fields in orders table"""
    updates = []
    params = []
    
    if phone is not None:
        updates.append("phone_number = ?")
        params.append(phone)
    if email is not None:
        updates.append("email = ?") 
        params.append(email)
    if phone_verified is not None:
        updates.append("phone_verified = ?")
        params.append(phone_verified)
    if email_verified is not None:
        updates.append("email_verified = ?")
        params.append(email_verified)
    if registration_stage is not None:
        updates.append("registration_stage = ?")
        params.append(registration_stage)
    
    if updates:
        params.append(order_id)
        query = f"UPDATE orders SET {', '.join(updates)} WHERE id = ?"
        cursor.execute(query, params)
        conn.commit()


def get_order_registration_data(order_id: int):
    """Get registration data for an order"""
    cursor.execute(
        "SELECT phone_number, phone_verified, email, email_verified, registration_stage "
        "FROM orders WHERE id = ?", 
        (order_id,)
    )
    return cursor.fetchone()


async def start_registration_flow(user_id: int, order_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Start the registration flow at Stage 2 - Request data"""
    
    # Update order to registration stage 2
    update_order_registration_data(order_id, registration_stage=REG_STAGE_REQUEST_DATA)
    
    # Create keyboard for data request
    keyboard = [
        [InlineKeyboardButton("📞 Надіслати номер телефону", callback_data=f"s2_req_phone_{order_id}")],
        [InlineKeyboardButton("📧 Надіслати email", callback_data=f"s2_req_email_{order_id}")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "🎯 **Етап 2 з 5: Дані для реєстрації**\n\n"
        "Для завершення реєстрації потрібно підтвердити:\n"
        "• Номер телефону (SMS-код)\n"
        "• Електронну пошту\n\n"
        "Оберіть, що хочете надіслати спочатку:"
    )
    
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.warning("Failed to send registration start message to user %s: %s", user_id, e)


async def handle_registration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle registration flow callbacks"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    try:
        # Parse callback data
        if data.startswith("s2_req_"):
            await handle_stage2_request(query, data, context)
        elif data.startswith("s3_phone_"):
            await handle_stage3_phone(query, data, context)
        elif data.startswith("s4_email_"):
            await handle_stage4_email(query, data, context)
        elif data.startswith("s5_continue_"):
            await handle_stage5_continue(query, data, context)
        else:
            await query.edit_message_text("❌ Невідомий тип запиту.")
            
    except Exception as e:
        logger.exception("Error in handle_registration_callback: %s", e)
        try:
            await query.edit_message_text("❌ Сталася помилка. Спробуйте ще раз.")
        except Exception:
            pass


async def handle_stage2_request(query, data: str, context: ContextTypes.DEFAULT_TYPE):
    """Handle Stage 2 - Data request"""
    user_id = query.from_user.id
    
    try:
        # Parse order_id from callback data (s2_req_phone_123 or s2_req_email_123)
        parts = data.split("_")
        if len(parts) < 3:
            raise ValueError("Invalid callback data format")
        order_id = int(parts[-1])
        req_type = parts[2]  # "phone" or "email"
        
        if req_type == "phone":
            text = (
                "📞 **Надішліть ваш номер телефону**\n\n"
                "Формат: +380XXXXXXXXX\n"
                "Приклад: +380501234567\n\n"
                "Надішліть повідомленням номер телефону:"
            )
            
            # Store context for next message
            user_states[user_id] = user_states.get(user_id, {})
            user_states[user_id]['awaiting_phone'] = order_id
            
        elif req_type == "email":
            text = (
                "📧 **Надішліть вашу електронну пошту**\n\n"
                "Приклад: example@gmail.com\n\n"
                "Надішліть повідомленням вашу електронну адресу:"
            )
            
            # Store context for next message  
            user_states[user_id] = user_states.get(user_id, {})
            user_states[user_id]['awaiting_email'] = order_id
            
        else:
            await query.edit_message_text("❌ Невідомий тип запиту.")
            return
            
        await query.edit_message_text(text, parse_mode='Markdown')
        
    except Exception as e:
        logger.exception("Error in handle_stage2_request: %s", e)
        await query.edit_message_text("❌ Сталася помилка при обробці запиту.")


async def handle_stage3_phone(query, data: str, context: ContextTypes.DEFAULT_TYPE):
    """Handle Stage 3 - Phone verification"""
    try:
        # Parse order_id from callback data  
        order_id = int(data.split("_")[-1])
        
        # Create keyboard for code input
        keyboard = [
            [InlineKeyboardButton("📝 Ввести код з SMS", callback_data=f"s3_enter_code_{order_id}")],
            [InlineKeyboardButton("🔄 Надіслати код повторно", callback_data=f"s3_resend_code_{order_id}")],
            [InlineKeyboardButton("📞 Змінити номер", callback_data=f"s2_req_phone_{order_id}")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            "📱 **Етап 3 з 5: Підтвердження номера телефону**\n\n"
            "SMS з кодом підтвердження надіслано на ваш номер.\n"
            "Код складається з 4-6 цифр.\n\n"
            "Оберіть дію:"
        )
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
    except Exception as e:
        logger.exception("Error in handle_stage3_phone: %s", e)
        await query.edit_message_text("❌ Сталася помилка.")


async def handle_stage4_email(query, data: str, context: ContextTypes.DEFAULT_TYPE):
    """Handle Stage 4 - Email verification"""
    try:
        # Parse order_id from callback data
        order_id = int(data.split("_")[-1])
        
        # Create keyboard for email verification
        keyboard = [
            [InlineKeyboardButton("✅ Підтвердити email", callback_data=f"s4_confirm_email_{order_id}")],
            [InlineKeyboardButton("📧 Змінити email", callback_data=f"s2_req_email_{order_id}")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            "📧 **Етап 4 з 5: Підтвердження електронної пошти**\n\n"
            "Лист з підтвердженням надіслано на вашу електронну адресу.\n"
            "Перейдіть за посиланням у листі для підтвердження.\n\n"
            "Після підтвердження натисніть кнопку нижче:"
        )
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
    except Exception as e:
        logger.exception("Error in handle_stage4_email: %s", e)
        await query.edit_message_text("❌ Сталася помилка.")


async def handle_stage5_continue(query, data: str, context: ContextTypes.DEFAULT_TYPE):
    """Handle Stage 5 - Final transition"""
    try:
        # Parse order_id from callback data
        order_id = int(data.split("_")[-1])
        
        # Check if both phone and email are verified
        reg_data = get_order_registration_data(order_id)
        if not reg_data:
            await query.edit_message_text("❌ Не знайдено дані замовлення.")
            return
            
        phone_number, phone_verified, email, email_verified, registration_stage = reg_data
        
        if phone_verified and email_verified:
            # Both verified - complete registration and continue with instructions
            update_order_registration_data(order_id, registration_stage=REG_STAGE_COMPLETE)
            
            await query.edit_message_text(
                "✅ **Реєстрація завершена!**\n\n"
                "Номер телефону та електронна пошта підтверджені.\n"
                "Продовжуємо з наступними інструкціями...",
                parse_mode='Markdown'
            )
            
            # Resume regular instruction flow
            from handlers.photo_handlers import send_instruction
            user_id = query.from_user.id
            await send_instruction(user_id, context)
            
        else:
            # Show status and what's missing
            missing = []
            if not phone_verified:
                missing.append("номер телефону")
            if not email_verified:
                missing.append("електронну пошту")
                
            text = (
                f"❌ **Реєстрація не завершена**\n\n"
                f"Ще потрібно підтвердити: {', '.join(missing)}\n\n"
                f"Статус підтвердження:\n"
                f"📞 Телефон: {'✅' if phone_verified else '❌'}\n"
                f"📧 Email: {'✅' if email_verified else '❌'}"
            )
            
            # Create navigation keyboard
            keyboard = []
            if not phone_verified:
                keyboard.append([InlineKeyboardButton("📞 Підтвердити телефон", callback_data=f"s3_phone_{order_id}")])
            if not email_verified:
                keyboard.append([InlineKeyboardButton("📧 Підтвердити email", callback_data=f"s4_email_{order_id}")])
                
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
    except Exception as e:
        logger.exception("Error in handle_stage5_continue: %s", e)
        await query.edit_message_text("❌ Сталася помилка.")


async def handle_registration_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text input during registration flow"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    state = user_states.get(user_id, {})
    
    # Only process if user is in a registration state
    if not any(key in state for key in ['awaiting_phone', 'awaiting_email', 'awaiting_sms_code']):
        # Not in registration flow, don't handle this message
        return
    
    try:
        # Check if waiting for phone number
        if 'awaiting_phone' in state:
            order_id = state['awaiting_phone']
            
            # Basic phone validation
            if not text.startswith('+') or len(text) < 10:
                await update.message.reply_text(
                    "❌ Невірний формат номера. Введіть номер у форматі +380XXXXXXXXX"
                )
                return
                
            # Save phone number
            update_order_registration_data(order_id, phone=text, registration_stage=REG_STAGE_PHONE_VERIFY)
            
            # Remove awaiting state
            del user_states[user_id]['awaiting_phone']
            
            # Move to phone verification stage
            keyboard = [
                [InlineKeyboardButton("📱 Перейти до підтвердження", callback_data=f"s3_phone_{order_id}")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"✅ Номер телефону збережено: {text}\n\n"
                f"Переходимо до підтвердження номера:",
                reply_markup=reply_markup
            )
            
        # Check if waiting for email
        elif 'awaiting_email' in state:
            order_id = state['awaiting_email']
            
            # Basic email validation
            if '@' not in text or '.' not in text:
                await update.message.reply_text(
                    "❌ Невірний формат email. Введіть коректну електронну адресу."
                )
                return
                
            # Save email
            update_order_registration_data(order_id, email=text, registration_stage=REG_STAGE_EMAIL_VERIFY)
            
            # Remove awaiting state
            del user_states[user_id]['awaiting_email']
            
            # Move to email verification stage  
            keyboard = [
                [InlineKeyboardButton("📧 Перейти до підтвердження", callback_data=f"s4_email_{order_id}")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"✅ Email збережено: {text}\n\n"
                f"Переходимо до підтвердження пошти:",
                reply_markup=reply_markup
            )
            
        # Check if waiting for SMS code
        elif 'awaiting_sms_code' in state:
            order_id = state['awaiting_sms_code']
            
            # Basic SMS code validation
            if not text.isdigit() or len(text) < 4 or len(text) > 6:
                await update.message.reply_text(
                    "❌ Невірний формат коду. Введіть 4-6 цифр з SMS."
                )
                return
                
            # Mark phone as verified (in real implementation, you'd verify the code)
            update_order_registration_data(order_id, phone_verified=1)
            
            # Remove awaiting state
            del user_states[user_id]['awaiting_sms_code']
            
            # Check if registration can be completed
            reg_data = get_order_registration_data(order_id)
            if reg_data:
                phone_number, phone_verified, email, email_verified, registration_stage = reg_data
                
                if phone_verified and email_verified:
                    # Both verified - move to completion
                    keyboard = [
                        [InlineKeyboardButton("✅ Завершити реєстрацію", callback_data=f"s5_continue_{order_id}")],
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await update.message.reply_text(
                        "🎉 **Номер телефону підтверджено!**\n\n"
                        "Всі дані підтверджені. Можна завершити реєстрацію:",
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                else:
                    # Still need email verification
                    keyboard = [
                        [InlineKeyboardButton("📧 Підтвердити email", callback_data=f"s4_email_{order_id}")],
                        [InlineKeyboardButton("✅ Завершити пізніше", callback_data=f"s5_continue_{order_id}")],
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await update.message.reply_text(
                        "✅ **Номер телефону підтверджено!**\n\n"
                        "Тепер потрібно підтвердити email:",
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
        
    except Exception as e:
        logger.exception("Error in handle_registration_text_input: %s", e)
        await update.message.reply_text("❌ Сталася помилка при обробці даних.")


async def handle_sms_code_input(query, data: str, context: ContextTypes.DEFAULT_TYPE):
    """Handle SMS code input request"""
    try:
        # Parse order_id from callback data
        order_id = int(data.split("_")[-1])
        user_id = query.from_user.id
        
        if "enter_code" in data:
            # User wants to enter SMS code
            user_states[user_id] = user_states.get(user_id, {})
            user_states[user_id]['awaiting_sms_code'] = order_id
            
            await query.edit_message_text(
                "📱 **Введіть код з SMS**\n\n"
                "Надішліть повідомленням код з 4-6 цифр, який прийшов на ваш телефон:",
                parse_mode='Markdown'
            )
            
        elif "resend_code" in data:
            # Simulate code resend
            await query.answer("📱 Код надіслано повторно!")
            
            keyboard = [
                [InlineKeyboardButton("📝 Ввести код з SMS", callback_data=f"s3_enter_code_{order_id}")],
                [InlineKeyboardButton("📞 Змінити номер", callback_data=f"s2_req_phone_{order_id}")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_reply_markup(reply_markup=reply_markup)
            
    except Exception as e:
        logger.exception("Error in handle_sms_code_input: %s", e)
        await query.edit_message_text("❌ Сталася помилка.")


async def handle_email_confirmation(query, data: str, context: ContextTypes.DEFAULT_TYPE):
    """Handle email confirmation"""
    try:
        # Parse order_id from callback data
        order_id = int(data.split("_")[-1])
        
        # Mark email as verified (in real implementation, you'd check actual confirmation)
        update_order_registration_data(order_id, email_verified=1)
        
        # Check if registration can be completed
        reg_data = get_order_registration_data(order_id)
        if reg_data:
            phone_number, phone_verified, email, email_verified, registration_stage = reg_data
            
            if phone_verified and email_verified:
                # Both verified - move to completion
                keyboard = [
                    [InlineKeyboardButton("✅ Завершити реєстрацію", callback_data=f"s5_continue_{order_id}")],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    "🎉 **Email підтверджено!**\n\n"
                    "Всі дані підтверджені. Можна завершити реєстрацію:",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                # Still need phone verification
                keyboard = [
                    [InlineKeyboardButton("📱 Підтвердити телефон", callback_data=f"s3_phone_{order_id}")],
                    [InlineKeyboardButton("✅ Завершити пізніше", callback_data=f"s5_continue_{order_id}")],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    "✅ **Email підтверджено!**\n\n"
                    "Тепер потрібно підтвердити номер телефону:",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                
    except Exception as e:
        logger.exception("Error in handle_email_confirmation: %s", e)
        await query.edit_message_text("❌ Сталася помилка.")


# Extended callback handler that includes SMS code and email confirmation
async def handle_extended_registration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Extended callback handler for all registration-related callbacks"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    try:
        if data.startswith("s3_enter_code_") or data.startswith("s3_resend_code_"):
            await handle_sms_code_input(query, data, context)
        elif data.startswith("s4_confirm_email_"):
            await handle_email_confirmation(query, data, context)
        else:
            # Fallback to main registration handler
            await handle_registration_callback(update, context)
            
    except Exception as e:
        logger.exception("Error in handle_extended_registration_callback: %s", e)
        try:
            await query.edit_message_text("❌ Сталася помилка. Спробуйте ще раз.")
        except Exception:
            pass
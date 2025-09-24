import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from db import cursor, get_banks, get_bank_details
from handlers.photo_handlers import assign_group_or_queue, create_order_in_db, send_instruction
from states import find_age_requirement, user_states

logger = logging.getLogger(__name__)


def _banks_from_instructions(action: str):
    """Get banks from database that support the given action and are active"""
    banks = get_banks()
    result = []
    
    for bank_name, is_active, register_enabled, change_enabled, _, _, _, _, _, _, _ in banks:
        if not is_active:
            continue
            
        if action == "register" and register_enabled:
            result.append(bank_name)
        elif action == "change" and change_enabled:
            result.append(bank_name)
            
    logger.debug(f"User menu banks (action={action}): {result}")
    return result

def _get_visible_banks(action: str):
    banks = _banks_from_instructions(action)
    try:
        cursor.execute("SELECT bank, show_register, show_change FROM bank_visibility")
        rows = cursor.fetchall()
        vis = {b: (sr, sc) for b, sr, sc in rows}
    except Exception:
        vis = {}
    result = []
    for bank in banks:
        sr, sc = vis.get(bank, (1, 1))
        if action == "register" and sr:
            result.append(bank)
        if action == "change" and sc:
            result.append(bank)
    return result

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Актуальні банки", callback_data="menu_banks")],
        [InlineKeyboardButton("Інформація та оплата", callback_data="menu_info")],
        [InlineKeyboardButton("Подати заявку на співпрацю", callback_data="menu_coop")]
    ]
    if update.message:
        await update.message.reply_text("Вітаємо! Оберіть опцію:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif update.callback_query:
        try:
            await update.callback_query.edit_message_text("Вітаємо! Оберіть опцію:", reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception:
            pass

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_banks":
        keyboard = [
            [InlineKeyboardButton("Реєстрація", callback_data="type_register")],
            [InlineKeyboardButton("Перевʼязка", callback_data="type_change")],
            [InlineKeyboardButton("Назад", callback_data="back_to_main")]
        ]
        await query.edit_message_text("Оберіть тип операції:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data == "menu_info":
        info_text = (
            "💳 Оплата здійснюється на карту XXXX XXXX XXXX XXXX\n"
            "Після оплати обов'язково відправте квитанцію в чат.\n\n"
            "Якщо маєте питання, звертайтесь до менеджера."
        )
        await query.edit_message_text(info_text, reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Назад", callback_data="back_to_main")]]
        ))
        return

    if data == "back_to_main":
        await start(update, context)
        return

    if data in ("type_register", "type_change"):
        action = "register" if data == "type_register" else "change"
        banks = _get_visible_banks(action)
        keyboard = []
        
        for bank in banks:
            # Get bank details to show price directly in button (action-specific)
            bank_details = get_bank_details(bank, action)
            button_text = bank
            
            # Add price and age indicators
            if bank_details:
                price = bank_details.get('price')
                min_age = bank_details.get('min_age', 18)
                
                # Add price directly to button text
                if price:
                    button_text += f" - {price}"
                    
                # Add age indicator if needed
                if min_age > 18:
                    button_text += " 🔞"
            
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"bank_{bank}_{action}")])
        
        keyboard.append([InlineKeyboardButton("Назад", callback_data="menu_banks")])
        
        if not banks:
            await query.edit_message_text("Наразі записи для цього типу відсутні. Спробуйте пізніше.",
                                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="menu_banks")]]))
            return
            
        # Update explanation text
        has_age_restrictions = any(get_bank_details(bank, action) and get_bank_details(bank, action).get('min_age', 18) > 18 for bank in banks)
        explanation = "\n\n🔞 - підвищені вікові вимоги" if has_age_restrictions else ""
        await query.edit_message_text(f"Оберіть банк (з ціною):{explanation}", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith("bank_"):
        try:
            _, bank, action = data.split("_", 2)
        except ValueError:
            await query.edit_message_text("❌ Некоректний вибір. Спробуйте ще раз.")
            return

        user_id = query.from_user.id
        
        # Get bank details from database with action-specific pricing
        bank_details = get_bank_details(bank, action)
        age_required = bank_details.get('min_age', 18) if bank_details else 18
        price = bank_details.get('price') if bank_details else None
        
        user_states[user_id] = {"order_id": None, "bank": bank, "action": action, "stage": 0, "age_required": age_required}

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Так, я відповідаю вимогам", callback_data="age_confirm_yes"),
             InlineKeyboardButton("Ні, я не підходжу", callback_data="age_confirm_no")]
        ])
        text = f"Ви обрали банк {bank} ({'Реєстрація' if action == 'register' else 'Перевʼязка'}).\n\n"
        
        # Show minimum age requirement only (price was already shown in selection menu)
        text += f"🔞 Мінімальний вік: {age_required} років\n\n"
        
        text += "Підтвердіть, будь ласка, що ви відповідаєте цим вимогам."
        await query.edit_message_text(text, reply_markup=keyboard)
        return

async def age_confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    state = user_states.get(user_id)
    if not state:
        await query.edit_message_text("❌ Сталася помилка, будь ласка, почніть заново командою /start")
        return

    if data == "age_confirm_no":
        reg_banks = _get_visible_banks("register")
        chg_banks = _get_visible_banks("change")
        keyboard = [[InlineKeyboardButton(bank, callback_data=f"bank_{bank}_register")] for bank in reg_banks] + \
                   [[InlineKeyboardButton(bank, callback_data=f"bank_{bank}_change")] for bank in chg_banks]
        keyboard.append([InlineKeyboardButton("Назад", callback_data="back_to_main")])
        await query.edit_message_text("Ви не відповідаєте віковим вимогам. Будь ласка, оберіть інший банк.", reply_markup=InlineKeyboardMarkup(keyboard))
        user_states.pop(user_id, None)
        return

    bank = state["bank"]
    action = state["action"]
    username = query.from_user.username or "Без_ніка"

    order_id = create_order_in_db(user_id, username, bank, action)
    user_states[user_id].update({"order_id": order_id, "stage": 0})

    assigned = await assign_group_or_queue(order_id, user_id, username, bank, action, context)
    if assigned:
        await send_instruction(user_id, context)
        await query.edit_message_text("✅ Вік підтверджено. Менеджер призначений. Починаємо інструкції.")
    else:
        await query.edit_message_text("✅ Вік підтверджено. Ви поставлені в чергу.")

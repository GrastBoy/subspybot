import re
from datetime import datetime
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from db import cursor, conn, ADMIN_GROUP_ID, log_action, logger
from states import (
    STAGE2_MANAGER_WAIT_DATA,
    STAGE2_MANAGER_WAIT_CODE,
    STAGE2_MANAGER_WAIT_MSG
)

PHONE_RE = re.compile(r"^\+?\d{9,15}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# ================== DB helpers ==================

def _get_order_core(order_id: int):
    cursor.execute("""
        SELECT id,user_id,username,bank,action,stage,status,group_id,
               phone_number,email,phone_verified,email_verified,
               phone_code_status,phone_code_session,phone_code_last_sent_at,
               phone_code_attempts,stage2_status,stage2_restart_count,stage2_complete
        FROM orders WHERE id=?""", (order_id,))
    return cursor.fetchone()

def _update_order(order_id: int, **fields):
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [order_id]
    cursor.execute(f"UPDATE orders SET {sets} WHERE id=?", vals)
    conn.commit()

# ================== Safe send helper ==================

async def _safe_send(bot, chat_id: int, text: str, **kwargs):
    try:
        await bot.send_message(chat_id=chat_id, text=text, **kwargs)
    except Exception as e:
        logger.warning("Failed to send message to %s: %s", chat_id, e)

# ================== Keyboards ==================

def _manager_data_keyboard(order_id: int, show_code: bool = False):
    # Початковий або очікуючий стан: дані ще не надано
    row1 = [InlineKeyboardButton("Надати дані", callback_data=f"mgr_provide_data_{order_id}")]
    # Код ще не можна (немає телефону) – залишимо неактивним або не показуватимемо
    rows = [row1]
    rows.append([InlineKeyboardButton("💬 Написати користувачу", callback_data=f"mgr_msg_{order_id}")])
    return InlineKeyboardMarkup(rows)

def _manager_actions_keyboard(order_id: int):
    # Після отримання даних – можна дати код і писати
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Надати код", callback_data=f"mgr_provide_code_{order_id}")],
        [InlineKeyboardButton("💬 Написати користувачу", callback_data=f"mgr_msg_{order_id}")]
    ])

def _render_stage2_keyboard(order):
    (oid, user_id, username, bank, action, stage, status, group_id,
     phone_number, email, phone_verified, email_verified,
     phone_code_status, phone_code_session, phone_code_last_sent_at,
     phone_code_attempts, stage2_status, stage2_restart_count, stage2_complete) = order

    buttons = []
    if stage2_complete:
        buttons.append([InlineKeyboardButton("⏭ Перейти далі", callback_data=f"s2_continue_{oid}")])
    else:
        if stage2_status == "idle":
            buttons.append([InlineKeyboardButton("📄 Запросити дані", callback_data=f"s2_req_data_{oid}")])
        elif stage2_status == "waiting_manager_data":
            # без кнопок
            pass
        elif stage2_status == "data_received":
            buttons.append([InlineKeyboardButton("🔑 Запросити код", callback_data=f"s2_req_code_{oid}")])
            buttons.append([
                InlineKeyboardButton("✅ Підтвердити пошту", callback_data=f"s2_email_confirm_{oid}"),
                InlineKeyboardButton("📞 Номер підтверджено", callback_data=f"s2_phone_confirm_{oid}")
            ])

        if (not stage2_complete) and phone_verified and email_verified:
            buttons.append([InlineKeyboardButton("⏭ Перейти далі", callback_data=f"s2_continue_{oid}")])
    return InlineKeyboardMarkup(buttons)

async def _send_stage2_ui(user_id: int, order_id: int, context: ContextTypes.DEFAULT_TYPE):
    order = _get_order_core(order_id)
    if not order:
        await _safe_send(context.bot, user_id, "❌ Замовлення не знайдено (Stage2).")
        return

    (_, _, username, bank, action, stage, status, group_id,
     phone_number, email, phone_verified, email_verified,
     phone_code_status, phone_code_session, phone_code_last_sent_at,
     phone_code_attempts, stage2_status, stage2_restart_count, stage2_complete) = order

    lines = [
        "🔐 Етап 2: Дані для реєстрації",
        f"🏦 {bank} / {action}",
        f"Статус: {stage2_status}"
    ]
    if stage2_status == "waiting_manager_data":
        lines.append("⌛ Очікуємо, поки менеджер надасть номер і email.")
    if phone_number:
        lines.append(f"Телефон: {phone_number} ({'✅' if phone_verified else '❌'})")
    if email:
        lines.append(f"Email: {email} ({'✅' if email_verified else '❌'})")
    if phone_code_status and phone_code_status != "none":
        lines.append(f"Статус коду: {phone_code_status}")
    if stage2_complete:
        lines.append("✅ Етап 2 завершено. Можете продовжити.")

    await _safe_send(context.bot, user_id, "\n".join(lines), reply_markup=_render_stage2_keyboard(order))

# ================== Helpers ==================

def _extract_order_id(data: str) -> Optional[int]:
    parts = data.split("_")
    if len(parts) < 3:
        return None
    try:
        return int(parts[-1])
    except ValueError:
        return None

async def _notify_managers_after_data(order_id: int, context: ContextTypes.DEFAULT_TYPE):
    order = _get_order_core(order_id)
    if not order:
        return
    (_, user_id, username, bank, action, _, _, _, phone, email,
     phone_verified, email_verified, phone_code_status, *_rest) = order
    txt = (
        f"📨 Дані отримано (Order {order_id}).\n"
        f"👤 @{username or 'Без_ніка'} (ID: {user_id})\n"
        f"🏦 {bank} / {action}\n"
        f"📞 Телефон: {phone or '—'} ({'✅' if phone_verified else '❌'})\n"
        f"📧 Email: {email or '—'} ({'✅' if email_verified else '❌'})\n"
        f"🔐 Код: {phone_code_status}\n"
        f"➡️ Доступні дії: Надати код / Написати користувачу"
    )
    try:
        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=txt,
            reply_markup=_manager_actions_keyboard(order_id)
        )
        log_action(order_id, "system", "provide_data_notify")
    except Exception as e:
        logger.warning("Failed notify managers after data: %s", e)

async def _notify_managers_request_code(order_id: int, context: ContextTypes.DEFAULT_TYPE):
    order = _get_order_core(order_id)
    if not order:
        return
    (_, user_id, username, bank, action, *_r) = order
    txt = (
        f"🔑 Запит коду (Order {order_id}).\n"
        f"👤 @{username or 'Без_ніка'} (ID: {user_id})\n"
        f"🏦 {bank} / {action}\n"
        f"➡️ Натисніть 'Надати код' або напишіть користувачу."
    )
    try:
        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=txt,
            reply_markup=_manager_actions_keyboard(order_id)
        )
        log_action(order_id, "system", "request_code_notify")
    except Exception as e:
        logger.warning("Failed notify managers request code: %s", e)

# ================== USER CALLBACKS ==================

async def user_stage2_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    order_id = _extract_order_id(data)
    if order_id is None:
        return

    cursor.execute("""SELECT user_id, stage2_status, phone_verified, email_verified,
                             stage2_complete, phone_code_status FROM orders WHERE id=?""", (order_id,))
    row = cursor.fetchone()
    if not row:
        await query.edit_message_text("❌ Замовлення не знайдено.")
        return
    order_user_id, stage2_status, phone_verified, email_verified, stage2_complete, phone_code_status = row
    if order_user_id != user_id:
        await query.edit_message_text("⛔ Це не ваше замовлення.")
        return

    if data.startswith("s2_req_data_"):
        if stage2_status == "idle":
            _update_order(order_id, stage2_status="waiting_manager_data")
            log_action(order_id, "user", "stage2_request_data")
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_GROUP_ID,
                    text=f"📨 Order {order_id}: користувач запросив номер і пошту.",
                    reply_markup=_manager_data_keyboard(order_id)
                )
            except Exception as e:
                logger.warning("Manager notify (req data) fail: %s", e)
            await query.edit_message_text("🔄 Запит відправлено. Очікуємо менеджера.")
        elif stage2_status == "waiting_manager_data":
            await query.edit_message_text("⌛ Очікуємо менеджера.")
        elif stage2_status == "data_received":
            await query.edit_message_text("✅ Дані вже отримані.")
        await _send_stage2_ui(user_id, order_id, context)
        return

    if data.startswith("s2_req_code_"):
        cursor.execute("SELECT stage2_status FROM orders WHERE id=?", (order_id,))
        st = cursor.fetchone()[0]
        if st != "data_received":
            await query.edit_message_text("Спочатку мають бути надані номер та email.")
            return
        _update_order(order_id, phone_code_status="requested", phone_code_session=int(datetime.utcnow().timestamp()))
        log_action(order_id, "user", "stage2_request_code")
        await query.edit_message_text("✅ Запит коду зафіксовано. Очікуйте.")
        await _notify_managers_request_code(order_id, context)
        await _send_stage2_ui(user_id, order_id, context)
        return

    if data.startswith("s2_phone_confirm_yes_") or data.startswith("s2_phone_confirm_back_"):
        if data.startswith("s2_phone_confirm_back_"):
            await query.edit_message_text("Скасовано.")
            await _send_stage2_ui(user_id, order_id, context)
            return
        _update_order(order_id, phone_verified=1, phone_code_status="confirmed")
        log_action(order_id, "user", "phone_confirm")
        if email_verified:
            _update_order(order_id, stage2_complete=1)
            log_action(order_id, "system", "stage2_complete")
        await query.edit_message_text("✅ Номер підтверджено.")
        await _send_stage2_ui(user_id, order_id, context)
        return

    if data.startswith("s2_phone_confirm_"):
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Так", callback_data=f"s2_phone_confirm_yes_{order_id}"),
             InlineKeyboardButton("Назад", callback_data=f"s2_phone_confirm_back_{order_id}")]
        ])
        await query.edit_message_text("Підтвердити, що номер верифіковано?", reply_markup=kb)
        return

    if data.startswith("s2_email_confirm_"):
        _update_order(order_id, email_verified=1)
        log_action(order_id, "user", "email_confirm")
        if phone_verified:
            _update_order(order_id, stage2_complete=1)
            log_action(order_id, "system", "stage2_complete")
        await query.edit_message_text("✅ Пошта підтверджена.")
        await _send_stage2_ui(user_id, order_id, context)
        return

    if data.startswith("s2_continue_"):
        if not (stage2_complete and phone_verified and email_verified):
            await query.edit_message_text("❌ Ще не всі умови виконані.")
            return
        cursor.execute("SELECT stage FROM orders WHERE id=?", (order_id,))
        gstage = cursor.fetchone()[0]
        new_stage = gstage + 1
        _update_order(order_id, stage=new_stage, status=f"На етапі {new_stage+1}")
        log_action(order_id, "user", "stage2_next", f"to_stage={new_stage}")
        await query.edit_message_text("✅ Переходимо далі.")
        from handlers.photo_handlers import send_instruction
        await send_instruction(user_id, context, order_id=order_id)
        return

    await query.edit_message_text("Невідома дія (Stage2).")

# ================== MANAGER CALLBACKS ==================

async def manager_stage2_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    parts = data.split("_")
    if len(parts) < 3:
        return
    action_group = parts[1]          # provide | msg
    sub_action = parts[2] if len(parts) > 3 else ""
    try:
        order_id = int(parts[-1])
    except ValueError:
        return

    cursor.execute("""SELECT user_id, stage2_status, phone_number, email,
                             phone_verified, email_verified
                      FROM orders WHERE id=?""", (order_id,))
    r = cursor.fetchone()
    if not r:
        await query.edit_message_text("Order not found.")
        return
    user_id, stage2_status, phone_number, email, phone_verified, email_verified = r

    # provide data
    if action_group == "provide" and sub_action == "data":
        if stage2_status == "idle":
            _update_order(order_id, stage2_status="waiting_manager_data")
        if stage2_status not in ("waiting_manager_data", "idle"):
            await query.edit_message_text(f"Надання даних недоступне (status={stage2_status}).")
            return
        await query.edit_message_text(
            "Надішліть номер і email (разом або окремо):\n"
            "+380931234567 user@mail.com\nабо окремими повідомленнями."
        )
        context.user_data['stage2_order_id'] = order_id
        context.user_data['stage2_partial_phone'] = None
        context.user_data['stage2_partial_email'] = None
        return STAGE2_MANAGER_WAIT_DATA

    # provide code
    if action_group == "provide" and sub_action == "code":
        if not phone_number:
            await query.edit_message_text("Спочатку потрібно надати номер та email.")
            return
        await query.edit_message_text("Введіть код (3–8 цифр).")
        context.user_data['stage2_order_id'] = order_id
        return STAGE2_MANAGER_WAIT_CODE

    # msg для користувача
    if action_group == "msg":
        # запуск стану введення повідомлення
        context.user_data['stage2_msg_order_id'] = order_id
        context.user_data['stage2_msg_user_id'] = user_id
        await query.edit_message_text("💬 Введіть текст повідомлення користувачу (одним повідомленням).")
        return STAGE2_MANAGER_WAIT_MSG

    await query.edit_message_text("Невідома дія (manager Stage2).")

# ================== Manager enters phone/email ==================

async def manager_enter_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    order_id = context.user_data.get("stage2_order_id")
    if not order_id:
        await update.message.reply_text("❌ Спочатку натисніть 'Надати дані'.")
        return ConversationHandler.END

    cursor.execute("SELECT user_id, stage2_status FROM orders WHERE id=?", (order_id,))
    r = cursor.fetchone()
    if not r:
        await update.message.reply_text("❌ Замовлення не знайдено.")
        return ConversationHandler.END
    user_id, stage2_status = r

    if stage2_status not in ("waiting_manager_data", "idle"):
        if stage2_status == "data_received":
            await update.message.reply_text("ℹ️ Дані вже надані.")
        else:
            await update.message.reply_text(f"❌ Статус не дозволяє вводити дані: {stage2_status}")
        return ConversationHandler.END

    text = (update.message.text or "").strip()

    phone_match = re.search(r"(\+?\d[\d\s\-\(\)]{7,}\d)", text)
    email_match = re.search(r"([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})", text)

    phone = None
    if phone_match:
        cleaned = re.sub(r"[\s\-\(\)]", "", phone_match.group(1))
        if PHONE_RE.match(cleaned):
            phone = cleaned

    email = email_match.group(1) if email_match and EMAIL_RE.match(email_match.group(1)) else None

    if phone:
        context.user_data['stage2_partial_phone'] = phone
    if email:
        context.user_data['stage2_partial_email'] = email

    p = context.user_data.get('stage2_partial_phone')
    e = context.user_data.get('stage2_partial_email')

    if not p and not e:
        await update.message.reply_text("❌ Не знайшов валідний номер або email. Надішліть ще раз.")
        return STAGE2_MANAGER_WAIT_DATA
    if p and not e:
        await update.message.reply_text("✅ Номер збережено. Надішліть email.")
        return STAGE2_MANAGER_WAIT_DATA
    if e and not p:
        await update.message.reply_text("✅ Email збережено. Надішліть номер.")
        return STAGE2_MANAGER_WAIT_DATA

    # Обидва є → зберігаємо
    _update_order(order_id,
                  phone_number=p,
                  email=e,
                  stage2_status="data_received")
    log_action(order_id, "manager", "provide_data", f"{p}|{e}")

    await update.message.reply_text(f"✅ Дані збережено: {p} | {e}")
    await _safe_send(context.bot, user_id,
                     f"📨 Отримано дані:\nТелефон: {p}\nEmail: {e}\n"
                     f"Можете підтвердити пошту / номер або (за потреби) натиснути '🔑 Запросити код'.")

    context.user_data.pop('stage2_partial_phone', None)
    context.user_data.pop('stage2_partial_email', None)

    await _send_stage2_ui(user_id, order_id, context)
    await _notify_managers_after_data(order_id, context)

    return ConversationHandler.END

# ================== Manager enters code ==================

async def manager_enter_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    order_id = context.user_data.get("stage2_order_id")
    if not order_id:
        await update.message.reply_text("❌ Спочатку натисніть 'Надати код'.")
        return ConversationHandler.END

    code = (update.message.text or "").strip()
    if not re.fullmatch(r"\d{3,8}", code):
        await update.message.reply_text("❌ Код має 3–8 цифр. Спробуйте ще раз.")
        return STAGE2_MANAGER_WAIT_CODE

    _update_order(order_id, phone_code_status="delivered")
    log_action(order_id, "manager", "provide_code", code)

    cursor.execute("SELECT user_id FROM orders WHERE id=?", (order_id,))
    uid = cursor.fetchone()[0]

    await update.message.reply_text("✅ Код збережено і відправлено користувачу.")
    await _safe_send(context.bot, uid,
                     f"🔐 Код: {code}\nВведіть його у застосунку і після верифікації натисніть '📞 Номер підтверджено'.")

    await _send_stage2_ui(uid, order_id, context)
    return ConversationHandler.END

# ================== Manager enters free message ==================

async def manager_enter_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    order_id = context.user_data.get("stage2_msg_order_id")
    user_id = context.user_data.get("stage2_msg_user_id")
    if not order_id or not user_id:
        await update.message.reply_text("❌ Немає контексту для повідомлення.")
        return ConversationHandler.END

    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("⚠️ Порожнє повідомлення. Введіть текст або /cancel.")
        return STAGE2_MANAGER_WAIT_MSG

    log_action(order_id, "manager", "stage2_send_message", text)
    await update.message.reply_text("✅ Повідомлення надіслано.")
    await _safe_send(update.application.bot, user_id, f"💬 Повідомлення від менеджера:\n{text}")

    context.user_data.pop("stage2_msg_order_id", None)
    context.user_data.pop("stage2_msg_user_id", None)
    return ConversationHandler.END
import re
from datetime import datetime
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from db import cursor, conn, ADMIN_GROUP_ID, log_action, logger
from states import (
    STAGE2_MANAGER_WAIT_DATA,
    STAGE2_MANAGER_WAIT_CODE,
    STAGE2_MANAGER_WAIT_MSG,
)

PHONE_RE = re.compile(r"^\+?\d{9,15}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CODE_RE = re.compile(r"^\d{3,8}$")  # 3–8 digits

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

def _get_user_active_order(user_id: int) -> Optional[tuple]:
    cursor.execute("""
        SELECT id,user_id,username,bank,action,stage,status,group_id,
               phone_number,email,phone_verified,email_verified,
               phone_code_status,phone_code_session,phone_code_last_sent_at,
               phone_code_attempts,stage2_status,stage2_restart_count,stage2_complete
        FROM orders
        WHERE user_id=? AND status!='Завершено'
        ORDER BY id DESC LIMIT 1
    """, (user_id,))
    return cursor.fetchone()

def _get_order_group_chat(order_id: int) -> int:
    cursor.execute("SELECT group_id FROM orders WHERE id=?", (order_id,))
    row = cursor.fetchone()
    return row[0] if row and row[0] else ADMIN_GROUP_ID

# ================== Safe send helper ==================

async def _safe_send(bot, chat_id: int, text: str, **kwargs):
    try:
        await bot.send_message(chat_id=chat_id, text=text, **kwargs)
    except Exception as e:
        logger.warning("Failed to send message to %s: %s", chat_id, e)

# ================== Keyboards ==================

def _manager_data_keyboard(order_id: int):
    # Початковий / очікувальний стан: можна надати дані та завжди написати юзеру
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Надати дані", callback_data=f"mgr_provide_data_{order_id}")],
        [InlineKeyboardButton("💬 Написати користувачу", callback_data=f"mgr_msg_{order_id}")]
    ])

def _manager_actions_keyboard(order_id: int):
    # Після отримання даних – можна дати код і написати юзеру
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Надати код", callback_data=f"mgr_provide_code_{order_id}")],
        [InlineKeyboardButton("💬 Написати користувачу", callback_data=f"mgr_msg_{order_id}")]
    ])

def _user_reply_keyboard(order_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Відповісти менеджеру", callback_data=f"s2_reply_{order_id}")]
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

def _set_current_stage2_order(context: ContextTypes.DEFAULT_TYPE, chat_id: int, order_id: int):
    try:
        context.application.chat_data.setdefault(chat_id, {})
        context.application.chat_data[chat_id]["stage2_current_order_id"] = order_id
    except Exception:
        pass

# ================== Notifications to manager groups ==================

async def _notify_managers_after_data(order_id: int, context: ContextTypes.DEFAULT_TYPE):
    order = _get_order_core(order_id)
    if not order:
        return
    (_, user_id, username, bank, action, *_rest) = order
    chat_id = _get_order_group_chat(order_id)
    txt = (f"📨 Дані отримано (Order {order_id}).\n"
           f"👤 @{username or 'Без_ніка'} (ID: {user_id})\n"
           f"🏦 {bank} / {action}\n"
           f"➡️ Дії: Надати код / 💬 Написати користувачу\n\n"
           f"Підказка: надішліть у чат <лише цифри 3–8> — це буде код користувачу.\n"
           f"Будь-який інший текст — повідомлення користувачу.")
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=txt,
            reply_markup=_manager_actions_keyboard(order_id)
        )
        _set_current_stage2_order(context, chat_id, order_id)
        log_action(order_id, "system", "provide_data_notify")
    except Exception as e:
        logger.warning("Failed to notify managers after data: %s", e)

async def _notify_managers_request_code(order_id: int, context: ContextTypes.DEFAULT_TYPE):
    order = _get_order_core(order_id)
    if not order:
        return
    (_, user_id, username, bank, action, *_r) = order
    chat_id = _get_order_group_chat(order_id)
    txt = (f"🔑 Запит коду (Order {order_id}).\n"
           f"👤 @{username or 'Без_ніка'} (ID: {user_id})\n"
           f"🏦 {bank} / {action}\n"
           f"➡️ Натисніть 'Надати код' або просто надішліть цифри 3–8 у чат.\n"
           f"Будь-який інший текст — повідомлення користувачу.")
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=txt,
            reply_markup=_manager_actions_keyboard(order_id)
        )
        _set_current_stage2_order(context, chat_id, order_id)
        log_action(order_id, "system", "request_code_notify")
    except Exception as e:
        logger.warning("Failed to notify managers request code: %s", e)

# ================== USER CALLBACKS (кнопки користувача) ==================

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
                chat_id = _get_order_group_chat(order_id)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"📨 Order {order_id}: користувач запросив номер і пошту.",
                    reply_markup=_manager_data_keyboard(order_id)
                )
                _set_current_stage2_order(context, chat_id, order_id)
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

    if data.startswith("s2_reply_"):
        # Просто підказка — відповідайте текстом, і його отримає менеджер (автоматичний бридж)
        await query.edit_message_text("💬 Напишіть ваше повідомлення тут — воно автоматично буде надіслане менеджеру.")
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

# ================== MANAGER CALLBACKS + MESSAGE FLOWS ==================

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

    chat_id = query.message.chat_id if query.message else ADMIN_GROUP_ID
    _set_current_stage2_order(context, chat_id, order_id)

    cursor.execute("""SELECT user_id, stage2_status, phone_number, email
                      FROM orders WHERE id=?""", (order_id,))
    r = cursor.fetchone()
    if not r:
        await query.edit_message_text("Order not found.")
        return
    user_id, stage2_status, phone_number, email = r

    # provide data
    if action_group == "provide" and sub_action == "data":
        if stage2_status == "idle":
            _update_order(order_id, stage2_status="waiting_manager_data")
        if stage2_status not in ("waiting_manager_data", "idle"):
            await query.edit_message_text(f"Надання даних недоступне (status={stage2_status}).")
            return
        await query.edit_message_text(
            "Надішліть номер і email (разом або окремо):\n"
            "+380931234567 user@mail.com\nабо окремими повідомленнями.",
            reply_markup=_manager_data_keyboard(order_id)
        )
        context.user_data['stage2_order_id'] = order_id
        context.user_data['stage2_partial_phone'] = None
        context.user_data['stage2_partial_email'] = None
        return STAGE2_MANAGER_WAIT_DATA

    # provide code
    if action_group == "provide" and sub_action == "code":
        if not phone_number:
            await query.edit_message_text("Спочатку потрібно надати номер та email.",
                                          reply_markup=_manager_data_keyboard(order_id))
            return
        await query.edit_message_text("Введіть код (3–8 цифр) одним повідомленням.",
                                      reply_markup=_manager_actions_keyboard(order_id))
        context.user_data['stage2_order_id'] = order_id
        return STAGE2_MANAGER_WAIT_CODE

    # msg: вмикаємо "режим листування" — будь-який текст із цієї групи піде користувачу як повідомлення
    if action_group == "msg":
        _set_current_stage2_order(context, chat_id, order_id)
        await query.edit_message_text(
            "💬 Режим листування активний для цього замовлення.\n"
            "— Надішліть текст у чат: він піде користувачу.\n"
            "— Надішліть лише цифри (3–8): це буде код.",
            reply_markup=_manager_actions_keyboard(order_id)
        )
        return ConversationHandler.END

    await query.edit_message_text("Невідома дія (manager Stage2).")

# Admin group free text: auto-detect code and auto-forward messages to current order
async def stage2_group_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return
    chat_id = msg.chat_id

    # Працюємо лише в групі менеджерів (або в прив'язній групі замовлення)
    # Якщо в проекті кілька груп — просто переконайтесь, що хендлер додано для кожної або використовуйте Chat filter.
    # Тут припускаємо, що цей хендлер підписаний на групи з менеджерами.
    # Захист: якщо менеджер у стані відхилення/вводу даних/коду — не перехоплюємо
    if context.user_data.get("reject_user_id") or context.user_data.get("stage2_order_id"):
        return

    text = msg.text.strip()

    # Визначити активне замовлення: з chat_data або останнє data_received
    chat_store = context.application.chat_data.get(chat_id, {})
    order_id = chat_store.get("stage2_current_order_id")

    if not order_id:
        cursor.execute("""
            SELECT id FROM orders
            WHERE stage2_status IN ('waiting_manager_data','data_received')
            ORDER BY phone_code_session DESC, id DESC LIMIT 1
        """)
        r = cursor.fetchone()
        if r:
            order_id = r[0]

    if not order_id:
        return  # немає контексту Stage2 — ігноруємо текст

    # Отримати користувача
    cursor.execute("SELECT user_id FROM orders WHERE id=?", (order_id,))
    r = cursor.fetchone()
    if not r:
        return
    user_id = r[0]

    # Якщо лише цифри -> це код
    if CODE_RE.fullmatch(text):
        _update_order(order_id, phone_code_status="delivered")
        log_action(order_id, "manager", "provide_code_auto", text)

        await msg.reply_text(f"✅ Код надіслано користувачу (Order {order_id}).",
                             reply_markup=_manager_actions_keyboard(order_id))
        await _safe_send(context.bot, user_id,
                         f"🔐 Код: {text}\nВведіть його у застосунку і після верифікації натисніть '📞 Номер підтверджено'.")
        await _send_stage2_ui(user_id, order_id, context)
        return

    # Інакше — це звичайне повідомлення менеджера
    log_action(order_id, "manager", "stage2_send_message_auto", text)
    await _safe_send(context.bot, user_id, f"💬 Повідомлення від менеджера:\n{text}",
                     reply_markup=_user_reply_keyboard(order_id))
    await msg.reply_text("📨 Відправлено користувачу.",
                         reply_markup=_manager_actions_keyboard(order_id))

# ================== Manager enters phone/email/code through states ==================

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

    await update.message.reply_text(f"✅ Дані збережено: {p} | {e}",
                                    reply_markup=_manager_actions_keyboard(order_id))
    await _safe_send(context.bot, user_id,
                     f"📨 Отримано дані:\nТелефон: {p}\nEmail: {e}\n"
                     f"Можете підтвердити пошту / номер або натиснути '🔑 Запросити код' (не обовʼязково).",
                     )
    await _send_stage2_ui(user_id, order_id, context)
    await _notify_managers_after_data(order_id, context)

    # Очистка partial
    context.user_data.pop('stage2_partial_phone', None)
    context.user_data.pop('stage2_partial_email', None)
    context.user_data.pop('stage2_order_id', None)

    return ConversationHandler.END

async def manager_enter_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    order_id = context.user_data.get("stage2_order_id")
    if not order_id:
        await update.message.reply_text("❌ Спочатку натисніть 'Надати код'.")
        return ConversationHandler.END

    code = (update.message.text or "").strip()
    if not CODE_RE.fullmatch(code):
        await update.message.reply_text("❌ Код має містити 3–8 цифр. Спробуйте ще раз.")
        return STAGE2_MANAGER_WAIT_CODE

    _update_order(order_id, phone_code_status="delivered")
    log_action(order_id, "manager", "provide_code", code)

    cursor.execute("SELECT user_id FROM orders WHERE id=?", (order_id,))
    uid = cursor.fetchone()[0]

    await update.message.reply_text("✅ Код збережено і відправлено користувачу.",
                                    reply_markup=_manager_actions_keyboard(order_id))
    await _safe_send(context.bot, uid,
                     f"🔐 Код: {code}\nВведіть його у застосунку і після верифікації натисніть '📞 Номер підтверджено'.")
    await _send_stage2_ui(uid, order_id, context)
    context.user_data.pop('stage2_order_id', None)
    return ConversationHandler.END

# ================== Bi-directional chat bridge ==================

# 1) Користувач пише текст — автоматично пересилаємо в групу менеджерів замовлення
async def stage2_user_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return
    user_id = msg.from_user.id
    text = msg.text.strip()

    order = _get_user_active_order(user_id)
    if not order:
        return
    order_id = order[0]
    group_chat_id = order[7] if order[7] else ADMIN_GROUP_ID

    # Переслати менеджеру(ам)
    header = f"💬 Повідомлення від користувача (Order {order_id}, @{order[2] or 'Без_ніка'} | ID {user_id}):"
    try:
        await context.bot.send_message(
            chat_id=group_chat_id,
            text=f"{header}\n{text}",
            reply_markup=_manager_actions_keyboard(order_id)
        )
        _set_current_stage2_order(context, group_chat_id, order_id)
        log_action(order_id, "user", "stage2_user_message", text)
    except Exception as e:
        logger.warning("Failed to forward user text to managers: %s", e)

# 2) Менеджер пише текст у групі — автоматично пересилаємо користувачу (реалізовано у stage2_group_text)

# ================== Manager free message via state (не обовʼязковий, залишено для сумісності) ==================

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
    await update.message.reply_text("✅ Повідомлення надіслано.",
                                    reply_markup=_manager_actions_keyboard(order_id))
    await _safe_send(context.bot, user_id, f"💬 Повідомлення від менеджера:\n{text}",
                     reply_markup=_user_reply_keyboard(order_id))

    context.user_data.pop("stage2_msg_order_id", None)
    context.user_data.pop("stage2_msg_user_id", None)
    return ConversationHandler.END
import re
from datetime import datetime, timedelta
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from db import cursor, conn, ADMIN_GROUP_ID, log_action, logger
from states import (
    STAGE2_MANAGER_WAIT_DATA,
    STAGE2_MANAGER_WAIT_CODE,
    STAGE2_MANAGER_WAIT_MSG,
)
from handlers.templates_store import get_template

PHONE_RE = re.compile(r"^\+?\d{9,15}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CODE_RE = re.compile(r"^\d{3,8}$")  # 3–8 цифр
ORDER_TAG_RE = re.compile(r"#(\d+)")
ORDER_ID_IN_TEXT_RE = re.compile(r"(?:OrderID|Order)\D*(\d+)")

CODE_REMINDER_MINUTES = 5

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

def _get_order_group_chat(order_id: int) -> int:
    cursor.execute("SELECT group_id FROM orders WHERE id=?", (order_id,))
    row = cursor.fetchone()
    return row[0] if row and row[0] else ADMIN_GROUP_ID

def _get_user_active_order(user_id: int):
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

# ================== Safe send helper ==================

async def _safe_send(bot, chat_id: int, text: str, **kwargs):
    try:
        await bot.send_message(chat_id=chat_id, text=text, **kwargs)
    except Exception as e:
        logger.warning("Failed to send message to %s: %s", chat_id, e)

# ================== Keyboards ==================

def _manager_data_keyboard(order_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Надати дані", callback_data=f"mgr_provide_data_{order_id}")],
        [InlineKeyboardButton("💬 Написати користувачу", callback_data=f"mgr_msg_{order_id}")]
    ])

def _manager_actions_keyboard(order_id: int):
    # Динамічна клавіатура дій менеджера:
    # - «Надати дані» показуємо, доки stage2_status != 'data_received'
    # - «Надати код» — завжди
    # - «💬 Написати користувачу» — завжди
    try:
        order = _get_order_core(order_id)
    except Exception:
        order = None

    btn_provide_data = InlineKeyboardButton("Надати дані", callback_data=f"mgr_provide_data_{order_id}")
    btn_provide_code = InlineKeyboardButton("Надати код", callback_data=f"mgr_provide_code_{order_id}")
    btn_msg = InlineKeyboardButton("💬 Написати користувачу", callback_data=f"mgr_msg_{order_id}")

    buttons = []

    if not order:
        # Якщо раптом не дістався ордер — підстрахуємось і покажемо всі кнопки
        buttons.append([btn_provide_data])
        buttons.append([btn_provide_code])
        buttons.append([btn_msg])
        return InlineKeyboardMarkup(buttons)

    # order = (id, user_id, username, bank, action, stage, status, group_id,
    #          phone_number, email, phone_verified, email_verified,
    #          phone_code_status, phone_code_session, phone_code_last_sent_at,
    #          phone_code_attempts, stage2_status, stage2_restart_count, stage2_complete)
    stage2_status = order[16]

    if stage2_status != "data_received":
        buttons.append([btn_provide_data])

    buttons.append([btn_provide_code])
    buttons.append([btn_msg])

    return InlineKeyboardMarkup(buttons)


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
    """Enhanced version that uses database tracking"""
    try:
        # Update in-memory cache
        context.application.chat_data.setdefault(chat_id, {})
        context.application.chat_data[chat_id]["stage2_current_order_id"] = order_id
        
        # Update database tracking
        from db import set_current_order_for_group, add_active_order_to_group
        
        # Check if this is a group that we manage
        cursor.execute("SELECT 1 FROM manager_groups WHERE group_id=?", (chat_id,))
        if cursor.fetchone():
            # Ensure the order is in active orders and set as current
            add_active_order_to_group(chat_id, order_id, set_as_current=True)
            
    except Exception as e:
        logger.warning("_set_current_stage2_order error: %s", e)

def _expand_template_if_any(text: str, order_id: int) -> str:
    """
    If text starts with !<key>, expand it using templates_store.
    Supports placeholders: {order_id}, {username}, {bank}, {action}.
    """
    if not text.startswith("!"):
        return text
    token = text.split()[0][1:]  # !hello -> hello
    tpl = get_template(token)
    if not tpl:
        return text  # unknown template, send as-is
    # fetch order fields
    row = _get_order_core(order_id)
    if not row:
        return tpl
    _, user_id, username, bank, action, *_ = row
    return tpl.format(
        order_id=order_id,
        username=username or "Без_ніка",
        bank=bank or "",
        action=action or ""
    )

# ================== Code reminder jobs ==================

async def _code_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    data = job.data or {}
    order_id = data.get("order_id")
    chat_id = data.get("chat_id")
    if not order_id or not chat_id:
        return
    cursor.execute("SELECT phone_code_status FROM orders WHERE id=?", (order_id,))
    r = cursor.fetchone()
    if not r:
        return
    status = r[0]
    if status == "requested":
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⏰ Нагадування: користувач по Order {order_id} очікує код уже {CODE_REMINDER_MINUTES} хв."
            )
        except Exception:
            pass

def _schedule_code_reminder(order_id: int, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    try:
        job_queue = context.application.job_queue
        # Cancel old
        _cancel_code_reminder(order_id, context)
        job_queue.run_once(
            _code_reminder_job,
            when=timedelta(minutes=CODE_REMINDER_MINUTES),
            data={"order_id": order_id, "chat_id": chat_id},
            name=f"code_reminder_{order_id}"
        )
    except Exception as e:
        logger.warning("schedule code reminder failed: %s", e)

def _cancel_code_reminder(order_id: int, context: ContextTypes.DEFAULT_TYPE):
    try:
        job_queue = context.application.job_queue
        for job in job_queue.get_jobs_by_name(f"code_reminder_{order_id}"):
            job.schedule_removal()
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
           f"Будь-який інший текст — повідомлення користувачу.\n"
           f"Також можна: #<id> або /o <id> щоб перемкнутися на інший ордер.")
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
           f"➡️ Надішліть цифри 3–8 у чат — це буде код. Будь-який інший текст — повідомлення користувачу.")
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=txt,
            reply_markup=_manager_actions_keyboard(order_id)
        )
        _set_current_stage2_order(context, chat_id, order_id)
        _schedule_code_reminder(order_id, chat_id, context)
        log_action(order_id, "system", "request_code_notify")
    except Exception as e:
        logger.warning("Failed to notify managers request code: %s", e)

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
        _cancel_code_reminder(order_id, context)
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

    if action_group == "provide" and sub_action == "code":
        if not phone_number:
            await query.edit_message_text("Спочатку потрібно надати номер та email.",
                                          reply_markup=_manager_data_keyboard(order_id))
            return
        await query.edit_message_text("Введіть код (3–8 цифр) одним повідомленням.",
                                      reply_markup=_manager_actions_keyboard(order_id))
        context.user_data['stage2_order_id'] = order_id
        return STAGE2_MANAGER_WAIT_CODE

    if action_group == "msg":
        _set_current_stage2_order(context, chat_id, order_id)
        await query.edit_message_text(
            "💬 Режим листування активний для цього замовлення.\n"
            "— Надішліть текст у чат: він піде користувачу.\n"
            "— Надішліть лише цифри (3–8): це буде код.\n"
            "— Можна використовувати шаблони: !hello, !wait_code, !after_code ...",
            reply_markup=_manager_actions_keyboard(order_id)
        )
        return ConversationHandler.END

    await query.edit_message_text("Невідома дія (manager Stage2).")

# Admin group free text: auto-detect code, auto-forward messages, #id switch, reply-based switch, templates
async def stage2_group_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return
    chat_id = msg.chat_id
    text = msg.text.strip()

    # 0) Set current order by tag or reply
    tag = ORDER_TAG_RE.search(text) or (ORDER_ID_IN_TEXT_RE.search(msg.reply_to_message.text) if msg.reply_to_message and msg.reply_to_message.text else None)
    if tag:
        try:
            order_id = int(tag.group(1))
            _set_current_stage2_order(context, chat_id, order_id)
            await msg.reply_text(f"✅ Поточне замовлення встановлено: Order {order_id}")
            return
        except Exception:
            pass

    # 1) Determine current order
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
        return  # no context

    # 2) Get user id
    cursor.execute("SELECT user_id FROM orders WHERE id=?", (order_id,))
    r = cursor.fetchone()
    if not r:
        return
    user_id = r[0]

    # 3) Code?
    if CODE_RE.fullmatch(text):
        _update_order(order_id, phone_code_status="delivered")
        _cancel_code_reminder(order_id, context)
        log_action(order_id, "manager", "provide_code_auto", text)

        await msg.reply_text(f"✅ Код надіслано користувачу (Order {order_id}).",
                             reply_markup=_manager_actions_keyboard(order_id))
        await _safe_send(context.bot, user_id,
                         f"🔐 Код: {text}\nВведіть його у застосунку і після верифікації натисніть '📞 Номер підтверджено'.")
        await _send_stage2_ui(user_id, order_id, context)
        return

    # 4) Template expand if "!key"
    text = _expand_template_if_any(text, order_id)

    # 5) Manager free message
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
            await update.message.reply_text("ℹ️ Дані вже надані.", reply_markup=_manager_actions_keyboard(order_id))
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
        await update.message.reply_text(
            "❌ Не знайшов валідний номер або email. Надішліть ще раз.",
            reply_markup=_manager_data_keyboard(order_id)
        )
        return STAGE2_MANAGER_WAIT_DATA
    if p and not e:
        await update.message.reply_text(
            "✅ Номер збережено. Надішліть email.",
            reply_markup=_manager_data_keyboard(order_id)
        )
        return STAGE2_MANAGER_WAIT_DATA
    if e and not p:
        await update.message.reply_text(
            "✅ Email збережено. Надішліть номер.",
            reply_markup=_manager_data_keyboard(order_id)
        )
        return STAGE2_MANAGER_WAIT_DATA

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
    _cancel_code_reminder(order_id, context)
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

async def stage2_user_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return
    if update.effective_chat and update.effective_chat.type != "private":
        return

    user_id = msg.from_user.id
    text = msg.text.strip()

    order = _get_user_active_order(user_id)
    if not order:
        return
    order_id = order[0]
    group_chat_id = order[7] if order[7] else ADMIN_GROUP_ID

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

# ================== Manager free message via state (optional) ==================

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

# ================== Quick command: /o <id> in groups ==================

async def set_current_order_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced /o command with better feedback and group support"""
    msg = update.message
    if not msg:
        return
        
    if not context.args:
        # Show current active orders for this group
        chat_id = msg.chat_id
        from db import get_group_active_orders, get_current_order_for_group
        
        # Check if this is a managed group
        cursor.execute("SELECT name FROM manager_groups WHERE group_id=?", (chat_id,))
        group_info = cursor.fetchone()
        
        if group_info:
            active_orders = get_group_active_orders(chat_id)
            current_order = get_current_order_for_group(chat_id)
            
            if not active_orders:
                await msg.reply_text("📭 Немає активних замовлень у цій групі.")
                return
            
            text = f"📋 <b>Активні замовлення ({group_info[0]}):</b>\n\n"
            
            for order_id, is_current in active_orders:
                # Get order details
                cursor.execute("""
                    SELECT user_id, username, bank, action, status 
                    FROM orders WHERE id=?
                """, (order_id,))
                order_data = cursor.fetchone()
                
                if order_data:
                    user_id, username, bank, action, status = order_data
                    current_mark = "➤ " if is_current else "  "
                    text += f"{current_mark}<b>#{order_id}</b> @{username or 'Без_ніка'} | {bank} {action} | <i>{status}</i>\n"
            
            text += f"\n💡 Поточне: #{current_order or 'не встановлено'}\n"
            text += "Використання: <code>/o &lt;order_id&gt;</code> для перемикання"
            
            await msg.reply_text(text, parse_mode="HTML")
        else:
            await msg.reply_text("Використання: /o <order_id>")
        return
    
    try:
        order_id = int(context.args[0])
    except Exception:
        await msg.reply_text("❌ order_id має бути числом.")
        return
        
    # Check if order exists
    cursor.execute("SELECT user_id, username, bank, action, status FROM orders WHERE id=?", (order_id,))
    order_data = cursor.fetchone()
    if not order_data:
        await msg.reply_text("❌ Замовлення не знайдено.")
        return
    
    user_id, username, bank, action, status = order_data
    chat_id = msg.chat_id
    
    # Set as current order
    _set_current_stage2_order(context, chat_id, order_id)
    
    await msg.reply_text(
        f"✅ <b>Поточне замовлення встановлено:</b>\n"
        f"🆔 Order #{order_id}\n"
        f"👤 @{username or 'Без_ніка'} (ID: {user_id})\n"
        f"🏦 {bank} / {action}\n"
        f"📍 {status}",
        parse_mode="HTML",
        reply_markup=_manager_actions_keyboard(order_id)
    )
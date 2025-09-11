import re
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from db import cursor, conn, ADMIN_GROUP_ID, log_action
from states import STAGE2_MANAGER_WAIT_DATA, STAGE2_MANAGER_WAIT_CODE

PHONE_RE = re.compile(r"^\+?\d{9,15}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

RATE_SECONDS_CODE = 30  # мінімальний інтервал між запитами коду

# ---------------- Utilities ----------------

def _get_order(order_id: int):
    cursor.execute("SELECT * FROM orders WHERE id=?", (order_id,))
    return cursor.fetchone()

def _get_order_core(order_id: int):
    cursor.execute("""SELECT id,user_id,username,bank,action,stage,status,group_id,
        phone_number,email,phone_verified,email_verified,phone_code_status,phone_code_session,
        phone_code_last_sent_at,phone_code_attempts,stage2_status,stage2_restart_count,stage2_complete
        FROM orders WHERE id=?""", (order_id,))
    return cursor.fetchone()

def _update_order(order_id: int, **fields):
    keys = ", ".join(f"{k}=?" for k in fields.keys())
    vals = list(fields.values())
    vals.append(order_id)
    cursor.execute(f"UPDATE orders SET {keys} WHERE id=?", vals)
    conn.commit()

def _render_stage2_keyboard(order):
    (oid, user_id, username, bank, action, stage, status, group_id,
     phone_number, email, phone_verified, email_verified,
     phone_code_status, phone_code_session, phone_code_last_sent_at,
     phone_code_attempts, stage2_status, stage2_restart_count, stage2_complete) = order

    buttons = []
    # Core status logic:
    if stage2_complete:
        buttons.append([InlineKeyboardButton("⏭ Перейти далі", callback_data=f"s2_continue_{oid}")])
    else:
        # stage2 not complete
        if stage2_status in ("idle", "restarted"):
            buttons.append([InlineKeyboardButton("📄 Запросити дані", callback_data=f"s2_req_data_{oid}")])
        elif stage2_status in ("waiting_manager_data",):
            buttons.append([InlineKeyboardButton("⏳ Очікуємо дані (оновити)", callback_data=f"s2_req_data_{oid}")])
        elif stage2_status in ("data_received",):
            # Show data summary if available
            if phone_number or email:
                # Request code allowed any time
                buttons_row = []
                buttons_row.append(InlineKeyboardButton("🔑 Запросити код", callback_data=f"s2_req_code_{oid}"))
                buttons.append(buttons_row)
                buttons2 = []
                buttons2.append(InlineKeyboardButton("✅ Підтвердити пошту", callback_data=f"s2_email_confirm_{oid}"))
                buttons2.append(InlineKeyboardButton("📞 Номер підтверджено", callback_data=f"s2_phone_confirm_{oid}"))
                buttons.append(buttons2)
                buttons.append([InlineKeyboardButton("♻️ Перезапустити дані", callback_data=f"s2_restart_{oid}")])
            else:
                buttons.append([InlineKeyboardButton("🔁 Дані ще не надійшли (оновити)", callback_data=f"s2_req_data_{oid}")])

        # If both verified -> show continue
        if not stage2_complete and phone_verified and email_verified:
            buttons.append([InlineKeyboardButton("⏭ Перейти далі", callback_data=f"s2_continue_{oid}")])

    return InlineKeyboardMarkup(buttons)

async def _send_stage2_ui(user_id: int, order_id: int, context: ContextTypes.DEFAULT_TYPE):
    order = _get_order_core(order_id)
    if not order:
        try:
            await context.bot.send_message(chat_id=user_id, text="❌ Замовлення не знайдено (Stage2).")
        except Exception:
            pass
        return
    (_, _, username, bank, action, stage, status, group_id,
     phone_number, email, phone_verified, email_verified,
     phone_code_status, phone_code_session, phone_code_last_sent_at,
     phone_code_attempts, stage2_status, stage2_restart_count, stage2_complete) = order

    lines = ["🔐 Етап 2: Дані для реєстрації\n"]
    lines.append(f"Банк: {bank} / {action}")
    lines.append(f"Статус етапу: {stage2_status}")
    if phone_number:
        lines.append(f"Телефон: {phone_number} ({'✅' if phone_verified else '❌'})")
    if email:
        lines.append(f"Email: {email} ({'✅' if email_verified else '❌'})")
    if phone_code_status and phone_code_status != 'none':
        lines.append(f"Статус коду: {phone_code_status}")
    if stage2_complete:
        lines.append("✅ Етап 2 завершено. Можна продовжити.")
    text = "\n".join(lines)
    kb = _render_stage2_keyboard(order)
    try:
        await context.bot.send_message(chat_id=user_id, text=text, reply_markup=kb)
    except Exception:
        pass

# ---------------- User Callbacks ----------------

async def user_stage2_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    try:
        action, order_id_str = data.split("_", 2)[1:]  # s2_<act>_<oid> or s2_<act>_<oid>_<rest>
    except Exception:
        # fallback robust parsing
        parts = data.split("_")
        if len(parts) < 3:
            return
        order_id_str = parts[-1]
        action = parts[1]
    try:
        order_id = int(order_id_str)
    except:
        return

    cursor.execute("SELECT user_id, stage2_status, phone_verified, email_verified, stage2_complete, phone_code_status, phone_code_last_sent_at FROM orders WHERE id=?", (order_id,))
    row = cursor.fetchone()
    if not row:
        await query.edit_message_text("❌ Замовлення не знайдено.")
        return
    order_user_id, stage2_status, phone_verified, email_verified, stage2_complete, phone_code_status, phone_code_last_sent_at = row
    if order_user_id != user_id:
        await query.edit_message_text("⛔ Це не ваше замовлення.")
        return

    # Actions
    if data.startswith("s2_req_data_"):
        if stage2_status in ("idle", "restarted"):
            _update_order(order_id, stage2_status="waiting_manager_data")
            log_action(order_id, "user", "stage2_request_data")
            # notify manager group
            try:
                await context.bot.send_message(chat_id=ADMIN_GROUP_ID,
                                               text=f"📨 Order {order_id}: користувач запросив номер і пошту.")
            except Exception:
                pass
            await query.edit_message_text("🔄 Запит відправлено менеджеру. Очікуйте.", reply_markup=None)
        elif stage2_status == "waiting_manager_data":
            await query.edit_message_text("⏳ Дані вже запитані. Очікуємо менеджера.")
        elif stage2_status == "data_received":
            await query.edit_message_text("✅ Дані вже отримані. Оновлюю інтерфейс...")
        await _send_stage2_ui(user_id, order_id, context)
        return

    if data.startswith("s2_req_code_"):
        # must have data_received
        if stage2_status != "data_received":
            await query.edit_message_text("Спочатку запросіть та отримайте дані.")
            return
        # rate limit
        if phone_code_last_sent_at:
            try:
                last_dt = datetime.fromisoformat(phone_code_last_sent_at)
                if last_dt + timedelta(seconds=RATE_SECONDS_CODE) > datetime.utcnow():
                    wait_sec = int((last_dt + timedelta(seconds=RATE_SECONDS_CODE) - datetime.utcnow()).total_seconds())
                    await query.edit_message_text(f"⏳ Зачекайте {wait_sec}s перед повторним запитом коду.")
                    return
            except:
                pass
        new_session = int(datetime.utcnow().timestamp())
        _update_order(order_id,
                      phone_code_status="requested",
                      phone_code_session=new_session,
                      phone_code_last_sent_at=datetime.utcnow().isoformat())
        log_action(order_id, "user", "stage2_request_code", f"session={new_session}")
        try:
            await context.bot.send_message(chat_id=ADMIN_GROUP_ID,
                                           text=f"🔑 Order {order_id}: користувач запросив код (session {new_session}).",
                                           reply_markup=_manager_code_inline(order_id))
        except Exception:
            pass
        await query.edit_message_text("✅ Запит коду відправлено. Очікуйте. (Можете натиснути ще раз пізніше)")
        await _send_stage2_ui(user_id, order_id, context)
        return

    if data.startswith("s2_phone_confirm_yes_") or data.startswith("s2_phone_confirm_back_"):
        if data.startswith("s2_phone_confirm_back_"):
            await query.edit_message_text("Скасовано підтвердження номера.")
            await _send_stage2_ui(user_id, order_id, context)
            return
        # confirm
        _update_order(order_id, phone_verified=1, phone_code_status="confirmed")
        log_action(order_id, "user", "phone_confirm")
        await query.edit_message_text("✅ Номер підтверджено.")
        # If both verified -> stage2_complete
        cursor.execute("SELECT email_verified FROM orders WHERE id=?", (order_id,))
        ev = cursor.fetchone()[0]
        if ev:
            _update_order(order_id, stage2_complete=1)
            log_action(order_id, "system", "stage2_complete")
        await _send_stage2_ui(user_id, order_id, context)
        return

    if data.startswith("s2_phone_confirm_"):
        # ask confirmation
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Так", callback_data=f"s2_phone_confirm_yes_{order_id}"),
             InlineKeyboardButton("Назад", callback_data=f"s2_phone_confirm_back_{order_id}")]
        ])
        await query.edit_message_text("Ви впевнені, що номер підтверджено у банку?", reply_markup=kb)
        return

    if data.startswith("s2_email_confirm_"):
        # mark email verified
        _update_order(order_id, email_verified=1)
        log_action(order_id, "user", "email_confirm")
        cursor.execute("SELECT phone_verified FROM orders WHERE id=?", (order_id,))
        pv = cursor.fetchone()[0]
        if pv:
            _update_order(order_id, stage2_complete=1)
            log_action(order_id, "system", "stage2_complete")
        await query.edit_message_text("✅ Пошта підтверджена.")
        await _send_stage2_ui(user_id, order_id, context)
        return

    if data.startswith("s2_restart_yes_") or data.startswith("s2_restart_back_"):
        if data.startswith("s2_restart_back_"):
            await query.edit_message_text("Перезапуск скасовано.")
            await _send_stage2_ui(user_id, order_id, context)
            return
        # reset
        _update_order(order_id,
                      stage2_status="restarted",
                      phone_number=None,
                      email=None,
                      phone_verified=0,
                      email_verified=0,
                      phone_code_status="none",
                      stage2_complete=0,
                      stage2_restart_count=int(stage2_status != "idle") + 1)
        log_action(order_id, "user", "stage2_restart")
        await query.edit_message_text("♻️ Етап даних перезапущено.")
        await _send_stage2_ui(user_id, order_id, context)
        return

    if data.startswith("s2_restart_"):
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Так", callback_data=f"s2_restart_yes_{order_id}"),
             InlineKeyboardButton("Назад", callback_data=f"s2_restart_back_{order_id}")]
        ])
        await query.edit_message_text("⚠️ Перезапустити дані? Підтвердження номера/пошти буде втрачено.", reply_markup=kb)
        return

    if data.startswith("s2_continue_"):
        # Verify stage2_complete
        if not stage2_complete or not (phone_verified and email_verified):
            await query.edit_message_text("❌ Ще не всі умови виконані.")
            return
        # Advance global stage
        cursor.execute("SELECT stage FROM orders WHERE id=?", (order_id,))
        gstage = cursor.fetchone()[0]
        new_stage = gstage + 1
        _update_order(order_id, stage=new_stage, status=f"На етапі {new_stage+1}")
        log_action(order_id, "user", "stage2_next", f"to_stage={new_stage}")
        await query.edit_message_text("✅ Переходимо далі.")
        # import send_instruction lazily to avoid circular
        from handlers.photo_handlers import send_instruction
        await send_instruction(user_id, context, order_id=order_id)
        return

    # fallback
    await query.edit_message_text("Невідома дія.")
    return

# ---------------- Manager side ----------------

def _manager_data_inline(order_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Надати дані", callback_data=f"mgr_provide_data_{order_id}")],
        [InlineKeyboardButton("Перезапустити Stage2", callback_data=f"mgr_restart_stage2_{order_id}")]
    ])

def _manager_code_inline(order_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Надати код", callback_data=f"mgr_provide_code_{order_id}")],
        [InlineKeyboardButton("Телефон підтверджено", callback_data=f"mgr_force_phone_{order_id}")],
        [InlineKeyboardButton("Пошта підтверджена", callback_data=f"mgr_force_email_{order_id}")],
        [InlineKeyboardButton("Перезапустити Stage2", callback_data=f"mgr_restart_stage2_{order_id}")]
    ])

async def manager_stage2_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    parts = data.split("_")
    if len(parts) < 3:
        return
    action = parts[1]
    try:
        order_id = int(parts[-1])
    except:
        return

    cursor.execute("SELECT user_id, stage2_status FROM orders WHERE id=?", (order_id,))
    r = cursor.fetchone()
    if not r:
        await query.edit_message_text("Order not found.")
        return
    user_id, stage2_status = r

    if action == "provide":
        # mgr_provide_data
        if stage2_status not in ("waiting_manager_data", "idle", "restarted"):
            await query.edit_message_text("Дані вже надано або етап у стані: " + stage2_status)
            return
        await query.edit_message_text(
            "Введіть номер та email у форматі:\nТелефон: +380XXXXXXXXX\nEmail: example@mail.com")
        context.user_data['stage2_order_id'] = order_id
        return STAGE2_MANAGER_WAIT_DATA

    if action == "provide" and "code" in parts:
        # safety fallback
        pass

    if action == "provide" and "data" in parts:
        pass

    if action == "provide" and "code" not in parts:
        pass

    if action == "provide" and "data" not in parts:
        pass

    if action == "provide" and "code" in data:
        pass

    if action == "provide" and "data" in data:
        pass

    if action == "provide" and "code" not in data and "data" not in data:
        pass

    if action == "provide" and "code" not in data:
        pass

    # Manager provide code
    if action == "provide" and "code" in data:
        # not used because pattern is mgr_provide_code_
        pass

    if action == "provide" and "data" in data:
        pass

    # precise actions
    if action == "provide" and "data" in data:
        pass  # (already handled)

    if action == "provide" and "code" in data:
        pass

    if parts[1] == "provide" and parts[2] == "data":
        # Already handled above
        return

    if parts[1] == "provide" and parts[2] == "code":
        # mgr_provide_code_{order_id}
        await query.edit_message_text("Введіть код (лише цифри).")
        context.user_data['stage2_order_id'] = order_id
        return STAGE2_MANAGER_WAIT_CODE

    if action == "force":
        # force_phone / force_email
        if parts[2] == "phone":
            from_user = user_id
            cursor.execute("SELECT email_verified FROM orders WHERE id=?", (order_id,))
            ev = cursor.fetchone()[0]
            _update_order(order_id, phone_verified=1, phone_code_status="confirmed")
            if ev:
                _update_order(order_id, stage2_complete=1)
            log_action(order_id, "manager", "force_phone")
            try:
                await update.callback_query.edit_message_text("Телефон підтверджено вручну.")
            except Exception:
                pass
            try:
                await update.callback_query.bot.send_message(chat_id=from_user, text="📞 Ваш номер підтверджено менеджером.")
            except Exception:
                pass
            return
        if parts[2] == "email":
            cursor.execute("SELECT phone_verified FROM orders WHERE id=?", (order_id,))
            pv = cursor.fetchone()[0]
            _update_order(order_id, email_verified=1)
            if pv:
                _update_order(order_id, stage2_complete=1)
            log_action(order_id, "manager", "force_email")
            try:
                await update.callback_query.edit_message_text("Пошта підтверджена вручну.")
            except Exception:
                pass
            try:
                await update.callback_query.bot.send_message(chat_id=user_id, text="📧 Ваша пошта підтверджена менеджером.")
            except Exception:
                pass
            return

    if action == "restart":
        _update_order(order_id,
                      stage2_status="restarted",
                      phone_number=None,
                      email=None,
                      phone_verified=0,
                      email_verified=0,
                      phone_code_status="none",
                      stage2_complete=0)
        log_action(order_id, "manager", "stage2_restart")
        try:
            await query.edit_message_text("Stage2 перезапущено менеджером.")
        except Exception:
            pass
        try:
            await query.bot.send_message(chat_id=user_id, text="⚠️ Етап даних перезапущено менеджером.")
        except Exception:
            pass
        return

    await query.edit_message_text("Невідома дія.")

async def manager_enter_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    order_id = context.user_data.get("stage2_order_id")
    if not order_id:
        await update.message.reply_text("Немає order_id в контексті.")
        return ConversationHandler.END

    # parse
    phone_match = re.search(r"(\+?\d{9,15})", text)
    email_match = re.search(r"([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})", text)
    phone = phone_match.group(1) if phone_match else None
    email = email_match.group(1) if email_match else None
    if phone and not PHONE_RE.match(phone):
        phone = None
    if email and not EMAIL_RE.match(email):
        email = None
    if not phone or not email:
        await update.message.reply_text("❌ Формат не розпізнано. Надішліть у повідомленні і номер, і email.")
        return STAGE2_MANAGER_WAIT_DATA

    _update_order(order_id,
                  phone_number=phone,
                  email=email,
                  stage2_status="data_received")
    log_action(order_id, "manager", "provide_data", f"{phone}|{email}")
    cursor.execute("SELECT user_id FROM orders WHERE id=?", (order_id,))
    uid = cursor.fetchone()[0]
    try:
        await update.message.reply_text("✅ Дані збережено.")
    except Exception:
        pass
    try:
        await update.message.bot.send_message(chat_id=uid,
                                              text=f"📨 Отримано дані:\nТелефон: {phone}\nEmail: {email}")
    except Exception:
        pass
    return ConversationHandler.END

async def manager_enter_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = (update.message.text or "").strip()
    order_id = context.user_data.get("stage2_order_id")
    if not order_id:
        await update.message.reply_text("Немає order_id в контексті.")
        return ConversationHandler.END
    if not re.fullmatch(r"\d{3,8}", code):
        await update.message.reply_text("❌ Код має бути лише цифри (3-8). Надішліть ще раз.")
        return STAGE2_MANAGER_WAIT_CODE

    # Update order
    _update_order(order_id, phone_code_status="delivered")
    log_action(order_id, "manager", "provide_code", code)
    cursor.execute("SELECT user_id FROM orders WHERE id=?", (order_id,))
    uid = cursor.fetchone()[0]
    try:
        await update.message.reply_text("✅ Код збережено.")
    except Exception:
        pass
    try:
        await update.message.bot.send_message(chat_id=uid,
                                              text=f"🔐 Код для підтвердження надійшов. Введіть його в застосунку і натисніть '📞 Номер підтверджено'.")
    except Exception:
        pass
    return ConversationHandler.END
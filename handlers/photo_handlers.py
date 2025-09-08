import os
import asyncio
from typing import List, Tuple, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from db import cursor, conn, ADMIN_GROUP_ID, logger
from states import user_states, find_age_requirement

# States for ConversationHandler
REJECT_REASON, MANAGER_MESSAGE = range(2)

# Debounce/aggregation for photo albums and series
DEBOUNCE_SECONDS = 1.8
# album_key -> list[Tuple[file_id, file_unique_id]]
pending_albums: dict[Tuple[int, int, int, int], List[Tuple[str, str]]] = {}
# album_key -> asyncio.Task
pending_timers: dict[Tuple[int, int, int, int], asyncio.Task] = {}


# ============= Core handlers (photos review flow) =============

async def handle_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Accept one or many screenshots from user (single, series, or Telegram album).
    Aggregate them per (user, order, stage, media_group_id) and send to managers once.
    Only the largest PhotoSize of a Telegram photo is stored/sent.
    """
    msg = update.message
    if not msg or not msg.photo:
        return

    user = msg.from_user
    user_id = user.id
    username = (user.username or "").strip() or "Без_ніка"

    # Validate session/state
    state = user_states.get(user_id)
    if not state:
        await msg.reply_text("Спочатку оберіть банк командою /start")
        return

    order_id = state.get("order_id")
    if not order_id:
        cursor.execute("SELECT id FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 1", (user_id,))
        r = cursor.fetchone()
        if not r:
            await msg.reply_text("Помилка: замовлення не знайдено в базі.")
            return
        order_id = r[0]
        user_states[user_id]["order_id"] = order_id

    # We store photos in DB as 1-based stage for clarity in admin messages
    current_stage_db = (state.get("stage", 0) if state else 0) + 1

    # Take only the largest PhotoSize for this message
    largest = msg.photo[-1]
    file_id = largest.file_id
    file_unique_id = largest.file_unique_id

    # Grouping key: user, order, stage, media_group (or fallback to message_id)
    media_group_id = getattr(msg, "media_group_id", None)
    group_discriminator = media_group_id if media_group_id is not None else msg.message_id
    album_key = (user_id, order_id, current_stage_db, group_discriminator)

    # Aggregate this photo in memory; prevent duplicates by file_unique_id within the album
    album_list = pending_albums.setdefault(album_key, [])
    if file_unique_id not in [fu for _, fu in album_list]:
        album_list.append((file_id, file_unique_id))

    # Debounce: cancel previous timer and start a fresh one
    prev_timer = pending_timers.get(album_key)
    if prev_timer and not prev_timer.done():
        prev_timer.cancel()

    pending_timers[album_key] = context.application.create_task(
        _debounced_send_album(album_key, username, context)
    )

    # Inform user
    try:
        await msg.reply_text("✅ Ваші скріни на перевірці. Очікуйте рішення менеджера.")
    except Exception:
        pass


async def _debounced_send_album(album_key: Tuple[int, int, int, int], username: str, context: ContextTypes.DEFAULT_TYPE):
    """After debounce, persist album photos, link replacements for rejected ones, and send to managers group."""
    try:
        await asyncio.sleep(DEBOUNCE_SECONDS)
    except asyncio.CancelledError:
        return

    user_id, order_id, stage_db, _ = album_key
    # Pull the album from memory
    photos = pending_albums.pop(album_key, [])
    pending_timers.pop(album_key, None)

    if not photos:
        return

    # Prepare DB state
    # 1) Get list of currently active rejected photos for this order/stage (to pair with replacements)
    cursor.execute(
        "SELECT id FROM order_photos WHERE order_id=? AND stage=? AND active=1 AND confirmed=-1 ORDER BY id ASC",
        (order_id, stage_db),
    )
    rejected_ids = [row[0] for row in cursor.fetchall()]

    inserted: List[Tuple[str, int]] = []  # (file_id, photo_db_id)

    for file_id, file_unique_id in photos:
        # Deduplicate by unique id within this order+stage (regardless of active)
        cursor.execute(
            "SELECT COUNT(*) FROM order_photos WHERE order_id=? AND stage=? AND file_unique_id=?",
            (order_id, stage_db, file_unique_id),
        )
        exists = cursor.fetchone()[0] > 0
        if exists:
            # Skip exact duplicates to avoid spam
            continue

        replace_of: Optional[int] = None
        if rejected_ids:
            # Consume one rejected item as "to be replaced"
            replace_of = rejected_ids.pop(0)
            # Deactivate that rejected record so it doesn't block stage completion anymore
            cursor.execute("UPDATE order_photos SET active=0 WHERE id=?", (replace_of,))

        cursor.execute(
            "INSERT INTO order_photos (order_id, stage, file_id, file_unique_id, confirmed, active, reason, replace_of) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (order_id, stage_db, file_id, file_unique_id, 0, 1, None, replace_of),
        )
        photo_db_id = cursor.lastrowid
        inserted.append((file_id, photo_db_id))

    if not inserted:
        # Nothing new to send
        conn.commit()
        return

    # Update order status to "waiting for review"
    try:
        cursor.execute(
            "UPDATE orders SET status=? WHERE id=?",
            (f"Очікує перевірки (етап {stage_db})", order_id),
        )
    except Exception:
        pass

    conn.commit()

    # Send each newly inserted photo to admin group with approve/reject
    total_photos = len(inserted)
    for idx, (file_id, photo_db_id) in enumerate(inserted, start=1):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Підтвердити", callback_data=f"approve_{user_id}_{photo_db_id}"),
             InlineKeyboardButton("❌ Відхилити", callback_data=f"reject_{user_id}_{photo_db_id}")],
            # Optionally extend with more actions:
            # [InlineKeyboardButton("↪️ Пропустити етап", callback_data=f"skip_{user_id}_{stage_db}")],
            # [InlineKeyboardButton("🏁 Завершити замовлення", callback_data=f"finish_{user_id}")],
            # [InlineKeyboardButton("💬 Написати повідомлення", callback_data=f"msg_{user_id}")]
        ])

        # Fetch fresh state in case it changed
        st = user_states.get(user_id, {})
        bank = st.get("bank", "—")
        action = st.get("action", "—")

        caption = (
            f"📌 <b>Перевірка скріну ({idx} із {total_photos})</b>\n"
            f"👤 Користувач: @{username} (ID: {user_id})\n"
            f"🏦 Банк: {bank}\n"
            f"🔄 Операція: {action}\n"
            f"📍 Етап: {stage_db}\n"
            f"🆔 ID скріну: {photo_db_id}"
        )
        try:
            await context.bot.send_photo(
                chat_id=ADMIN_GROUP_ID,
                photo=file_id,
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        except Exception as e:
            logger.warning("Не вдалося переслати фото в адмін-групу: %s", e)


async def handle_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Inline buttons in the admin group:
    - approve_{user_id}_{photo_db_id}
    - reject_{user_id}_{photo_db_id}
    """
    query = update.callback_query
    await query.answer()
    raw = query.data

    try:
        action, str_user_id, str_photo_db_id = raw.split("_")
        user_id = int(str_user_id)
        photo_db_id = int(str_photo_db_id)
    except Exception:
        try:
            await query.edit_message_caption(caption="⚠️ Некоректні дані.")
        except Exception:
            pass
        return

    # Ensure local cache of user's state exists
    state = user_states.get(user_id)
    if not state:
        cursor.execute(
            "SELECT id, username, bank, action, stage FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 1",
            (user_id,),
        )
        r = cursor.fetchone()
        if r:
            order_id, username, bank, action_db, stage0 = r[0], (r[1] or "Без_ніка"), r[2], r[3], r[4]
            user_states[user_id] = {
                "order_id": order_id,
                "bank": bank,
                "action": action_db,
                "stage": stage0,
                "age_required": find_age_requirement(bank, action_db),
                "username": username,
            }
        else:
            try:
                await query.edit_message_caption(caption="⚠️ Користувача не знайдено в сесії")
            except Exception:
                pass
            return

    order_id = user_states[user_id]["order_id"]
    stage_db = user_states[user_id]["stage"] + 1  # photos stored with 1-based stage

    if action == "approve":
        cursor.execute("UPDATE order_photos SET confirmed=1 WHERE id=?", (photo_db_id,))
        conn.commit()
        try:
            await query.edit_message_caption(caption="✅ Скрін підтверджено менеджером.")
        except Exception:
            pass

        # Evaluate stage completion after approval
        await _evaluate_stage_and_notify(user_id, order_id, stage_db, context)
        return ConversationHandler.END

    elif action == "reject":
        context.user_data['reject_user_id'] = user_id
        context.user_data['photo_db_id'] = photo_db_id
        try:
            await query.edit_message_caption(caption="❌ Введіть у чаті причину відхилення цього скріну.")
        except Exception:
            pass
        return REJECT_REASON

    # In case of unknown action
    return ConversationHandler.END


async def reject_reason_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin writes the reason after pressing Reject button."""
    user_id = context.user_data.get('reject_user_id')
    photo_db_id = context.user_data.get('photo_db_id')
    if not user_id or not photo_db_id:
        try:
            await update.message.reply_text("⚠️ Немає контексту для відхилення.")
        except Exception:
            pass
        return ConversationHandler.END

    reason = update.message.text.strip() if update.message and update.message.text else ""
    if not reason:
        reason = "Не вказано"

    cursor.execute("UPDATE order_photos SET confirmed=-1, reason=? WHERE id=?", (reason, photo_db_id))
    conn.commit()

    try:
        await update.message.reply_text("❌ Причину відхилення збережено.")
    except Exception:
        pass

    # Evaluate stage completion after rejection with reason
    state = user_states.get(user_id)
    if state:
        order_id = state["order_id"]
        stage_db = state["stage"] + 1
        await _evaluate_stage_and_notify(user_id, order_id, stage_db, context)

    return ConversationHandler.END


async def manager_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Optional: manager can send a freeform message to user (if you add a button for it)."""
    user_id = context.user_data.get('msg_user_id')
    if not user_id:
        return ConversationHandler.END
    message = update.message.text
    try:
        await context.bot.send_message(chat_id=user_id, text=f"💬 Повідомлення менеджера: {message}")
        await update.message.reply_text("✅ Повідомлення відправлено.")
    except Exception:
        pass
    return ConversationHandler.END


# ============= Helpers =============

async def _evaluate_stage_and_notify(user_id: int, order_id: int, stage_db: int, context: ContextTypes.DEFAULT_TYPE):
    """
    Evaluate the current stage for a user:
    - If any active photo is still pending (confirmed=0), do nothing.
    - If any active photo is rejected (confirmed=-1), notify the user with reasons and stay on stage.
    - If all active photos are approved (confirmed=1), move to next stage: update DB, notify, and send next instruction.
    """
    # Consider only active photos for the current stage
    cursor.execute(
        "SELECT id, confirmed, COALESCE(reason, '') FROM order_photos "
        "WHERE order_id=? AND stage=? AND active=1 ORDER BY id ASC",
        (order_id, stage_db),
    )
    rows = cursor.fetchall()

    if not rows:
        return

    any_pending = any(r[1] == 0 for r in rows)
    any_rejected = any(r[1] == -1 for r in rows)
    all_approved = all(r[1] == 1 for r in rows)

    if any_pending:
        # Still pending review
        return

    if any_rejected:
        # Prepare reasons and notify the user
        cursor.execute(
            "SELECT id, COALESCE(reason, '') FROM order_photos "
            "WHERE order_id=? AND stage=? AND active=1 AND confirmed=-1 ORDER BY id ASC",
            (order_id, stage_db),
        )
        rejected = cursor.fetchall()
        lines = []
        for i, (pid, reason) in enumerate(rejected, start=1):
            lines.append(f"{i}. Скрін ID {pid}: {reason or 'без причини'}")
        text = "❌ Деякі скріни не пройшли перевірку менеджером.\n" \
               "Потрібно замінити наступні скріни:\n" + "\n".join(lines) + \
               "\n\nСкиньте заміну скрінів, щоб перейти на наступний етап."
        try:
            await context.bot.send_message(chat_id=user_id, text=text)
        except Exception:
            pass
        return

    if all_approved:
        # Advance to next stage
        try:
            user_states[user_id]['stage'] = user_states[user_id].get('stage', 0) + 1
        except Exception:
            # If state was missing, restore minimal state
            cursor.execute("SELECT stage FROM orders WHERE id=?", (order_id,))
            r = cursor.fetchone()
            new_stage0 = (r[0] if r else 0) + 1
            user_states[user_id] = user_states.get(user_id, {})
            user_states[user_id]['stage'] = new_stage0

        new_stage0 = user_states[user_id]['stage']  # 0-based in user_states
        try:
            update_order_stage_db(order_id, new_stage0, status=f"На етапі {new_stage0 + 1}")
        except Exception as e:
            logger.warning("Не вдалося оновити стадію замовлення %s: %s", order_id, e)

        try:
            await context.bot.send_message(chat_id=user_id, text="✅ Всі ваші скріни підтверджено. Переходимо на наступний етап.")
            await send_instruction(user_id, context)
        except Exception as e:
            logger.warning("Не вдалося надіслати інструкцію наступного етапу: %s", e)


# ============= Other existing service functions (kept) =============

def create_order_in_db(user_id: int, username: str, bank: str, action: str) -> int:
    cursor.execute(
        "INSERT INTO orders (user_id, username, bank, action, stage, status) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, username, bank, action, 0, "На етапі 1")
    )
    conn.commit()
    return cursor.lastrowid


def update_order_stage_db(order_id: int, new_stage: int, status: str = None):
    if status is None:
        cursor.execute("UPDATE orders SET stage=? WHERE id=?", (new_stage, order_id))
    else:
        cursor.execute("UPDATE orders SET stage=?, status=? WHERE id=?", (new_stage, status, order_id))
    conn.commit()


def set_order_group_db(order_id: int, group_chat_id: int):
    cursor.execute("UPDATE orders SET group_id=? WHERE id=?", (group_chat_id, order_id))
    conn.commit()


def free_group_db_by_chatid(group_chat_id: int):
    cursor.execute("UPDATE manager_groups SET busy=0 WHERE group_id=?", (group_chat_id,))
    conn.commit()


def occupy_group_db_by_dbid(group_db_id: int):
    cursor.execute("UPDATE manager_groups SET busy=1 WHERE id=?", (group_db_id,))
    conn.commit()


def get_free_groups(limit: int = None):
    q = "SELECT id, group_id FROM manager_groups WHERE busy=0 ORDER BY id ASC"
    if limit:
        q += f" LIMIT {limit}"
    cursor.execute(q)
    return cursor.fetchall()


def pop_queue_next():
    cursor.execute("SELECT id, user_id, username, bank, action FROM queue ORDER BY id ASC LIMIT 1")
    row = cursor.fetchone()
    if not row:
        return None
    qid, user_id, username, bank, action = row
    cursor.execute("DELETE FROM queue WHERE id=?", (qid,))
    conn.commit()
    return (user_id, username, bank, action)


def enqueue_user(user_id: int, username: str, bank: str, action: str):
    cursor.execute("INSERT INTO queue (user_id, username, bank, action) VALUES (?, ?, ?, ?)",
                   (user_id, username, bank, action))
    conn.commit()


def get_last_order_for_user(user_id: int):
    cursor.execute(
        "SELECT id, bank, action, stage, status, group_id FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 1",
        (user_id,))
    return cursor.fetchone()


def get_order_by_id(order_id: int):
    cursor.execute("SELECT id, user_id, username, bank, action, stage, status, group_id FROM orders WHERE id=?",
                   (order_id,))
    return cursor.fetchone()


def get_photos_for_order_stage(order_id: int, stage_db: int):
    cursor.execute(
        "SELECT id, file_id, confirmed FROM order_photos WHERE order_id=? AND stage=? AND active=1",
        (order_id, stage_db)
    )
    return cursor.fetchall()


async def assign_group_or_queue(order_id: int, user_id: int, username: str, bank: str, action: str,
                                context: ContextTypes.DEFAULT_TYPE) -> bool:
    cursor.execute("SELECT id, group_id, name FROM manager_groups WHERE busy=0 ORDER BY id ASC LIMIT 1")
    free_group = cursor.fetchone()
    if free_group:
        group_db_id, group_chat_id, group_name = free_group
        try:
            occupy_group_db_by_dbid(group_db_id)
            set_order_group_db(order_id, group_chat_id)
            logger.info("Order %s assigned to group %s (%s)", order_id, group_chat_id, group_name)
            msg = f"📢 Нова заявка від @{username} (ID: {user_id})\n🏦 {bank} — {action}\nOrderID: {order_id}"
            try:
                await context.bot.send_message(chat_id=group_chat_id, text=msg)
            except Exception as e:
                logger.warning("Не вдалося відправити повідомлення в групу %s: %s", group_chat_id, e)
            return True
        except Exception as e:
            logger.exception("assign_group_or_queue error while assigning: %s", e)
            return False
    else:
        try:
            enqueue_user(user_id, username, bank, action)
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="⏳ Усі менеджери зайняті. Ви в черзі. Отримаєте повідомлення, коли звільниться менеджер."
                )
            except Exception:
                logger.warning("Не вдалося повідомити користувача в черзі (ID=%s)", user_id)
            logger.info("User %s (order %s) enqueued", user_id, order_id)
        except Exception as e:
            logger.exception("assign_group_or_queue error while enqueue: %s", e)
        return False


async def assign_queued_clients_to_free_groups(context: ContextTypes.DEFAULT_TYPE):
    try:
        free_groups = get_free_groups()
        if not free_groups:
            return

        for group_db_id, group_chat_id in free_groups:
            next_client = pop_queue_next()
            if not next_client:
                break
            user_id, username, bank, action = next_client

            new_order_id = create_order_in_db(user_id, username, bank, action)

            try:
                occupy_group_db_by_dbid(group_db_id)
                set_order_group_db(new_order_id, group_chat_id)
            except Exception as e:
                logger.exception("Error occupying group or setting order group: %s", e)

            user_states[user_id] = {"order_id": new_order_id, "bank": bank, "action": action, "stage": 0,
                                    "age_required": find_age_requirement(bank, action)}
            try:
                await context.bot.send_message(chat_id=user_id, text="✅ Звільнилося місце! Починаємо реєстрацію.")
                await send_instruction(user_id, context)
            except Exception as e:
                logger.warning("Не вдалося повідомити користувача після призначення з черги: %s", e)
    except Exception as e:
        logger.exception("assign_queued_clients_to_free_groups error: %s", e)


async def send_instruction(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    from states import INSTRUCTIONS
    state = user_states.get(user_id)
    if not state:
        row = get_last_order_for_user(user_id)
        if not row:
            logger.warning("send_instruction: не знайдено замовлення для користувача %s", user_id)
            try:
                await context.bot.send_message(chat_id=user_id,
                                               text="❌ Помилка: замовлення не знайдено. Почніть заново командою /start")
            except Exception:
                pass
            return
        order_id, bank, action, stage0, status, group_id = row[0], row[1], row[2], row[3], row[4], row[5]
        user_states[user_id] = {"order_id": order_id, "bank": bank, "action": action, "stage": stage0,
                                "age_required": find_age_requirement(bank, action)}
        state = user_states[user_id]

    order_id = state.get("order_id")
    bank = state.get("bank")
    action = state.get("action")
    stage0 = state.get("stage", 0)

    steps = INSTRUCTIONS.get(bank, {}).get(action, [])
    if not steps:
        update_order_stage_db(order_id, stage0, status="Помилка: інструкції відсутні")
        logger.warning("No instructions for %s %s (order %s)", bank, action, order_id)
        try:
            await context.bot.send_message(chat_id=user_id,
                                           text="❌ Помилка: інструкції для обраного банку/операції відсутні. Зв'яжіться з адміністратором.")
            await context.bot.send_message(chat_id=ADMIN_GROUP_ID,
                                           text=f"⚠️ Для замовлення {order_id} немає інструкцій: {bank} {action}")
        except Exception:
            pass
        return

    if stage0 >= len(steps):
        update_order_stage_db(order_id, stage0, status="Завершено")
        order = get_order_by_id(order_id)
        if order:
            group_chat_id = order[7]
            if group_chat_id:
                try:
                    free_group_db_by_chatid(group_chat_id)
                except Exception:
                    pass
        try:
            await context.bot.send_message(chat_id=user_id, text="✅ Ваше замовлення завершено. Дякуємо!")
            await context.bot.send_message(chat_id=ADMIN_GROUP_ID,
                                           text=f"✅ Замовлення {order_id} виконано для @{order[2]} (ID: {order[1]})")
        except Exception:
            pass
        user_states.pop(user_id, None)
        try:
            await assign_queued_clients_to_free_groups(context)
        except Exception:
            pass
        return

    step = steps[stage0]
    text = step.get("text", "") if isinstance(step, dict) else str(step)
    images = step.get("images", []) if isinstance(step, dict) else []

    update_order_stage_db(order_id, stage0, status=f"На етапі {stage0 + 1}")

    if text:
        try:
            await context.bot.send_message(chat_id=user_id, text=text)
        except Exception as e:
            logger.warning("Не вдалося відправити текст інструкції користувачу %s: %s", user_id, e)

    for img in images:
        try:
            if isinstance(img, str) and os.path.exists(img):
                with open(img, "rb") as f:
                    await context.bot.send_photo(chat_id=user_id, photo=f)
            else:
                await context.bot.send_photo(chat_id=user_id, photo=img)
        except Exception as e:
            logger.warning("Не вдалося відправити зображення %s користувачу %s: %s", img, user_id, e)
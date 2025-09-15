import re
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes
from db import cursor, conn, ADMIN_GROUP_ID, log_action, logger

CODE_RE = re.compile(r"^\d{3,8}$")
ORDER_TAG_RE = re.compile(r"#(\d+)")
ORDER_ID_IN_TEXT_RE = re.compile(r"(?:OrderID|Order)\D*(\d+)")

def is_manager_group(chat_id: int) -> bool:
    try:
        cursor.execute("SELECT 1 FROM manager_groups WHERE group_id=?", (chat_id,))
        return cursor.fetchone() is not None
    except Exception:
        return False

def get_group_current_order(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> Optional[int]:
    try:
        store = context.application.chat_data.get(chat_id, {})
        return store.get("current_order_id")
    except Exception:
        return None

def set_group_current_order(context: ContextTypes.DEFAULT_TYPE, chat_id: int, order_id: int):
    try:
        context.application.chat_data.setdefault(chat_id, {})
        context.application.chat_data[chat_id]["current_order_id"] = order_id
    except Exception:
        pass

def get_active_order_for_group(chat_id: int) -> Optional[int]:
    cursor.execute(
        "SELECT id FROM orders WHERE group_id=? AND status!='Завершено' ORDER BY id DESC LIMIT 1",
        (chat_id,)
    )
    row = cursor.fetchone()
    return row[0] if row else None

def get_active_order_for_user(user_id: int) -> Optional[tuple]:
    cursor.execute(
        "SELECT id, user_id, username, bank, action, stage, status, group_id FROM orders "
        "WHERE user_id=? AND status!='Завершено' ORDER BY id DESC LIMIT 1",
        (user_id,)
    )
    return cursor.fetchone()

async def stage2_group_text_bridge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Груповий текст у менеджерських групах:
    - '#123' або 'OrderID: 123' в тексті → зафіксувати поточне замовлення для групи
    - лише цифри 3–8 → це код для поточного/останнього замовлення групи
    - будь-який інший текст → повідомлення користувачу поточного/останнього замовлення групи
    Захист: якщо менеджер у стані введення причини відхилення (reject) — нічого не чіпати.
    """
    msg = update.message
    if not msg or not msg.text:
        return
    chat_id = msg.chat_id

    # Працюємо лише в менеджерських групах
    if not is_manager_group(chat_id):
        return

    # Якщо цей менеджер зараз у стані введення причини/іншого state — не перехоплюємо
    # (ConversationHandler для модерації фото використовує context.user_data['reject_user_id'])
    if context.user_data.get("reject_user_id"):
        return

    text = msg.text.strip()

    # 1) Прив'язка поточного замовлення маркером
    m_tag = ORDER_TAG_RE.search(text) or ORDER_ID_IN_TEXT_RE.search(text)
    if m_tag:
        try:
            order_id = int(m_tag.group(1))
            # Перевіримо, що замовлення реальне і (бажано) прив'язане до цієї групи
            cursor.execute("SELECT user_id, group_id FROM orders WHERE id=?", (order_id,))
            row = cursor.fetchone()
            if not row:
                await msg.reply_text("❌ Замовлення не знайдено.")
                return
            _, order_group = row
            # Дозволимо прив'язати будь-яке, але підкажемо якщо інша група
            if order_group and order_group != chat_id:
                await msg.reply_text(f"⚠️ Order {order_id} привʼязане до іншої групи ({order_group}), але зробив його активним тут.")
            set_group_current_order(context, chat_id, order_id)
            await msg.reply_text(f"✅ Поточне замовлення встановлено: Order {order_id}")
            return
        except Exception as e:
            logger.warning("Set current order parse error: %s", e)

    # 2) Визначаємо order_id
    order_id = get_group_current_order(context, chat_id)
    if not order_id:
        order_id = get_active_order_for_group(chat_id)
    if not order_id:
        # Немає контексту замовлення — ігноруємо
        return

    # Отримуємо user_id
    cursor.execute("SELECT user_id FROM orders WHERE id=?", (order_id,))
    row = cursor.fetchone()
    if not row:
        return
    user_id = row[0]

    # 3) Якщо лише цифри → це код
    if CODE_RE.fullmatch(text):
        try:
            cursor.execute("UPDATE orders SET phone_code_status='delivered' WHERE id=?", (order_id,))
            conn.commit()
        except Exception as e:
            logger.warning("Failed to update code status: %s", e)
        log_action(order_id, "manager", "provide_code_auto", text)

        await msg.reply_text(f"✅ Код надіслано користувачу (Order {order_id}).")
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🔐 Код: {text}\nВведіть його у застосунку і після верифікації натисніть '📞 Номер підтверджено'."
            )
        except Exception as e:
            logger.warning("Send code to user fail: %s", e)
        return

    # 4) Інакше — пересилаємо як повідомлення менеджера
    log_action(order_id, "manager", "stage2_send_message_auto", text)
    try:
        await context.bot.send_message(chat_id=user_id, text=f"💬 Повідомлення від менеджера:\n{text}")
    except Exception as e:
        logger.warning("Send manager message to user fail: %s", e)
    try:
        await msg.reply_text("📨 Відправлено користувачу.")
    except Exception:
        pass


async def stage2_user_text_bridge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Приватний текст від користувача → у менеджерську групу його активного замовлення.
    """
    msg = update.message
    if not msg or not msg.text:
        return
    if update.effective_chat and update.effective_chat.type != "private":
        return

    user_id = msg.from_user.id
    text = msg.text.strip()

    order = get_active_order_for_user(user_id)
    if not order:
        return
    order_id, _, username, bank, action, stage, status, group_id = order
    target_group = group_id or ADMIN_GROUP_ID

    header = f"💬 Повідомлення від користувача (Order {order_id}, @{username or 'Без_ніка'} | ID {user_id}):"
    try:
        await context.bot.send_message(
            chat_id=target_group,
            text=f"{header}\n{text}"
        )
        set_group_current_order(context, target_group, order_id)
        log_action(order_id, "user", "stage2_user_message", text)
    except Exception as e:
        logger.warning("Forward user text to managers fail: %s", e)

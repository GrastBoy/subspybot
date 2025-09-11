import os
import json
from telegram import Update
from telegram.ext import ContextTypes
from db import cursor, conn, ADMIN_ID, ADMIN_GROUP_ID, logger
from handlers.photo_handlers import (
    get_last_order_for_user,
    get_order_by_id,
    free_group_db_by_chatid,
    assign_queued_clients_to_free_groups,
)
from states import user_states

ADMINS_FILE = "admins.txt"

def load_admins():
    """Зчитати список адмінів з файлу"""
    if not os.path.exists(ADMINS_FILE):
        with open(ADMINS_FILE, "w") as f:
            f.write(str(ADMIN_ID) + "\n")
    with open(ADMINS_FILE, "r") as f:
        return set(int(line.strip()) for line in f if line.strip().isdigit())

def save_admins(admins):
    """Зберегти список адмінів у файл"""
    with open(ADMINS_FILE, "w") as f:
        for admin_id in admins:
            f.write(str(admin_id) + "\n")

def is_admin(user_id):
    return user_id in load_admins()

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("⛔ У вас немає прав для цієї команди.")
        return

    args = context.args
    if not args:
        cursor.execute("SELECT id, user_id, username, bank, action, status FROM orders ORDER BY id DESC LIMIT 10")
        orders = cursor.fetchall()
        if not orders:
            await update.message.reply_text("📭 Замовлень немає.")
            return
        text = "📋 <b>Останні 10 замовлень:</b>\n\n"
        for o in orders:
            text += f"🆔 OrderID: {o[0]}\n👤 UserID: {o[1]} (@{o[2]})\n🏦 {o[3]} — {o[4]}\n📍 {o[5]}\n\n"
        await update.message.reply_text(text, parse_mode="HTML")
        return

    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Невірний формат ID.")
        return

    cursor.execute("SELECT id, bank, action FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 1", (target_id,))
    order = cursor.fetchone()
    if not order:
        await update.message.reply_text("❌ Замовлень для цього користувача не знайдено.")
        return

    order_id = order[0]
    bank = order[1]
    action = order[2]
    await update.message.reply_text(f"📂 Історія замовлення:\n🏦 {bank} — {action}", parse_mode="HTML")

    cursor.execute("SELECT stage, file_id FROM order_photos WHERE order_id=? ORDER BY stage ASC", (order_id,))
    photos = cursor.fetchall()
    for stage, file_id in photos:
        try:
            await update.message.reply_photo(photo=file_id, caption=f"Етап {stage}")
        except Exception:
            pass

async def add_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return await update.message.reply_text("⛔ Немає доступу")
    if len(context.args) < 2:
        return await update.message.reply_text("Використання: /addgroup <group_id> <назва>")
    try:
        group_id = int(context.args[0])
    except ValueError:
        return await update.message.reply_text("❌ ID групи має бути числом")
    name = " ".join(context.args[1:])
    cursor.execute("INSERT OR IGNORE INTO manager_groups (group_id, name) VALUES (?, ?)", (group_id, name))
    conn.commit()
    await update.message.reply_text(f"✅ Групу '{name}' додано")

async def del_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return await update.message.reply_text("⛔ Немає доступу")
    if not context.args:
        return await update.message.reply_text("Використання: /delgroup <group_id>")
    try:
        group_id = int(context.args[0])
    except ValueError:
        return await update.message.reply_text("❌ ID групи має бути числом")
    cursor.execute("DELETE FROM manager_groups WHERE group_id=?", (group_id,))
    conn.commit()
    await update.message.reply_text("✅ Групу видалено")

async def list_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return await update.message.reply_text("⛔ Немає доступу")
    cursor.execute("SELECT group_id, name, busy FROM manager_groups ORDER BY id ASC")
    groups = cursor.fetchall()
    if not groups:
        return await update.message.reply_text("📭 Немає груп")
    text = "📋 Список груп:\n"
    for gid, name, busy in groups:
        text += f"• {name} ({gid}) — {'🔴 Зайнята' if busy else '🟢 Вільна'}\n"
    await update.message.reply_text(text)

async def show_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return await update.message.reply_text("⛔ У вас немає прав для цієї команди.")
    cursor.execute("SELECT id, user_id, username, bank, action, created_at FROM queue ORDER BY id ASC")
    rows = cursor.fetchall()
    if not rows:
        return await update.message.reply_text("📭 Черга пуста.")
    text = "📋 Черга:\n\n"
    for r in rows:
        text += f"#{r[0]} — @{r[2]} (ID: {r[1]}) — {r[3]} / {r[4]} — {r[5]}\n"
    await update.message.reply_text(text)

async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Доступ тільки для адміністратора.")
        return

    args = context.args
    if not args or len(args) < 1:
        await update.message.reply_text("❌ Вкажіть user_id нового адміна. Приклад: /add_admin 123456789")
        return
    try:
        new_admin_id = int(args[0])
    except Exception:
        await update.message.reply_text("❌ Некоректний user_id.")
        return

    admins = load_admins()
    if new_admin_id in admins:
        await update.message.reply_text("ℹ️ Користувач вже є адміном.")
        return

    admins.add(new_admin_id)
    save_admins(admins)
    await update.message.reply_text(f"✅ Додано нового адміна: {new_admin_id}")

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Доступ тільки для адміністратора.")
        return

    args = context.args
    if not args or len(args) < 1:
        await update.message.reply_text("❌ Вкажіть user_id адміна для видалення. Приклад: /remove_admin 123456789")
        return
    try:
        remove_admin_id = int(args[0])
    except Exception:
        await update.message.reply_text("❌ Некоректний user_id.")
        return

    admins = load_admins()
    if remove_admin_id not in admins:
        await update.message.reply_text("❌ Користувач не є адміном.")
        return

    admins.remove(remove_admin_id)
    save_admins(admins)
    await update.message.reply_text(f"✅ Видалено адміна: {remove_admin_id}")

async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Доступ тільки для адміністратора.")
        return

    admins = load_admins()
    msg = "🛡️ Список адміністраторів:\n" + "\n".join(str(a) for a in admins)
    await update.message.reply_text(msg)

async def finish_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Доступ тільки для адміністратора.")
        return

    try:
        args = context.args
        if not args or len(args) < 1:
            await update.message.reply_text("❌ Вкажіть order_id. Приклад: /finish_order 123")
            return
        order_id = int(args[0])
        cursor.execute("SELECT user_id, group_id FROM orders WHERE id=? AND status!='Завершено'", (order_id,))
        row = cursor.fetchone()
        if not row:
            await update.message.reply_text("❌ Замовлення не знайдено або вже завершено.")
            return
        client_user_id, group_chat_id = row[0], row[1]

        cursor.execute("UPDATE orders SET status='Завершено' WHERE id=?", (order_id,))
        conn.commit()

        if group_chat_id:
            try:
                free_group_db_by_chatid(group_chat_id)
            except Exception:
                pass

        user_states.pop(client_user_id, None)

        try:
            await context.bot.send_message(chat_id=client_user_id, text="🏁 Ваше замовлення було завершено адміністратором.")
        except Exception:
            pass

        await update.message.reply_text(f"✅ Замовлення {order_id} завершено.")
        logger.info(f"Order {order_id} завершено адміністратором.")

        try:
            await assign_queued_clients_to_free_groups(context)
        except Exception:
            pass

    except Exception as e:
        logger.exception("finish_order error: %s", e)
        await update.message.reply_text("⚠️ Сталася помилка під час завершення замовлення.")

async def finish_all_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Доступ тільки для адміністратора.")
        return

    try:
        cursor.execute("SELECT id, user_id, group_id FROM orders WHERE status!='Завершено'")
        rows = cursor.fetchall()
        finished_count = 0
        freed_groups = set()

        for order_id, client_user_id, group_chat_id in rows:
            cursor.execute("UPDATE orders SET status='Завершено' WHERE id=?", (order_id,))
            user_states.pop(client_user_id, None)
            if group_chat_id:
                freed_groups.add(group_chat_id)
            try:
                await context.bot.send_message(chat_id=client_user_id, text="🏁 Ваше замовлення було завершено адміністратором.")
            except Exception:
                pass
            finished_count += 1

        for gid in freed_groups:
            try:
                free_group_db_by_chatid(gid)
            except Exception:
                pass

        cursor.execute("DELETE FROM queue")
        conn.commit()

        await update.message.reply_text(f"✅ Завершено всі незавершені замовлення: {finished_count} шт. Чергу очищено.")
        logger.info(f"Всі незавершені замовлення завершено ({finished_count} шт). Черга очищена.")

    except Exception as e:
        logger.exception("finish_all_orders error: %s", e)
        await update.message.reply_text("⚠️ Сталася помилка під час завершення всіх замовлень.")

async def orders_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Доступ тільки для адміністратора.")
        return

    try:
        cursor.execute("SELECT COUNT(*) FROM orders")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM orders WHERE status='Завершено'")
        finished = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM orders WHERE status!='Завершено'")
        unfinished = cursor.fetchone()[0]
        msg = (
            f"📊 Статистика замовлень:\n"
            f"Всього: {total}\n"
            f"Завершено: {finished}\n"
            f"Незавершено: {unfinished}\n"
        )
        await update.message.reply_text(msg)
    except Exception as e:
        logger.exception("orders_stats error: %s", e)
        await update.message.reply_text("⚠️ Не вдалося отримати статистику.")

async def stage2debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Адмін: /stage2debug <order_id> — показати поля Stage2 для діагностики."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Немає доступу")
        return
    if not context.args:
        await update.message.reply_text("Використання: /stage2debug <order_id>")
        return
    try:
        oid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("order_id має бути числом.")
        return
    cursor.execute("""SELECT id, user_id, phone_number, email, phone_verified, email_verified,
                             phone_code_status, phone_code_session, stage2_status, stage2_complete
                      FROM orders WHERE id=?""", (oid,))
    row = cursor.fetchone()
    if not row:
        await update.message.reply_text("Не знайдено.")
        return
    keys = ["id","user_id","phone_number","email","phone_verified","email_verified",
            "phone_code_status","phone_code_session","stage2_status","stage2_complete"]
    data = dict(zip(keys, row))
    await update.message.reply_text("Stage2:\n" + "\n".join(f"{k}: {v}" for k,v in data.items()))

async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ тільки для адміністратора.")
        return

    text = (
        "🛡️ <b>Довідка по адмін-командам</b>\n\n"
        "<b>/history [user_id]</b> — Останні 10 замовлень або останнє замовлення користувача.\n"
        "<b>/addgroup &lt;group_id&gt; &lt;назва&gt;</b> — Додати групу менеджерів.\n"
        "<b>/delgroup &lt;group_id&gt;</b> — Видалити групу.\n"
        "<b>/groups</b> — Список груп.\n"
        "<b>/queue</b> — Черга очікування.\n"
        "<b>/status</b> — Статус вашого останнього замовлення (для користувача).\n"
        "<b>/finish_order &lt;order_id&gt;</b> — Закрити замовлення.\n"
        "<b>/finish_all_orders</b> — Закрити всі незавершені замовлення.\n"
        "<b>/orders_stats</b> — Статистика замовлень.\n"
        "<b>/myorders</b> — Список ваших замовлень (для користувача).\n"
        "<b>/order &lt;order_id&gt;</b> — Картка замовлення (для адміна).\n"
    )
    await update.message.reply_text(text, parse_mode="HTML")
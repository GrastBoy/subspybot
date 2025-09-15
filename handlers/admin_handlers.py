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
from handlers.templates_store import list_templates, set_template, del_template

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
    
    args = context.args
    if len(args) < 2:
        return await update.message.reply_text(
            "Використання: /addgroup <group_id> <назва> [bank] [admin]\n\n"
            "Приклади:\n"
            "• /addgroup -123456789 'ПУМБ Менеджери' ПУМБ\n"
            "• /addgroup -987654321 'Адмін група' '' admin\n"
            "• /addgroup -111222333 'Універсальна група' ''"
        )
    
    try:
        group_id = int(args[0])
    except ValueError:
        return await update.message.reply_text("❌ ID групи має бути числом")
    
    name = args[1]
    bank = args[2] if len(args) > 2 and args[2] else None
    is_admin_group = 1 if len(args) > 3 and args[3].lower() == 'admin' else 0
    
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO manager_groups (group_id, name, bank, is_admin_group) 
            VALUES (?, ?, ?, ?)
        """, (group_id, name, bank, is_admin_group))
        conn.commit()
        
        group_type = "адмін група" if is_admin_group else f"група для банку '{bank}'" if bank else "універсальна група"
        await update.message.reply_text(f"✅ {group_type} '{name}' додано/оновлено")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка: {e}")

async def del_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return await update.message.reply_text("⛔ Немає доступу")
    if not context.args:
        return await update.message.reply_text("Використання: /delgroup <group_id>")
    try:
        group_id = int(context.args[0])
    except ValueError:
        return await update.message.reply_text("❌ ID групи має бути числом")
    
    # Clean up active orders for this group
    cursor.execute("DELETE FROM group_active_orders WHERE group_id=?", (group_id,))
    cursor.execute("DELETE FROM manager_groups WHERE group_id=?", (group_id,))
    conn.commit()
    await update.message.reply_text("✅ Групу видалено")

async def list_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return await update.message.reply_text("⛔ Немає доступу")
    
    cursor.execute("""
        SELECT group_id, name, bank, is_admin_group, busy 
        FROM manager_groups ORDER BY is_admin_group DESC, bank ASC, name ASC
    """)
    groups = cursor.fetchall()
    
    if not groups:
        return await update.message.reply_text("📭 Немає груп")
    
    text = "📋 <b>Список груп:</b>\n\n"
    
    # Admin groups first
    admin_groups = [g for g in groups if g[3]]
    if admin_groups:
        text += "<b>🔴 Адмін групи:</b>\n"
        for gid, name, bank, is_admin, busy in admin_groups:
            status = '🔴 Зайнята' if busy else '🟢 Вільна'
            text += f"• {name} ({gid}) — {status}\n"
        text += "\n"
    
    # Bank-specific groups
    bank_groups = [g for g in groups if not g[3] and g[2]]
    if bank_groups:
        text += "<b>🏦 Групи банків:</b>\n"
        for gid, name, bank, is_admin, busy in bank_groups:
            status = '🔴 Зайнята' if busy else '🟢 Вільна'
            text += f"• {name} ({gid}) — <i>{bank}</i> — {status}\n"
        text += "\n"
    
    # Universal groups
    universal_groups = [g for g in groups if not g[3] and not g[2]]
    if universal_groups:
        text += "<b>🌐 Універсальні групи:</b>\n"
        for gid, name, bank, is_admin, busy in universal_groups:
            status = '🔴 Зайнята' if busy else '🟢 Вільна'
            text += f"• {name} ({gid}) — {status}\n"
    
    await update.message.reply_text(text, parse_mode="HTML")

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
        "<b>📋 Базові команди:</b>\n"
        "<b>/history [user_id]</b> — Останні 10 замовлень або останнє замовлення користувача.\n"
        "<b>/queue</b> — Черга очікування.\n"
        "<b>/status</b> — Статус вашого останнього замовлення (для користувача).\n"
        "<b>/finish_order &lt;order_id&gt;</b> — Закрити замовлення.\n"
        "<b>/finish_all_orders</b> — Закрити всі незавершені замовлення.\n"
        "<b>/orders_stats</b> — Статистика замовлень.\n\n"
        
        "<b>🏦 Управління групами банків:</b>\n"
        "<b>/addgroup &lt;group_id&gt; &lt;назва&gt; [bank] [admin]</b> — Додати групу.\n"
        "   Приклади:\n"
        "   • <code>/addgroup -123 'ПУМБ Менеджери' ПУМБ</code>\n"
        "   • <code>/addgroup -456 'Адмін група' '' admin</code>\n"
        "<b>/delgroup &lt;group_id&gt;</b> — Видалити групу.\n"
        "<b>/groups</b> — Список всіх груп з типами.\n\n"
        
        "<b>📝 Управління активними замовленнями:</b>\n"
        "<b>/group_orders [group_id]</b> — Показати активні замовлення по групах.\n"
        "<b>/assign_order &lt;order_id&gt; &lt;group_id&gt; [current]</b> — Призначити замовлення групі.\n"
        "<b>/remove_order &lt;order_id&gt; &lt;group_id&gt;</b> — Видалити замовлення з активних.\n"
        "<b>/o &lt;order_id&gt;</b> — Встановити поточне замовлення (в групі).\n"
        "<b>/o</b> — Показати активні замовлення групи.\n\n"
        
        "<b>📄 Шаблони:</b>\n"
        "<b>/tmpl_list</b> — Список текстових шаблонів.\n"
        "<b>/tmpl_set &lt;key&gt; &lt;text&gt;</b> — Створити/оновити шаблон.\n"
        "<b>/tmpl_del &lt;key&gt;</b> — Видалити шаблон.\n\n"
        
        "<b>🏛️ Керування банками:</b>\n"
        "<b>/banks</b> — Показати список банків та їх видимість.\n"
        "<b>/bank_show &lt;bank name&gt; [register|change|both]</b> — Показати банк у списку.\n"
        "<b>/bank_hide &lt;bank name&gt; [register|change|both]</b> — Приховати банк зі списку.\n\n"
        
        "<b>💡 Нова архітектура груп:</b>\n"
        "• <b>Групи банків</b> — отримують замовлення конкретного банку\n"
        "• <b>Адмін групи</b> — бачать усі замовлення з усіх банків\n"
        "• <b>Універсальні групи</b> — можуть отримувати будь-які замовлення\n"
        "• <b>Множинні замовлення</b> — група може працювати з кількома замовленнями\n"
        "• <b>Перемикач замовлень</b> — <code>/o &lt;id&gt;</code> або <code>#123</code> у повідомленні"
    )
    await update.message.reply_text(text, parse_mode="HTML")

# ============= Templates admin commands =============

async def tmpl_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу")
    data = list_templates()
    if not data:
        return await update.message.reply_text("📭 Шаблонів немає.")
    lines = ["🧩 Шаблони:"]
    for k, v in data.items():
        preview = (v[:60] + "…") if len(v) > 60 else v
        lines.append(f"• !{k} — {preview}")
    await update.message.reply_text("\n".join(lines))

async def tmpl_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу")
    if not context.args or len(context.args) < 2:
        return await update.message.reply_text("Використання: /tmpl_set <key> <text>")
    key = context.args[0].strip()
    text = " ".join(context.args[1:]).strip()
    set_template(key, text)
    await update.message.reply_text(f"✅ Шаблон !{key} збережено.")

async def tmpl_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу")
    if not context.args:
        return await update.message.reply_text("Використання: /tmpl_del <key>")
    key = context.args[0].strip()
    ok = del_template(key)
    if ok:
        await update.message.reply_text(f"🗑 Видалено шаблон !{key}.")
    else:
        await update.message.reply_text("❌ Немає такого ключа.")

# ============= Banks visibility management (admin) =============
def _parse_bank_and_scope(args):
    valid_scopes = {"register", "change", "both"}
    scope = "both"
    if not args:
        return None, None
    if args[-1].lower() in valid_scopes:
        scope = args[-1].lower()
        bank_name = " ".join(args[:-1]).strip()
    else:
        bank_name = " ".join(args).strip()
    if not bank_name:
        return None, None
    return bank_name, scope

async def banks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу")
    from db import cursor
    cursor.execute("SELECT bank, show_register, show_change FROM bank_visibility")
    rows = cursor.fetchall()
    vis = {b: (sr, sc) for b, sr, sc in rows}

    try:
        from states import INSTRUCTIONS
        all_banks = sorted(set(INSTRUCTIONS.keys()) | set(vis.keys()))
    except Exception:
        all_banks = sorted(set(vis.keys()))

    lines = ["🏦 Банки (видимість у меню):"]
    for b in all_banks:
        sr, sc = vis.get(b, (1, 1))
        lines.append(f"• {b} — Реєстрація: {'✅' if sr else '❌'}, Перевʼяз: {'✅' if sc else '❌'}")
    lines.append("\nКерування: /bank_show <bank> [register|change|both], /bank_hide <bank> [register|change|both]")
    await update.message.reply_text("\n".join(lines))

async def bank_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу")
    from db import cursor, conn
    bank, scope = _parse_bank_and_scope(context.args)
    if not bank:
        return await update.message.reply_text("Використання: /bank_show <bank name> [register|change|both]")
    cursor.execute("INSERT OR IGNORE INTO bank_visibility (bank, show_register, show_change) VALUES (?, 1, 1)", (bank,))
    if scope in ("register", "both"):
        cursor.execute("UPDATE bank_visibility SET show_register=1 WHERE bank=?", (bank,))
    if scope in ("change", "both"):
        cursor.execute("UPDATE bank_visibility SET show_change=1 WHERE bank=?", (bank,))
    conn.commit()
    await update.message.reply_text(f"✅ Показуємо '{bank}' для: {scope}")

async def bank_hide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу")
    from db import cursor, conn
    bank, scope = _parse_bank_and_scope(context.args)
    if not bank:
        return await update.message.reply_text("Використання: /bank_hide <bank name> [register|change|both]")
    cursor.execute("INSERT OR IGNORE INTO bank_visibility (bank, show_register, show_change) VALUES (?, 1, 1)", (bank,))
    if scope in ("register", "both"):
        cursor.execute("UPDATE bank_visibility SET show_register=0 WHERE bank=?", (bank,))
    if scope in ("change", "both"):
        cursor.execute("UPDATE bank_visibility SET show_change=0 WHERE bank=?", (bank,))
    conn.commit()
    await update.message.reply_text(f"✅ Приховали '{bank}' для: {scope}")

# ================ New Group and Order Management Commands ================

async def group_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show active orders for all groups or specific group"""
    if not is_admin(update.message.from_user.id):
        return await update.message.reply_text("⛔ Немає доступу")
    
    group_filter = None
    if context.args:
        try:
            group_filter = int(context.args[0])
        except ValueError:
            return await update.message.reply_text("❌ ID групи має бути числом")
    
    # Get groups with their active orders
    if group_filter:
        cursor.execute("""
            SELECT mg.group_id, mg.name, mg.bank, mg.is_admin_group 
            FROM manager_groups mg WHERE mg.group_id=?
        """, (group_filter,))
    else:
        cursor.execute("""
            SELECT mg.group_id, mg.name, mg.bank, mg.is_admin_group 
            FROM manager_groups mg ORDER BY mg.is_admin_group DESC, mg.bank
        """)
    
    groups = cursor.fetchall()
    if not groups:
        return await update.message.reply_text("📭 Груп не знайдено")
    
    text = "📋 <b>Активні замовлення по групах:</b>\n\n"
    
    for group_id, name, bank, is_admin in groups:
        # Get active orders for this group
        cursor.execute("""
            SELECT gao.order_id, gao.is_current, o.user_id, o.username, o.bank, o.action, o.status
            FROM group_active_orders gao
            JOIN orders o ON gao.order_id = o.id
            WHERE gao.group_id=?
            ORDER BY gao.is_current DESC, gao.assigned_at ASC
        """, (group_id,))
        
        active_orders = cursor.fetchall()
        
        group_type = "🔴 Адмін" if is_admin else f"🏦 {bank}" if bank else "🌐 Універс."
        text += f"<b>{group_type} | {name} ({group_id}):</b>\n"
        
        if not active_orders:
            text += "  📭 Немає активних замовлень\n\n"
        else:
            for order_id, is_current, user_id, username, order_bank, action, status in active_orders:
                current_mark = "➤ " if is_current else "  "
                text += f"{current_mark}#{order_id} @{username or 'Без_ніка'} | {order_bank} {action} | {status}\n"
            text += "\n"
    
    await update.message.reply_text(text, parse_mode="HTML")

async def assign_order_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually assign an order to a specific group"""
    if not is_admin(update.message.from_user.id):
        return await update.message.reply_text("⛔ Немає доступу")
    
    if len(context.args) < 2:
        return await update.message.reply_text(
            "Використання: /assign_order <order_id> <group_id> [current]\n"
            "Приклад: /assign_order 123 -456789 current"
        )
    
    try:
        order_id = int(context.args[0])
        group_id = int(context.args[1])
        set_as_current = len(context.args) > 2 and context.args[2].lower() == 'current'
    except ValueError:
        return await update.message.reply_text("❌ Order ID та Group ID мають бути числами")
    
    # Check if order exists
    cursor.execute("SELECT id, user_id, username, bank, action FROM orders WHERE id=?", (order_id,))
    order = cursor.fetchone()
    if not order:
        return await update.message.reply_text("❌ Замовлення не знайдено")
    
    # Check if group exists
    cursor.execute("SELECT name FROM manager_groups WHERE group_id=?", (group_id,))
    group = cursor.fetchone()
    if not group:
        return await update.message.reply_text("❌ Група не знайдена")
    
    # Import db helper functions
    from db import add_active_order_to_group
    
    if add_active_order_to_group(group_id, order_id, set_as_current):
        # Update order's group_id
        cursor.execute("UPDATE orders SET group_id=? WHERE id=?", (group_id, order_id))
        conn.commit()
        
        current_text = " (встановлено як поточне)" if set_as_current else ""
        await update.message.reply_text(
            f"✅ Замовлення #{order_id} призначено групі {group[0]}{current_text}"
        )
    else:
        await update.message.reply_text("❌ Не вдалося призначити замовлення")

async def remove_order_from_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove an order from group's active list"""
    if not is_admin(update.message.from_user.id):
        return await update.message.reply_text("⛔ Немає доступу")
    
    if len(context.args) < 2:
        return await update.message.reply_text(
            "Використання: /remove_order <order_id> <group_id>"
        )
    
    try:
        order_id = int(context.args[0])
        group_id = int(context.args[1])
    except ValueError:
        return await update.message.reply_text("❌ Order ID та Group ID мають бути числами")
    
    from db import remove_active_order_from_group
    
    if remove_active_order_from_group(group_id, order_id):
        await update.message.reply_text(f"✅ Замовлення #{order_id} видалено з активних")
    else:
        await update.message.reply_text("❌ Не вдалося видалити замовлення")
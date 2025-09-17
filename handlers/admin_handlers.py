import os

from telegram import Update
from telegram.ext import ContextTypes

from db import ADMIN_ID, conn, cursor, is_admin, logger, add_admin_db, remove_admin_db, list_admins_db
from handlers.photo_handlers import (
    assign_queued_clients_to_free_groups,
    free_group_db_by_chatid,
)
from handlers.templates_store import del_template, list_templates, set_template
from states import user_states

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

    if add_admin_db(new_admin_id):
        await update.message.reply_text(f"✅ Додано нового адміна: {new_admin_id}")
    else:
        await update.message.reply_text("ℹ️ Користувач вже є адміном.")

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

    if remove_admin_db(remove_admin_id):
        await update.message.reply_text(f"✅ Видалено адміна: {remove_admin_id}")
    else:
        await update.message.reply_text("❌ Користувач не є адміном.")

async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Доступ тільки для адміністратора.")
        return

    admins = list_admins_db()
    if admins:
        msg = "🛡️ Список адміністраторів:\n" + "\n".join(str(a) for a in admins)
    else:
        msg = "🛡️ Список адміністраторів порожній"
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
        cursor.execute("SELECT user_id, group_id, bank FROM orders WHERE id=? AND status!='Завершено'", (order_id,))
        row = cursor.fetchone()
        if not row:
            await update.message.reply_text("❌ Замовлення не знайдено або вже завершено.")
            return
        client_user_id, group_chat_id, bank_name = row[0], row[1], row[2]

        # Check if order form exists (indicates complete user process)
        cursor.execute("SELECT form_data FROM order_forms WHERE order_id=?", (order_id,))
        form_row = cursor.fetchone()
        
        if form_row:
            # Complete order - user went through full process
            new_status = "Завершено"
            completion_type = "повне"
        else:
            # Incomplete order - manager finished manually without complete user process
            new_status = "Незавершено (менеджер)"
            completion_type = "неповне"

        cursor.execute("UPDATE orders SET status=? WHERE id=?", (new_status, order_id,))
        conn.commit()

        # Generate and send questionnaire
        try:
            from db import generate_order_questionnaire
            questionnaire = generate_order_questionnaire(order_id, bank_name)
            
            # Send questionnaire to the admin who finished the order
            completion_icon = "✅" if completion_type == "повне" else "⚠️"
            await update.message.reply_text(f"{completion_icon} Замовлення {order_id} завершено ({completion_type}).\n\n{questionnaire}", parse_mode='HTML')
            
            # Also send to the manager group if it exists
            if group_chat_id:
                try:
                    await context.bot.send_message(
                        chat_id=group_chat_id,
                        text=f"📋 Замовлення #{order_id} завершено ({completion_type}). Ось підсумкова анкета:\n\n{questionnaire}",
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.warning(f"Failed to send questionnaire to group {group_chat_id}: {e}")
                    
        except Exception as e:
            logger.warning(f"Failed to generate questionnaire for order {order_id}: {e}")
            await update.message.reply_text(f"✅ Замовлення {order_id} завершено ({completion_type}). (Помилка генерації анкети: {e})")

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
        cursor.execute("SELECT id, user_id, group_id FROM orders WHERE status!='Завершено' AND status!='Незавершено (менеджер)'")
        rows = cursor.fetchall()
        finished_count = 0
        freed_groups = set()

        for order_id, client_user_id, group_chat_id in rows:
            # Check if order form exists to determine completion type
            cursor.execute("SELECT form_data FROM order_forms WHERE order_id=?", (order_id,))
            form_row = cursor.fetchone()
            
            if form_row:
                new_status = "Завершено"
            else:
                new_status = "Незавершено (менеджер)"
                
            cursor.execute("UPDATE orders SET status=? WHERE id=?", (new_status, order_id,))
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
        completed = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM orders WHERE status='Незавершено (менеджер)'")
        incomplete = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM orders WHERE status!='Завершено' AND status!='Незавершено (менеджер)'")
        active = cursor.fetchone()[0]
        
        completion_rate = (completed / total * 100) if total > 0 else 0
        
        msg = (
            f"📊 <b>Статистика замовлень</b>\n\n"
            f"📈 Всього: {total}\n"
            f"✅ Завершено повністю: {completed} ({completion_rate:.1f}%)\n"
            f"⚠️ Завершено неповно: {incomplete}\n"
            f"🔄 Активних: {active}\n\n"
            f"💡 <i>Неповні замовлення - це ті, які менеджер завершив вручну, але клієнт не пройшов повний процес реєстрації/перев'язки.</i>"
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
    keys = ["id", "user_id", "phone_number", "email", "phone_verified", "email_verified",
            "phone_code_status", "phone_code_session", "stage2_status", "stage2_complete"]
    data = dict(zip(keys, row))
    await update.message.reply_text("Stage2:\n" + "\n".join(f"{k}: {v}" for k,v in data.items()))

async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ тільки для адміністратора.")
        return

    text = (
        "🛡️ <b>Довідка по адмін-командам</b>\n\n"
        "<b>Основні команди:</b>\n"
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
        "<b>/tmpl_list</b> — список текстових шаблонів для швидких відповідей.\n"
        "<b>/tmpl_set &lt;key&gt; &lt;text&gt;</b> — створити/оновити шаблон.\n"
        "<b>/tmpl_del &lt;key&gt;</b> — видалити шаблон.\n"
        "<b>/o &lt;order_id&gt;</b> — встановити поточне замовлення в цій групі.\n\n"
        "<b>Управління банками:</b>\n"
        "<b>/banks</b> — показати список банків та їх видимість для Реєстрації/Перевʼязу.\n"
        "<b>/bank_show &lt;bank name&gt; [register|change|both]</b> — показати банк у списку.\n"
        "<b>/bank_hide &lt;bank name&gt; [register|change|both]</b> — приховати банк зі списку.\n"
        "<b>/bank_management</b> — повне управління банками через інтерфейс.\n"
        "<b>/add_bank &lt;name&gt;</b> — швидко додати новий банк.\n"
        "<b>/data_history &lt;bank&gt;</b> — показати історію використання даних для банку.\n\n"
        "<b>Управління групами:</b>\n"
        "<b>/add_bank_group &lt;group_id&gt; &lt;bank&gt; &lt;name&gt;</b> — додати групу для банку.\n"
        "<b>/add_admin_group &lt;group_id&gt; &lt;name&gt;</b> — додати адмін групу.\n"
        "<b>/active_orders</b> — показати активні замовлення (в групах).\n\n"
        "<b>Анкети та форми:</b>\n"
        "<b>/order_form &lt;order_id&gt;</b> — показати анкету замовлення.\n"
        "<b>/list_forms [bank]</b> — список останніх анкет.\n"
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
    from db import conn, cursor
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
    from db import conn, cursor
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

# ============= New Enhanced Admin Commands =============

async def bank_management_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start bank management interface"""
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу")

    from handlers.bank_management import banks_management_menu
    await banks_management_menu(update, context)

async def add_bank_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick add bank command"""
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу")

    if not context.args:
        return await update.message.reply_text("Використання: /add_bank <назва банку>")

    bank_name = " ".join(context.args).strip()
    from db import add_bank, log_action

    if add_bank(bank_name, True, True):
        log_action(0, f"admin_{update.effective_user.id}", "add_bank_quick", bank_name)
        await update.message.reply_text(f"✅ Банк '{bank_name}' успішно додано!")
    else:
        await update.message.reply_text(f"❌ Помилка при додаванні банку '{bank_name}' (можливо, вже існує)")

async def add_bank_group_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add bank-specific manager group"""
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу")

    if len(context.args) < 3:
        return await update.message.reply_text("Використання: /add_bank_group <group_id> <bank> <назва>")

    try:
        group_id = int(context.args[0])
        bank = context.args[1]
        name = " ".join(context.args[2:])

        from db import add_manager_group, log_action

        if add_manager_group(group_id, name, bank, False):
            log_action(0, f"admin_{update.effective_user.id}", "add_bank_group", f"{bank}:{group_id}:{name}")
            await update.message.reply_text(f"✅ Групу '{name}' для банку '{bank}' додано!")
        else:
            await update.message.reply_text("❌ Помилка при додаванні групи (можливо, вже існує)")

    except ValueError:
        await update.message.reply_text("❌ Group ID має бути числом")

async def add_admin_group_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add admin manager group"""
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу")

    if len(context.args) < 2:
        return await update.message.reply_text("Використання: /add_admin_group <group_id> <назва>")

    try:
        group_id = int(context.args[0])
        name = " ".join(context.args[1:])

        from db import add_manager_group, log_action

        if add_manager_group(group_id, name, None, True):
            log_action(0, f"admin_{update.effective_user.id}", "add_admin_group", f"{group_id}:{name}")
            await update.message.reply_text(f"✅ Адмін групу '{name}' додано!")
        else:
            await update.message.reply_text("❌ Помилка при додаванні групи (можливо, вже існує)")

    except ValueError:
        await update.message.reply_text("❌ Group ID має бути числом")

async def data_history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show data usage history for a bank"""
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу")

    if not context.args:
        return await update.message.reply_text("Використання: /data_history <назва банку>")

    bank = " ".join(context.args).strip()
    from handlers.data_validation import show_data_usage_history
    await show_data_usage_history(update, context, bank)

async def order_form_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show order form/questionnaire"""
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу")

    if not context.args:
        return await update.message.reply_text("Використання: /order_form <order_id>")

    try:
        order_id = int(context.args[0])
        
        # Get order details to determine bank
        from db import cursor, generate_order_questionnaire
        cursor.execute("SELECT bank FROM orders WHERE id = ?", (order_id,))
        row = cursor.fetchone()
        
        if not row:
            return await update.message.reply_text(f"❌ Замовлення #{order_id} не знайдено")
        
        bank_name = row[0]
        questionnaire = generate_order_questionnaire(order_id, bank_name)
        
        await update.message.reply_text(questionnaire, parse_mode='HTML')
        
    except ValueError:
        await update.message.reply_text("❌ Order ID має бути числом")
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка: {e}")

async def list_forms_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List order forms"""
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу")

    bank = " ".join(context.args).strip() if context.args else None
    from handlers.order_forms import list_order_forms
    await list_order_forms(update, context, bank)

async def active_orders_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show active orders for current group"""
    from handlers.multi_order_management import show_active_orders
    await show_active_orders(update, context)

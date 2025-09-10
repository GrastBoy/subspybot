from telegram import Update
from telegram.ext import ContextTypes
from db import cursor
from handlers.photo_handlers import get_order_by_id

async def myorders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("SELECT id, bank, action, stage, status, created_at FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 10", (user_id,))
    rows = cursor.fetchall()
    if not rows:
        await update.message.reply_text("У вас немає замовлень.")
        return
    lines = ["📋 Ваші замовлення:"]
    for oid, bank, action, stage, status, created in rows:
        lines.append(f"— #{oid} | {bank} / {action} | {status} | Етап {stage+1} | {created}")
    await update.message.reply_text("\n".join(lines))

async def order_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Адмінський перегляд
    user_id = update.effective_user.id
    from handlers.admin_handlers import is_admin
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Доступ тільки для адміністратора.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("Використання: /order <order_id>")
        return
    try:
        order_id = int(args[0])
    except Exception:
        await update.message.reply_text("❌ Некоректний order_id")
        return

    row = get_order_by_id(order_id)
    if not row:
        await update.message.reply_text("❌ Замовлення не знайдено.")
        return

    oid, uid, uname, bank, action, stage, status, group_id = row
    text = (
        f"🆔 OrderID: {oid}\n"
        f"👤 User: @{uname or 'Без ника'} (ID: {uid})\n"
        f"🏦 {bank} / {action}\n"
        f"📍 {status} (етап {stage+1})\n"
        f"👥 Group: {group_id or '—'}\n"
        f"Команди: /finish_order {oid}"
    )
    await update.message.reply_text(text)
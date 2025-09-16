from telegram import Update
from telegram.ext import ContextTypes

from db import cursor, is_admin


def _fmt_bool(v) -> str:
    return "✅" if v else "❌"

async def myorders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute(
        "SELECT id, bank, action, stage, status, created_at FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 10",
        (user_id,)
    )
    rows = cursor.fetchall()
    if not rows:
        await update.message.reply_text("У вас немає замовлень.")
        return
    lines = ["📋 Ваші замовлення:"]
    for oid, bank, action, stage, status, created in rows:
        lines.append(f"• #{oid} — {bank}/{action}, етап {stage + 1}, {status}, створено {created}")
    await update.message.reply_text("\n".join(lines))

async def order_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Доступ тільки для адміністратора.")
        return
    if not context.args:
        await update.message.reply_text("Використання: /order <order_id>")
        return
    try:
        order_id = int(context.args[0])
    except Exception:
        await update.message.reply_text("order_id має бути числом.")
        return

    cursor.execute("""SELECT id, user_id, username, bank, action, stage, status, group_id,
                             phone_number, email, phone_verified, email_verified,
                             phone_code_status, phone_code_session, stage2_status, stage2_complete, created_at
                      FROM orders WHERE id=?""", (order_id,))
    row = cursor.fetchone()
    if not row:
        await update.message.reply_text("Не знайдено.")
        return
    (oid, uid, uname, bank, action, stage, status, group_id,
     phone, email, pv, ev, code_status, code_sess, s2_status, s2_complete, created) = row

    text = (
        f"📄 Order {oid}\n"
        f"👤 User: {uid} (@{uname or 'Без_ніка'})\n"
        f"🏦 {bank} / {action}\n"
        f"📍 Статус: {status}\n"
        f"🧭 Етап: {stage + 1}\n"
        f"👥 Group: {group_id or '—'}\n"
        f"📞 Phone: {phone or '—'} ({_fmt_bool(pv)})\n"
        f"📧 Email: {email or '—'} ({_fmt_bool(ev)})\n"
        f"🔐 Code: {code_status} (sess {code_sess})\n"
        f"🔒 Stage2: {s2_status}, complete={_fmt_bool(s2_complete)}\n"
        f"🕒 Created: {created}\n"
    )
    await update.message.reply_text(text)

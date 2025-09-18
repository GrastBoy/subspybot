"""
Admin command handler for reloading instructions cache
"""
import logging

from telegram import Update
from telegram.ext import ContextTypes

from db import is_admin
from services.instructions_cache import get_cache_stats, reload_instructions

logger = logging.getLogger(__name__)

async def reload_instructions_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin-only command to reload instructions cache"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Немає доступу")
        return

    try:
        # Force reload instructions
        banks_count, total_steps = reload_instructions()

        # Get new cache stats
        new_stats = get_cache_stats()

        response_text = (
            f"♻️ Інструкції перезавантажено.\n"
            f"Банків: {banks_count}\n"
            f"Кроків: {total_steps}\n"
            f"TTL: {new_stats['ttl_seconds']} секунд\n"
            f"Перезавантажень: {new_stats['reloads']}"
        )

        await update.message.reply_text(response_text)

        logger.info(
            "Instructions cache reloaded by admin %s: %d banks, %d steps",
            update.effective_user.id, banks_count, total_steps
        )

    except Exception as e:
        logger.error("Error reloading instructions cache: %s", e)
        await update.message.reply_text(f"❌ Помилка при перезавантаженні: {e}")

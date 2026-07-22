"""
Kelem User Support Bot — @kelemsupportbot

Users message this bot to reach support. Each user may send at most
DAILY_QUESTION_LIMIT (3) support messages per day. Every accepted message is
persisted and forwarded to the admin via the admin support bot, where the admin
can reply back. The admin's real identity/username is never exposed here.
"""

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Importing config sets up the firestore emulator shims before support_common.
from config import db  # noqa: F401
import support_common as sc

WELCOME = (
    "👋 *Kelem Support*\n\n"
    "Send us your question or problem and our team will reply here.\n\n"
    f"ℹ️ You can send up to *{sc.DAILY_QUESTION_LIMIT} messages per day*."
)

SENT = (
    "✅ Your message was sent to support.\n"
    "We'll reply to you here as soon as possible.\n\n"
    "📊 Messages left today: *{remaining}*"
)

LIMIT_REACHED = (
    "⚠️ You've reached your limit of "
    f"{sc.DAILY_QUESTION_LIMIT} support messages for today.\n"
    "Please try again tomorrow."
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    sc.register_support_user(user, update.effective_chat.id)
    await update.message.reply_text(WELCOME, parse_mode='Markdown')


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()
    if not text:
        return

    sc.register_support_user(user, chat_id)

    allowed, remaining = sc.try_consume_quota(user.id)
    if not allowed:
        await update.message.reply_text(LIMIT_REACHED)
        return

    ticket_id = sc.record_message(user, chat_id, text, direction='user')

    try:
        await _notify_admin(user, text, ticket_id)
    except Exception as e:
        logger.error(f"Failed to notify admin about ticket {ticket_id}: {e}")

    await update.message.reply_text(
        SENT.format(remaining=remaining), parse_mode='Markdown'
    )


async def _notify_admin(user, text, ticket_id):
    """Send the new support message to the admin via the admin support bot."""
    if not sc.ADMIN_CHAT_ID:
        logger.warning("ADMIN_CHAT_ID is not set; cannot notify admin.")
        return

    admin_bot = Bot(token=sc.ADMIN_SUPPORT_BOT_TOKEN)
    uname = f"@{user.username}" if user.username else "—"
    notification = (
        "📨 *New support message*\n\n"
        f"👤 {user.first_name or 'User'} ({uname})\n"
        f"🆔 `{user.id}`\n\n"
        f"💬 {text}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✍️ Reply", callback_data=f"reply_{user.id}")],
    ])
    await admin_bot.send_message(
        chat_id=sc.ADMIN_CHAT_ID,
        text=notification,
        reply_markup=kb,
        parse_mode='Markdown',
    )


def main():
    import asyncio as _asyncio

    async def _pre_start():
        b = Bot(token=sc.SUPPORT_BOT_TOKEN)
        await b.delete_webhook(drop_pending_updates=True)
        await _asyncio.sleep(5)
        me = await b.get_me()
        logger.info(f"✅ Support bot connected: @{me.username}")

    _asyncio.run(_pre_start())

    app = Application.builder().token(sc.SUPPORT_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("💬 User Support Bot starting...")

    async def _handle_error(update, context):
        from telegram.error import Conflict
        if isinstance(context.error, Conflict):
            return
        logger.error(f"Unhandled exception: {context.error}", exc_info=context.error)

    app.add_error_handler(_handle_error)
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

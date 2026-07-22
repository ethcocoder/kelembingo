"""
Kelem Admin Support Bot — @kelemadminsupportbot

Only the admin (ADMIN_CHAT_ID) may use this bot. It receives notifications of
new user support messages and lets the admin reply to any player. Replies are
delivered to the user through the user support bot, so the admin's real
telegram account / username is never exposed to players.

Reply flow:
  • Tap "✍️ Reply" on a notification, or use /players to pick a user.
  • Then send the reply text; it is delivered to the chosen user.
  • You can also reply directly (Telegram reply) to a notification message.
"""

import logging
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from config import db  # noqa: F401  (sets up firestore emulator shims)
import support_common as sc


def _is_admin(user_id):
    return sc.ADMIN_CHAT_ID and user_id == sc.ADMIN_CHAT_ID


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    await update.message.reply_text(
        "🛠 *Admin Support Panel*\n\n"
        "New user messages arrive here automatically.\n\n"
        "• Tap *✍️ Reply* on a message to answer that user.\n"
        "• /players — list users with recent messages.\n"
        "Your identity is never shown to users.",
        parse_mode='Markdown',
    )


async def players(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return
    users = sc.list_recent_users(20)
    if not users:
        await update.message.reply_text("No support messages yet.")
        return

    rows = []
    for u in users:
        name = u.get('firstName') or 'User'
        uname = f" (@{u['username']})" if u.get('username') else ""
        rows.append([InlineKeyboardButton(
            f"{name}{uname}", callback_data=f"reply_{u['userId']}"
        )])
    await update.message.reply_text(
        "👥 Select a player to reply to:",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id):
        return

    if query.data.startswith("reply_"):
        uid = query.data.replace("reply_", "")
        context.user_data['reply_to'] = uid
        su = sc.get_support_user(uid) or {}
        name = su.get('firstName') or 'User'
        last = su.get('lastText', '')
        await query.message.reply_text(
            f"✍️ Replying to *{name}* (`{uid}`).\n"
            + (f"\nLast message:\n💬 {last}\n" if last else "")
            + "\nSend your reply now.",
            parse_mode='Markdown',
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return

    text = (update.message.text or "").strip()
    if not text:
        return

    uid = context.user_data.get('reply_to')

    # Support replying directly to a notification message.
    if not uid and update.message.reply_to_message:
        m = re.search(r"🆔\s*`?(\d+)`?", update.message.reply_to_message.text or "")
        if m:
            uid = m.group(1)

    if not uid:
        await update.message.reply_text(
            "ℹ️ Choose a user first: tap *✍️ Reply* on a message or use /players.",
            parse_mode='Markdown',
        )
        return

    chat_id = sc.get_user_chat_id(uid)
    try:
        user_bot = Bot(token=sc.SUPPORT_BOT_TOKEN)
        await user_bot.send_message(
            chat_id=int(chat_id),
            text=f"💬 *Support reply:*\n\n{text}",
            parse_mode='Markdown',
        )
    except Exception as e:
        logger.error(f"Failed to deliver reply to {uid}: {e}")
        await update.message.reply_text(f"❌ Could not deliver: {str(e)[:100]}")
        return

    sc.record_message(update.effective_user, chat_id, text, direction='admin')
    su = sc.get_support_user(uid) or {}
    await update.message.reply_text(
        f"✅ Sent to {su.get('firstName') or 'user'}."
    )
    context.user_data.pop('reply_to', None)


def main():
    import asyncio as _asyncio

    async def _pre_start():
        b = Bot(token=sc.ADMIN_SUPPORT_BOT_TOKEN)
        await b.delete_webhook(drop_pending_updates=True)
        await _asyncio.sleep(5)
        me = await b.get_me()
        logger.info(f"✅ Admin support bot connected: @{me.username}")

    _asyncio.run(_pre_start())

    app = Application.builder().token(sc.ADMIN_SUPPORT_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("players", players))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("🛠 Admin Support Bot starting...")

    async def _handle_error(update, context):
        from telegram.error import Conflict
        if isinstance(context.error, Conflict):
            return
        logger.error(f"Unhandled exception: {context.error}", exc_info=context.error)

    app.add_error_handler(_handle_error)
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

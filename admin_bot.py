import os
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from config import db
import firestore_db as firestore

ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN", "")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))


def _is_admin(user_id):
    return user_id == ADMIN_CHAT_ID


# ═══════════════════════════════════════════════════════════════════
# /start
# ═══════════════════════════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    await update.message.reply_text(
        "✅ Admin Panel Active\n\n"
        "Use /deposits or /withdrawals to see pending requests.\n"
        "Approve/reject buttons are sent automatically for new requests."
    )


# ═══════════════════════════════════════════════════════════════════
# /deposits — list pending deposits
# ═══════════════════════════════════════════════════════════════════
async def deposits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return
    pending = list(db.collection('deposits').where('status', '==', 'pending').order_by('createdAt').limit(20).stream())
    if not pending:
        await update.message.reply_text("✅ No pending deposits.")
        return

    for doc in pending:
        d = doc.to_dict()
        did = doc.id
        ocr = d.get('ocr', {})
        status_icon = "✅" if ocr.get('status') == 'success' else "❌" if ocr.get('status') == 'failed' else "❓"
        date_text = ocr.get('transactionDate') or 'N/A'
        receiver_text = ocr.get('receiverName') or d.get('senderName', 'N/A')
        type_text = ocr.get('transactionType') or 'N/A'
        confidence = ocr.get('confidence', 0)

        text = (
            f"💵 *Deposit #{did[:8]}*\n\n"
            f"👤 {d.get('firstName', '?')} (@{d.get('username', '?')})\n"
            f"💰 TeleBirr Name: {d.get('telebirrName', 'N/A')}\n"
            f"━━━ *Screenshot Parsed* ━━━\n"
            f"{status_icon} *Status:* {ocr.get('status', 'unknown')}\n"
            f"💵 *Amount:* {d.get('amount', 0)} ETB\n"
            f"📅 *Date:* {date_text}\n"
            f"🔖 *Reference:* {d.get('transactionId', 'N/A')}\n"
            f"👤 *Receiver:* {receiver_text}\n"
            f"📋 *Type:* {type_text}\n"
            f"📊 *Confidence:* {int(confidence * 100)}%\n"
            f"🕐 {d.get('createdAt', 'N/A')}"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Approve", callback_data=f"approve_{did}"),
             InlineKeyboardButton("❌ Reject", callback_data=f"reject_{did}")],
        ])
        file_id = d.get('imageFileId')
        if file_id:
            try:
                await context.bot.send_photo(
                    chat_id=ADMIN_CHAT_ID, photo=file_id,
                    caption=text, reply_markup=kb, parse_mode='Markdown',
                )
                continue
            except Exception:
                pass
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID, text=text,
            reply_markup=kb, parse_mode='Markdown',
        )


# ═══════════════════════════════════════════════════════════════════
# /withdrawals — list pending withdrawals
# ═══════════════════════════════════════════════════════════════════
async def withdrawals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return
    pending = list(db.collection('withdrawals').where('status', '==', 'pending').order_by('createdAt').limit(20).stream())
    if not pending:
        await update.message.reply_text("✅ No pending withdrawals.")
        return

    for doc in pending:
        w = doc.to_dict()
        wid = doc.id
        text = (
            f"🎰 *Withdrawal #{wid[:8]}*\n\n"
            f"👤 {w.get('firstName', '?')} (@{w.get('username', '?')})\n"
            f"💰 TeleBirr Name: {w.get('telebirrName', 'N/A')}\n"
            f"💵 {w.get('amount', 0)} ETB\n"
            f"📱 Phone: {w.get('phone', 'N/A')}\n"
            f"🕐 {w.get('createdAt', 'N/A')}"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Approve", callback_data=f"approve_withdraw_{wid}"),
             InlineKeyboardButton("❌ Reject", callback_data=f"reject_withdraw_{wid}")],
        ])
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID, text=text,
            reply_markup=kb, parse_mode='Markdown',
        )


# ═══════════════════════════════════════════════════════════════════
# Callback router
# ═══════════════════════════════════════════════════════════════════
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id):
        return

    data = query.data

    if data.startswith("approve_") and not data.startswith("approve_withdraw_"):
        deposit_id = data.replace("approve_", "")
        await process_deposit(deposit_id, "approved", query)

    elif data.startswith("reject_") and not data.startswith("reject_withdraw_"):
        deposit_id = data.replace("reject_", "")
        await process_deposit(deposit_id, "rejected", query)

    elif data.startswith("approve_withdraw_"):
        wid = data.replace("approve_withdraw_", "")
        await process_withdrawal(wid, "approved", query, context)

    elif data.startswith("reject_withdraw_"):
        wid = data.replace("reject_withdraw_", "")
        await process_withdrawal(wid, "rejected", query, context)


# ═══════════════════════════════════════════════════════════════════
# Process deposit
# ═══════════════════════════════════════════════════════════════════
async def process_deposit(deposit_id, status, query):
    try:
        ref = db.collection('deposits').document(deposit_id)
        result = {}

        @firestore.transactional
        def _txn(transaction, ref, status):
            doc = ref.get(transaction=transaction)
            if not doc.exists:
                raise Exception("Deposit not found.")
            data = doc.to_dict()
            if data.get('status') != 'pending':
                raise Exception(f"Already {data.get('status')}.")
            transaction.update(ref, {
                'status': status,
                'processedAt': datetime.now(tz=timezone.utc),
            })
            user_id = data.get('userId')
            amount = data.get('amount', 0)
            if status == "approved" and user_id and amount > 0:
                user_ref = db.collection('users').document(str(user_id))
                transaction.update(user_ref, {
                    'balance': firestore.Increment(amount),
                    'updated_at': datetime.now(tz=timezone.utc),
                })
            result['user_id'] = user_id
            result['amount'] = amount
            return data

        transaction = db.transaction()
        data = _txn(transaction, ref, status)
        user_id = result.get('user_id')
        amount = result.get('amount', 0)

        # Notify user via game bot
        try:
            from telegram import Bot
            from config import BOT_TOKEN
            bot = Bot(token=BOT_TOKEN)
            if status == "approved" and user_id:
                await bot.send_message(
                    chat_id=int(user_id),
                    text=f"✅ Deposit approved!\n💰 {amount} ETB has been added to your wallet.",
                )
            elif user_id:
                await bot.send_message(
                    chat_id=int(user_id),
                    text=f"❌ Deposit rejected.\nPlease contact support if you need help.",
                )
        except Exception as e:
            logger.error(f"Failed to notify user {user_id}: {e}")

        new_text = (
            f"{'✅' if status == 'approved' else '❌'} Deposit {status}\n"
            f"User: {data.get('firstName', '?')} | {amount} ETB"
        )
        try:
            await query.edit_message_text(new_text)
        except Exception:
            try:
                await query.edit_message_caption(caption=new_text)
            except Exception:
                pass

    except Exception as e:
        logger.error(f"Error processing deposit: {e}")
        try:
            await query.edit_message_text(f"❌ Error: {str(e)[:100]}")
        except Exception:
            try:
                await query.edit_message_caption(caption=f"❌ Error: {str(e)[:100]}")
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════════
# Process withdrawal
# ═══════════════════════════════════════════════════════════════════
async def process_withdrawal(wid, status, query, context):
    try:
        ref = db.collection('withdrawals').document(wid)
        result = {}

        @firestore.transactional
        def _txn(transaction, ref, status):
            doc = ref.get(transaction=transaction)
            if not doc.exists:
                raise Exception("Withdrawal not found.")
            data = doc.to_dict()
            if data.get('status') != 'pending':
                raise Exception(f"Already {data.get('status')}.")
            transaction.update(ref, {
                'status': status,
                'processedAt': datetime.now(tz=timezone.utc),
            })
            user_id = data.get('userId')
            amount = data.get('amount', 0)
            if status == "rejected" and user_id and amount > 0:
                user_ref = db.collection('users').document(str(user_id))
                transaction.update(user_ref, {
                    'balance': firestore.Increment(amount),
                    'updated_at': datetime.now(tz=timezone.utc),
                })
            result['user_id'] = user_id
            result['amount'] = amount
            return data

        transaction = db.transaction()
        data = _txn(transaction, ref, status)
        user_id = result.get('user_id')
        amount = result.get('amount', 0)

        # Notify user
        try:
            from telegram import Bot
            from config import BOT_TOKEN
            bot = Bot(token=BOT_TOKEN)
            if status == "approved" and user_id:
                await bot.send_message(
                    chat_id=int(user_id),
                    text=f"✅ Withdrawal approved!\n💰 {amount} ETB will be sent to your TeleBirr.",
                )
            elif user_id:
                await bot.send_message(
                    chat_id=int(user_id),
                    text=f"❌ Withdrawal rejected.\n💰 {amount} ETB has been refunded to your balance.",
                )
        except Exception as e:
            logger.error(f"Failed to notify user {user_id}: {e}")

        await query.edit_message_text(
            f"{'✅' if status == 'approved' else '❌'} Withdrawal {status}\n"
            f"User: {data.get('firstName', '?')} | {amount} ETB"
        )

    except Exception as e:
        logger.error(f"Error processing withdrawal: {e}")
        await query.edit_message_text(f"❌ Error: {str(e)[:100]}")


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════
def main():
    import asyncio as _asyncio

    async def _pre_start():
        from telegram import Bot
        import asyncio as _aio
        b = Bot(token=ADMIN_BOT_TOKEN)
        await b.delete_webhook(drop_pending_updates=True)
        await _aio.sleep(5)
        me = await b.get_me()
        logger.info(f"✅ Admin bot connected: @{me.username}")

    _asyncio.run(_pre_start())

    app = Application.builder().token(ADMIN_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("deposits", deposits))
    app.add_handler(CommandHandler("withdrawals", withdrawals))
    app.add_handler(CallbackQueryHandler(handle_callback))
    logger.info("🔧 Admin Bot starting...")

    async def _handle_error(update, context):
        from telegram.error import Conflict
        if isinstance(context.error, Conflict):
            return
        logger.error(f"Unhandled exception: {context.error}", exc_info=context.error)

    app.add_error_handler(_handle_error)
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

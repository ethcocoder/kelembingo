import os
import logging
import httpx
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
import firebase_admin
from firebase_admin import credentials, firestore

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Firebase
cred = credentials.Certificate(os.path.join(os.path.dirname(__file__), "bingo-bot-5c708-firebase-adminsdk-fbsvc-c5d4b699f3.json"))
firebase_admin.initialize_app(cred)
db = firestore.client()

ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN", "YOUR_ADMIN_BOT_TOKEN_HERE")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
PAYMENT_BOT_TOKEN = os.getenv("PAYMENT_BOT_TOKEN", "YOUR_PAYMENT_BOT_TOKEN_HERE")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ Unauthorized. This bot is for admins only.")
        return
    
    text = """🔧 *Yegara Admin Bot*

*Commands:*
/deposits - View pending deposits
/withdrawals - View pending withdrawals
/stats - System statistics
/approve <id> - Approve a deposit
/reject <id> - Reject a deposit
/approve_withdraw <id> - Approve withdrawal
/reject_withdraw <id> - Reject withdrawal

*Quick Actions:*
/deposit_queue - Show deposit queue
/withdraw_queue - Show withdrawal queue"""
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def deposits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return
    
    pending = db.collection("deposits").where("status", "==", "pending").order_by("createdAt").get()
    
    if not pending:
        await update.message.reply_text("✅ No pending deposits.")
        return
    
    text = "📋 *Pending Deposits:*\n\n"
    for doc in pending:
        d = doc.to_dict()
        text += f"🆔 `{doc.id}`\n"
        text += f"👤 {d.get('firstName', 'Unknown')} (@{d.get('username', 'unknown')})\n"
        text += f"💰 {d.get('amount', 0)} ETB\n"
        text += f"📝 TXN: `{d.get('transactionId', 'N/A')}`\n"
        text += f"⏰ {d['createdAt'].strftime('%Y-%m-%d %H:%M')}\n\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def withdrawals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return
    
    pending = db.collection("withdrawals").where("status", "==", "pending").order_by("createdAt").get()
    
    if not pending:
        await update.message.reply_text("✅ No pending withdrawals.")
        return
    
    text = "📋 *Pending Withdrawals:*\n\n"
    for doc in pending:
        w = doc.to_dict()
        text += f"🆔 `{doc.id}`\n"
        text += f"👤 {w.get('firstName', 'Unknown')} (@{w.get('username', 'unknown')})\n"
        text += f"💰 {w.get('amount', 0)} ETB\n"
        text += f"📱 TeleBirr: `{w.get('telebirrNumber', 'N/A')}`\n"
        text += f"⏰ {w['createdAt'].strftime('%Y-%m-%d %H:%M')}\n\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return
    
    users = len(list(db.collection("users").get()))
    games = len(list(db.collection("games").get()))
    pending_deposits = len(list(db.collection("deposits").where("status", "==", "pending").get()))
    pending_withdrawals = len(list(db.collection("withdrawals").where("status", "==", "pending").get()))
    total_deposited = sum(d.to_dict().get("amount", 0) for d in db.collection("deposits").where("status", "==", "approved").get())
    total_withdrawn = sum(w.to_dict().get("amount", 0) for w in db.collection("withdrawals").where("status", "==", "approved").get())
    
    text = f"""📊 *System Statistics*

👥 *Users:* {users}
🎮 *Games:* {games}
💰 *Pending Deposits:* {pending_deposits}
💸 *Pending Withdrawals:* {pending_withdrawals}
📈 *Total Deposited:* {total_deposited:.2f} ETB
📉 *Total Withdrawn:* {total_withdrawn:.2f} ETB
💵 *Net Balance:* {total_deposited - total_withdrawn:.2f} ETB"""
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_CHAT_ID:
        await query.edit_message_text("⛔ Unauthorized.")
        return
    
    data = query.data
    
    if data.startswith("approve_"):
        deposit_id = data.replace("approve_", "")
        await process_deposit(deposit_id, "approved", query)
    
    elif data.startswith("reject_"):
        deposit_id = data.replace("reject_", "")
        await process_deposit(deposit_id, "rejected", query)
    
    elif data.startswith("approve_withdraw_"):
        withdraw_id = data.replace("approve_withdraw_", "")
        await process_withdrawal(withdraw_id, "approved", query)
    
    elif data.startswith("reject_withdraw_"):
        withdraw_id = data.replace("reject_withdraw_", "")
        await process_withdrawal(withdraw_id, "rejected", query)

async def process_deposit(deposit_id, status, query):
    try:
        doc_ref = db.collection("deposits").document(deposit_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            await query.edit_message_text("❌ Deposit not found.")
            return
        
        deposit = doc.to_dict()
        
        if deposit["status"] != "pending":
            await query.edit_message_text(f"⚠️ Deposit already {deposit['status']}.")
            return
        
        # Update deposit status
        doc_ref.update({
            "status": status,
            "processedAt": datetime.utcnow()
        })
        
        if status == "approved":
            # Credit user balance
            user_id = deposit["userId"]
            amount = deposit.get("amount", 0)
            
            user_ref = db.collection("users").document(str(user_id))
            user_doc = user_ref.get()
            
            if user_doc.exists:
                current_balance = user_doc.to_dict().get("balance", 0)
                user_ref.update({
                    "balance": current_balance + amount,
                    "updatedAt": datetime.utcnow()
                })
            
            # Notify user
            await notify_user(user_id, f"✅ *Deposit Approved\!*\n\n+{amount} ETB added to your balance.\nNew Balance: {current_balance + amount:.2f} ETB", "approved")
            
            await query.edit_message_text(
                f"✅ *Deposit Approved*\n\n"
                f"User: {deposit.get('firstName', 'Unknown')}\n"
                f"Amount: {deposit.get('amount', 0)} ETB\n"
                f"Balance credited automatically."
            )
        else:
            await notify_user(deposit["userId"], f"❌ *Deposit Rejected*\n\nYour deposit of {deposit.get('amount', 0)} ETB was rejected.\nPlease contact admin if you believe this is an error.", "rejected")
            
            await query.edit_message_text(
                f"❌ *Deposit Rejected*\n\n"
                f"User: {deposit.get('firstName', 'Unknown')}\n"
                f"Amount: {deposit.get('amount', 0)} ETB"
            )
        
    except Exception as e:
        logger.error(f"Error processing deposit: {e}")
        await query.edit_message_text(f"❌ Error: {str(e)}")

async def process_withdrawal(withdraw_id, status, query):
    try:
        doc_ref = db.collection("withdrawals").document(withdraw_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            await query.edit_message_text("❌ Withdrawal not found.")
            return
        
        withdrawal = doc.to_dict()
        
        if withdrawal["status"] != "pending":
            await query.edit_message_text(f"⚠️ Withdrawal already {withdrawal['status']}.")
            return
        
        doc_ref.update({
            "status": status,
            "processedAt": datetime.utcnow()
        })
        
        if status == "approved":
            # Deduct from user balance (already deducted on request, just confirm)
            await notify_user(withdrawal["userId"], f"✅ *Withdrawal Approved\!*\n\n{withdrawal.get('amount', 0)} ETB will be sent to your TeleBirr.\nPlease allow up to 24 hours.", "approved")
            
            await query.edit_message_text(
                f"✅ *Withdrawal Approved*\n\n"
                f"User: {withdrawal.get('firstName', 'Unknown')}\n"
                f"Amount: {withdrawal.get('amount', 0)} ETB\n"
                f"TeleBirr: {withdrawal.get('telebirrNumber', 'N/A')}\n\n"
                f"📱 *Send {withdrawal.get('amount', 0)} ETB to:*\n`{withdrawal.get('telebirrNumber', 'N/A')}`"
            )
        else:
            # Refund user balance
            user_id = withdrawal["userId"]
            amount = withdrawal.get("amount", 0)
            user_ref = db.collection("users").document(str(user_id))
            user_doc = user_ref.get()
            if user_doc.exists:
                current_balance = user_doc.to_dict().get("balance", 0)
                user_ref.update({"balance": current_balance + amount, "updatedAt": datetime.utcnow()})
            
            await notify_user(user_id, f"❌ *Withdrawal Rejected*\n\nYour withdrawal of {amount} ETB was rejected.\n{amount} ETB has been refunded to your balance.", "rejected")
            
            await query.edit_message_text(
                f"❌ *Withdrawal Rejected*\n\n"
                f"User: {withdrawal.get('firstName', 'Unknown')}\n"
                f"Amount: {withdrawal.get('amount', 0)} ETB\n"
                f"Balance refunded."
            )
        
    except Exception as e:
        logger.error(f"Error processing withdrawal: {e}")
        await query.edit_message_text(f"❌ Error: {str(e)}")

async def notify_user(user_id, text, status=None):
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{PAYMENT_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": user_id,
                    "text": text,
                    "parse_mode": "MarkdownV2"
                }
            )
    except Exception as e:
        logger.error(f"Failed to notify user {user_id}: {e}")

async def handle_withdrawal_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle new withdrawal requests forwarded from payment bot"""
    if update.effective_user.id != ADMIN_CHAT_ID:
        return
    
    if update.message and update.message.forward_from:
        pass

async def deposit_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return
    await deposits(update, context)

async def withdraw_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return
    await withdrawals(update, context)

def main():
    app = Application.builder().token(ADMIN_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("deposits", deposits))
    app.add_handler(CommandHandler("withdrawals", withdrawals))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("deposit_queue", deposit_queue))
    app.add_handler(CommandHandler("withdraw_queue", withdraw_queue))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    logger.info("🔧 Yegara Admin Bot is starting...")
    app.run_polling()

if __name__ == "__main__":
    main()

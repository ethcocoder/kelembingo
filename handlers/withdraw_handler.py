import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import firebase_admin
from firebase_admin import firestore

logger = logging.getLogger(__name__)

db = firestore.client()

async def handle_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle withdrawal request from game wallet screen"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Get user data
    user_doc = db.collection("users").document(str(user_id)).get()
    if not user_doc.exists:
        await query.edit_message_text("❌ User not found.")
        return
    
    user = user_doc.to_dict()
    balance = user.get("balance", 0)
    
    if balance <= 0:
        await query.edit_message_text("❌ Insufficient balance for withdrawal.")
        return
    
    # Show withdrawal form
    text = f"""💸 *Withdrawal Request*

*Your Balance:* {balance:.2f} ETB

Enter the amount you want to withdraw:

*Minimum:* 10 ETB
*Maximum:* {balance:.2f} ETB

Send the amount as a number (e.g., 50)"""
    
    await query.edit_message_text(text, parse_mode='Markdown')
    context.user_state = "awaiting_withdraw_amount"

async def process_withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process the withdrawal amount entered by user"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    try:
        amount = float(text)
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number.")
        return
    
    if amount < 10:
        await update.message.reply_text("❌ Minimum withdrawal is 10 ETB.")
        return
    
    # Get user balance
    user_doc = db.collection("users").document(str(user_id)).get()
    if not user_doc.exists:
        await update.message.reply_text("❌ User not found.")
        return
    
    balance = user_doc.to_dict().get("balance", 0)
    
    if amount > balance:
        await update.message.reply_text(f"❌ Insufficient balance. Your balance: {balance:.2f} ETB")
        return
    
    # Ask for TeleBirr number
    text = f"""📱 *TeleBirr Number*

Amount: *{amount:.2f} ETB*

Please enter your TeleBirr phone number:
Format: +251XXXXXXXXX"""
    
    await update.message.reply_text(text, parse_mode='Markdown')
    context.user_data = {"withdraw_amount": amount}
    context.user_state = "awaiting_telebirr_number"

async def process_telebirr_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process the TeleBirr number and create withdrawal request"""
    user = update.effective_user
    telebirr = update.message.text.strip()
    amount = context.user_data.get("withdraw_amount", 0)
    
    # Validate phone number
    if not telebirr.startswith("+251") or len(telebirr) < 12:
        await update.message.reply_text("❌ Invalid phone number. Must start with +251 and be at least 12 digits.")
        return
    
    # Deduct from balance
    user_ref = db.collection("users").document(str(user.id))
    user_doc = user_ref.get()
    current_balance = user_doc.to_dict().get("balance", 0)
    
    if amount > current_balance:
        await update.message.reply_text("❌ Insufficient balance.")
        return
    
    user_ref.update({
        "balance": current_balance - amount,
        "updatedAt": datetime.utcnow()
    })
    
    # Create withdrawal request
    withdrawal_data = {
        "userId": user.id,
        "username": user.username or "unknown",
        "firstName": user.first_name,
        "amount": amount,
        "telebirrNumber": telebirr,
        "status": "pending",
        "createdAt": datetime.utcnow(),
        "processedAt": None,
        "adminNote": ""
    }
    
    doc_ref = db.collection("withdrawals").add(withdrawal_data)
    withdrawal_id = doc_ref[1].id
    
    text = f"""✅ *Withdrawal Request Submitted\!*

💰 *Amount:* {amount:.2f} ETB
📱 *TeleBirr:* `{telebirr}`
⏳ *Status:* Pending

*Note:* Balance has been temporarily deducted.
You'll receive the money within 24 hours after admin approval.

Request ID: `{withdrawal_id}`"""
    
    await update.message.reply_text(text, parse_mode='Markdown')
    
    # TODO: Notify admin bot about withdrawal request
    logger.info(f"Withdrawal request {withdrawal_id} created for user {user.id}")

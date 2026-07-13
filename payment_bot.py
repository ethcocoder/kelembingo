import os
import io
import hashlib
import logging
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import firebase_admin
from firebase_admin import credentials, firestore

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Firebase
cred = credentials.Certificate(os.path.join(os.path.dirname(__file__), "bingo-bot-5c708-firebase-adminsdk-fbsvc-c5d4b699f3.json"))
firebase_admin.initialize_app(cred)
db = firestore.client()

PAYMENT_BOT_TOKEN = os.getenv("PAYMENT_BOT_TOKEN", "YOUR_PAYMENT_BOT_TOKEN_HERE")
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN", "YOUR_ADMIN_BOT_TOKEN_HERE")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "YOUR_TELEGRAM_USER_ID")

TELEBIRR_NUMBER = "+251911000000"
RATE_LIMIT_HOURS = 1
MAX_DEPOSITS_PER_HOUR = 3
MAX_PENDING_DEPOSITS = 3
DEPOSIT_TIMEOUT_MINUTES = 30

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = f"""💰 *Yegara Pay Bot*

Welcome {user.first_name}!

I process your TeleBirr deposits securely.

*How to deposit:*
1\. Pay to TeleBirr number: `{TELEBIRR_NUMBER}`
2\. Take a screenshot of the receipt
3\. Send the screenshot here
4\. Wait for admin approval

Your balance will be updated automatically after approval\.

Type /help for more info\."""
    await update.message.reply_text(text, parse_mode='MarkdownV2')

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """💰 *Deposit Help*

*Steps:*
1\. Open TeleBirr app
2\. Send payment to: `+251911000000`
3\. Screenshot the receipt
4\. Send screenshot here

*Supported amounts:* Any amount
*Processing time:* Usually under 5 minutes

*Commands:*
/deposit - Start deposit process
/status - Check pending deposits
/balance - Check your balance
/cancel - Cancel current deposit

*Security:*
• Each screenshot is verified
• Duplicate screenshots are rejected
• Transaction IDs are tracked"""
    await update.message.reply_text(text, parse_mode='Markdown')

async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Check rate limit
    recent_deposits = await check_rate_limit(user_id)
    if recent_deposits >= MAX_DEPOSITS_PER_HOUR:
        await update.message.reply_text("⚠️ Rate limit reached. Please wait before making another deposit.")
        return
    
    # Check pending deposits
    pending = await get_pending_deposits(user_id)
    if pending >= MAX_PENDING_DEPOSITS:
        await update.message.reply_text("⚠️ You have too many pending deposits. Please wait for approval.")
        return
    
    text = f"""💳 *Deposit Process Started*

Pay to this TeleBirr number:
`{TELEBIRR_NUMBER}`

*Important:*
• Send the EXACT amount you want to deposit
• Screenshot must show the full receipt
• Include Transaction ID in the screenshot

When ready, send your screenshot below\!"""
    await update.message.reply_text(text, parse_mode='Markdown')
    context.user_state = "awaiting_screenshot"

async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not update.message.photo:
        await update.message.reply_text("❌ Please send a screenshot image, not text.")
        return
    
    # Get the photo
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = await file.download_as_bytearray()
    
    # Calculate image hash for duplicate detection
    image_hash = hashlib.sha256(bytes(image_bytes)).hexdigest()
    
    # Check for duplicate screenshot
    if await is_duplicate_screenshot(image_hash):
        await update.message.reply_text("❌ This screenshot has already been used. Please send a new one.")
        return
    
    # Extract text from image using OCR
    await update.message.reply_text("🔍 Analyzing screenshot...")
    
    extracted = extract_text_from_image(bytes(image_bytes))
    
    if not extracted.get("transaction_id"):
        await update.message.reply_text(
            "❌ Could not extract transaction details.\n\n"
            "Please make sure:\n"
            "• Screenshot is clear and readable\n"
            "• Shows the transaction ID\n"
            "• Shows the amount\n\n"
            "Try sending a clearer screenshot."
        )
        return
    
    # Check if transaction ID already used
    if await is_duplicate_transaction(extracted["transaction_id"]):
        await update.message.reply_text(
            f"❌ Transaction ID `{extracted['transaction_id']}` has already been processed.\n\n"
            "Each transaction can only be used once.",
            parse_mode='Markdown'
        )
        return
    
    # Store deposit in Firestore
    deposit_data = {
        "userId": user.id,
        "username": user.username or "unknown",
        "firstName": user.first_name,
        "amount": extracted.get("amount", 0),
        "transactionId": extracted["transaction_id"],
        "senderName": extracted.get("sender_name", "Unknown"),
        "recipientName": extracted.get("recipient_name", "Unknown"),
        "status": "pending",
        "imageHash": image_hash,
        "extractedText": extracted.get("raw_text", ""),
        "createdAt": datetime.utcnow(),
        "processedAt": None,
        "adminNote": ""
    }
    
    doc_ref = db.collection("deposits").add(deposit_data)
    deposit_id = doc_ref[1].id
    
    # Confirm to user
    text = f"""✅ *Screenshot Received\!*

💳 *Payment Details:*
• Amount: *{extracted.get('amount', 'Unknown')} ETB*
• Name: `{extracted.get('sender_name', 'Unknown')}`
• Transaction ID: `{extracted['transaction_id']}`
• Time: {extracted.get('time', 'Unknown')}

⏳ *Waiting for admin approval\.\.\.*
You'll be notified once processed\.

Deposit ID: `{deposit_id}`"""
    
    await update.message.reply_text(text, parse_mode='MarkdownV2')
    
    # Notify admin
    await notify_admin(deposit_data, deposit_id)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Get user's recent deposits
    deposits = db.collection("deposits").where("userId", "==", user_id).order_by("createdAt", direction=firestore.Query.DESCENDING).limit(5).get()
    
    if not deposits:
        await update.message.reply_text("📊 No deposits found.")
        return
    
    text = "📊 *Your Recent Deposits:*\n\n"
    for doc in deposits:
        d = doc.to_dict()
        status_emoji = {"pending": "⏳", "approved": "✅", "rejected": "❌"}.get(d["status"], "❓")
        text += f"{status_emoji} *{d.get('amount', 0)} ETB* - {d['status'].upper()}\n"
        text += f"   TXN: `{d.get('transactionId', 'N/A')}`\n"
        text += f"   Date: {d['createdAt'].strftime('%Y-%m-%d %H:%M')}\n\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def check_rate_limit(user_id):
    one_hour_ago = datetime.utcnow() - timedelta(hours=RATE_LIMIT_HOURS)
    deposits = db.collection("deposits").where("userId", "==", user_id).where("createdAt", ">=", one_hour_ago).get()
    return len(list(deposits))

async def get_pending_deposits(user_id):
    deposits = db.collection("deposits").where("userId", "==", user_id).where("status", "==", "pending").get()
    return len(list(deposits))

async def is_duplicate_screenshot(image_hash):
    deposits = db.collection("deposits").where("imageHash", "==", image_hash).get()
    return len(list(deposits)) > 0

async def is_duplicate_transaction(transaction_id):
    deposits = db.collection("deposits").where("transactionId", "==", transaction_id).get()
    return len(list(deposits)) > 0

def extract_text_from_image(image_bytes):
    """Extract transaction details from TeleBirr screenshot"""
    try:
        import pytesseract
        from PIL import Image
        
        img = Image.open(io.BytesIO(image_bytes))
        text = pytesseract.image_to_string(img)
        
        result = {"raw_text": text}
        
        # Extract Transaction ID
        txn_patterns = [
            r'(?:Transaction\s*ID|TXN|Ref|Reference)[:\s]*([A-Z0-9]{8,})',
            r'(?:Transaction\s*ID|TXN|Ref|Reference)[:\s]*(\d{8,})',
            r'TXN(\d{8,})',
            r'([A-Z0-9]{12,})',
        ]
        for pattern in txn_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["transaction_id"] = match.group(1)
                break
        
        # Extract Amount
        amount_patterns = [
            r'(?:Amount|Total|ETB)[:\s]*([\d,.]+)',
            r'([\d,.]+)\s*ETB',
            r'ETB\s*([\d,.]+)',
        ]
        for pattern in amount_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount_str = match.group(1).replace(",", "")
                try:
                    result["amount"] = float(amount_str)
                except ValueError:
                    pass
                break
        
        # Extract Names
        name_patterns = [
            r'(?:From|Sender|Payer)[:\s]*([A-Za-z\s]+)',
            r'(?:To|Recipient|Payee)[:\s]*([A-Za-z\s]+)',
        ]
        for i, pattern in enumerate(name_patterns):
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if i == 0:
                    result["sender_name"] = match.group(1).strip()
                else:
                    result["recipient_name"] = match.group(1).strip()
        
        return result
        
    except ImportError:
        logger.warning("pytesseract not installed, using basic extraction")
        return {"raw_text": "OCR not available", "transaction_id": None}
    except Exception as e:
        logger.error(f"OCR error: {e}")
        return {"raw_text": str(e), "transaction_id": None}

async def notify_admin(deposit_data, deposit_id):
    """Notify admin about new deposit"""
    try:
        import httpx
        
        text = f"""💰 *New Deposit Request\!*

👤 *User:* {deposit_data['firstName']} (@{deposit_data['username']})
🆔 *User ID:* `{deposit_data['userId']}`
💳 *Amount:* *{deposit_data.get('amount', 'Unknown')} ETB*
📝 *Transaction ID:* `{deposit_data.get('transactionId', 'N/A')}`
👤 *Sender Name:* {deposit_data.get('senderName', 'Unknown')}
⏰ *Time:* {deposit_data['createdAt'].strftime('%Y-%m-%d %H:%M:%S')}

Deposit ID: `{deposit_id}`"""
        
        keyboard = [[
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{deposit_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{deposit_id}")
        ]]
        
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{ADMIN_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": ADMIN_CHAT_ID,
                    "text": text,
                    "parse_mode": "MarkdownV2",
                    "reply_markup": {"inline_keyboard": keyboard}
                }
            )
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")

def main():
    app = Application.builder().token(PAYMENT_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("deposit", deposit))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    
    logger.info("💳 Yegara Pay Bot is starting...")
    app.run_polling()

if __name__ == "__main__":
    main()

import logging
import os
import re
import hashlib
import asyncio
from datetime import datetime, timezone

from telegram import (
    Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove,
    InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters,
)
from config import (
    db, BOT_TOKEN, ADMIN_CHAT_ID, ADMIN_BOT_TOKEN,
    DEFAULT_STAKE_10, DEFAULT_STAKE_20,
    SUPPORT_USERNAME, REFERRAL_BONUS, BONUS_TO_ETB_RATE, MIN_WITHDRAW,
    TELEBIRR_NUMBER,
)
from telegram import Bot
from handlers.user_manager import UserManager
from firestore_db import FieldFilter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

user_manager = UserManager(db)
ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')

# ─── Conversation states ───
REG_NAME, REG_CONTACT = 0, 1
AWAIT_PHOTO = 3
DEPOSIT_AMOUNT, DEPOSIT_TELEBIRR_NAME = 11, 12
WITHDRAW_AMOUNT, WITHDRAW_TELEBIRR_NAME = 4, 13
TRANSFER_ID, TRANSFER_AMOUNT, TRANSFER_CONFIRM = 6, 7, 8
BONUS_CONFIRM = 9
PLAY_STAKE = 10

MAIN_KEYBOARD = ReplyKeyboardRemove()
MAIN_INLINE_KEYBOARD = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("Play 🎮", callback_data="menu_play"), InlineKeyboardButton("Register 📝", callback_data="menu_register")],
        [InlineKeyboardButton("Check Balance 💵", callback_data="menu_balance"), InlineKeyboardButton("Deposit 💵", callback_data="menu_deposit")],
        [InlineKeyboardButton("Contact Support ☎️", callback_data="menu_support"), InlineKeyboardButton("Instruction 📖", callback_data="menu_instruction")],
        [InlineKeyboardButton("Transfer 🎁", callback_data="menu_transfer"), InlineKeyboardButton("Withdraw 🤑", callback_data="menu_withdraw")],
        [InlineKeyboardButton("Invite 🔗", callback_data="menu_invite"), InlineKeyboardButton("Convert Bonus 💸", callback_data="menu_bonus")],
    ]
)


def _admin_id():
    return int(ADMIN_CHAT_ID) if ADMIN_CHAT_ID else 8462274722


# ═══════════════════════════════════════════════════════════════════
# /start
# ═══════════════════════════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = await user_manager.get_or_create_user(user.id, user.first_name, user.username or "")

    # Referral tracking
    if context.args and context.args[0].startswith("ref_"):
        try:
            referrer_id = int(context.args[0][4:])
            if referrer_id != user.id:
                await user_manager.set_referred_by(user.id, referrer_id)
                ref_user = await user_manager.get_user(referrer_id)
                if ref_user:
                    await user_manager.add_referral_bonus(referrer_id, REFERRAL_BONUS)
        except (ValueError, IndexError):
            pass

    text = "👋 Welcome to Yegara Bingo! Choose an Option below."
    banner_path = os.path.join(ASSETS_DIR, 'welcome_banner.png')
    try:
        if os.path.exists(banner_path):
            with open(banner_path, 'rb') as photo:
                await update.effective_message.reply_photo(
                    photo=photo,
                    caption=text,
                    reply_markup=MAIN_INLINE_KEYBOARD,
                    read_timeout=30,
                    write_timeout=60,
                    connect_timeout=30
                )
        else:
            await update.effective_message.reply_text(text, reply_markup=MAIN_INLINE_KEYBOARD)
    except Exception as e:
        logger.warning(f"Banner upload failed, sending text only: {e}")
        await update.effective_message.reply_text(text, reply_markup=MAIN_INLINE_KEYBOARD)

    await update.effective_message.reply_text(
        "🎮 ጨዋታውን ለመጀመር ከታች ያለውን Play የሚለውን ይጫኑ::\n"
        "(Click Play below to start the game)"
    )


# ═══════════════════════════════════════════════════════════════════
# 🎮 Play — Opens the Mini App directly
# ═══════════════════════════════════════════════════════════════════
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://yegarabingo.onrender.com/game")

async def handle_play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    uid = update.effective_user.id
    u = await user_manager.get_user(uid)
    if not u:
        await update.effective_message.reply_text("Please /start first.")
        return

    is_reg = u.get('registered') or (u.get('phone') and len(u.get('phone')) > 0)
    if not is_reg:
        await update.effective_message.reply_text(
            "⚠️ You must register first to play!\n\n"
            "Please tap *📝 Register* from the main menu or use the button below.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📝 Register", callback_data="menu_register")]]),
            parse_mode='Markdown'
        )
        return

    pw = u.get('play_wallet', 0)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Play Now — 10 ETB", web_app=WebAppInfo(url=WEBAPP_URL))],
    ])
    await update.effective_message.reply_text(
        f"💰 Your Play Wallet: *{pw} ETB*\n\n"
        f"🎯 Stake: *10 ETB* per cartela (max 2)\n"
        f"🏆 Prize: *(Players × Stake × 0.75) / Winners*\n\n"
        f"Tap below to open the game:",
        reply_markup=kb, parse_mode='Markdown',
    )


# ═══════════════════════════════════════════════════════════════════
# 📝 Register
# ═══════════════════════════════════════════════════════════════════
async def handle_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    uid = update.effective_user.id
    if await user_manager.is_registered(uid):
        u = await user_manager.get_user(uid)
        await update.effective_message.reply_text(
            f"✅ You are already registered!\n\n"
            f"Name: {u.get('first_name', '')}\n"
            f"Phone: {u.get('phone', '')}",
            reply_markup=MAIN_KEYBOARD,
        )
        return ConversationHandler.END

    kb = ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Share Contact", request_contact=True)]],
        one_time_keyboard=True, resize_keyboard=True,
    )
    await update.effective_message.reply_text(
        "📱 Tap the button below to share your contact:",
        reply_markup=kb,
    )
    return REG_CONTACT


async def reg_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    if not contact:
        await update.message.reply_text("❌ Please tap the Share Contact button below.")
        return REG_CONTACT

    phone = contact.phone_number
    if not phone.startswith('+'):
        phone = '+' + phone

    name = update.effective_user.first_name or ''
    await user_manager.register_user(update.effective_user.id, name, phone, '')
    await update.message.reply_text(
        f"✅ Registration complete!\n\n"
        f"Name: {name}\n"
        f"Phone: {phone}",
        reply_markup=MAIN_KEYBOARD,
    )
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════
# 💵 Check Balance
# ═══════════════════════════════════════════════════════════════════
async def handle_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    uid = update.effective_user.id
    info = await user_manager.get_balance_info(uid)
    if not info:
        await update.effective_message.reply_text("Please /start first.", reply_markup=MAIN_KEYBOARD)
        return

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💵 Deposit", callback_data="bal_deposit"),
         InlineKeyboardButton("🤑 Withdraw", callback_data="bal_withdraw")],
    ])
    
    text = (
        f"💼 *Account Info*\n\n"
        f"Name:       {info['first_name']}\n"
        f"Main wallet: {info['balance']:.1f}\n"
        f"Play wallet: {info['play_wallet']:.1f}\n"
        f"Coin:        {info['bonus']}"
    )

    await update.effective_message.reply_text(
        text,
        reply_markup=kb, parse_mode='Markdown',
    )


# ═══════════════════════════════════════════════════════════════════
# 💵 Deposit
# ═══════════════════════════════════════════════════════════════════
async def handle_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        return await _show_deposit_flow(update.callback_query, context)
    return await _show_deposit_flow_msg(update, context)


async def _show_deposit_flow_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await user_manager.get_user(uid)
    if not u:
        await update.effective_message.reply_text("Please /start first.", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END

    # Check pending deposits limit
    pending = db.collection('deposits').where('userId', '==', str(uid)).where('status', '==', 'pending').get()
    if len(list(pending)) >= 3:
        await update.effective_message.reply_text(
            "⚠️ You have too many pending deposits.\nWait for them to be processed.",
            reply_markup=MAIN_KEYBOARD,
        )
        return ConversationHandler.END

    await update.effective_message.reply_text(
        "💵 *Deposit via TeleBirr*\n\nHow much ETB do you want to deposit? (Minimum 10)",
        parse_mode='Markdown',
    )
    return DEPOSIT_AMOUNT


async def _show_deposit_flow(query, context):
    uid = query.from_user.id
    u = await user_manager.get_user(uid)
    if not u:
        await query.edit_message_text("Please /start first.")
        return ConversationHandler.END
    pending = db.collection('deposits').where('userId', '==', str(uid)).where('status', '==', 'pending').get()
    if len(list(pending)) >= 3:
        await query.edit_message_text("⚠️ Too many pending deposits. Wait for processing.")
        return ConversationHandler.END

    await query.edit_message_text(
        "💵 *Deposit via TeleBirr*\n\nHow much ETB do you want to deposit? (Minimum 10)",
        parse_mode='Markdown',
    )
    return DEPOSIT_AMOUNT


async def deposit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.strip())
        if amount < 10:
            await update.effective_message.reply_text("⚠️ Minimum deposit is 10 ETB. Please enter again.")
            return DEPOSIT_AMOUNT
    except ValueError:
        await update.effective_message.reply_text("❌ Invalid amount. Please enter a number.")
        return DEPOSIT_AMOUNT

    context.user_data['deposit_amount'] = amount
    await update.effective_message.reply_text(
        "💰 Please enter your TeleBirr name\n"
        "(The name registered on your TeleBirr account):"
    )
    return DEPOSIT_TELEBIRR_NAME


async def deposit_telebirr_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['telebirr_name'] = update.message.text.strip()
    uid = update.effective_user.id
    await user_manager.set_awaiting_screenshot(uid, True)
    amount = context.user_data.get('deposit_amount', 0)
    await update.effective_message.reply_text(
        f"💵 *Deposit {amount} ETB via TeleBirr*\n\n"
        f"1. Send *{TELEBIRR_NUMBER}* via TeleBirr\n"
        f"2. Take a screenshot of the confirmation\n"
        f"3. Send the screenshot here\n\n"
        f"⏳ Waiting for your screenshot...",
        parse_mode='Markdown',
    )
    return AWAIT_PHOTO


async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await user_manager.get_user(uid)

    if not u or not u.get('awaiting_screenshot'):
        return

    # Check admin online
    admin_online = await _is_admin_online()
    if not admin_online:
        await update.effective_message.reply_text(
            "⚠️ Admin is offline. Please try again later.",
            reply_markup=MAIN_KEYBOARD,
        )
        await user_manager.set_awaiting_screenshot(uid, False)
        return ConversationHandler.END

    photo = update.message.photo
    if not photo:
        await update.effective_message.reply_text("Please send a photo (screenshot).")
        return AWAIT_PHOTO

    await update.effective_message.reply_text("⏳ Processing your deposit...")

    # Download and hash image
    file = await photo[-1].get_file()
    image_bytes = await file.download_as_bytearray()
    image_hash = hashlib.sha256(bytes(image_bytes)).hexdigest()

    # Check duplicate image
    existing = db.collection('deposits').where('imageHash', '==', image_hash).limit(1).get()
    if existing:
        await update.effective_message.reply_text("❌ This screenshot was already submitted.", reply_markup=MAIN_KEYBOARD)
        await user_manager.set_awaiting_screenshot(uid, False)
        return ConversationHandler.END

    # OCR extraction
    extracted = await asyncio.to_thread(_extract_text_from_image, bytes(image_bytes))

    txn_id = extracted.get('transaction_ref') or f"IMG-{image_hash[:12]}"
    amount = context.user_data.get('deposit_amount', extracted.get('amount') or 0)
    sender_name = extracted.get('receiver_name') or extracted.get('sender_name') or u.get('first_name', 'Unknown')

    # Check duplicate transaction ID
    if txn_id and not txn_id.startswith("IMG-"):
        dup = db.collection('deposits').where('transactionId', '==', txn_id).limit(1).get()
        if dup:
            await update.effective_message.reply_text("❌ This transaction was already submitted.", reply_markup=MAIN_KEYBOARD)
            await user_manager.set_awaiting_screenshot(uid, False)
            return ConversationHandler.END

    deposit_data = {
        'userId': str(uid),
        'username': update.effective_user.username or '',
        'firstName': update.effective_user.first_name or '',
        'telebirrName': context.user_data.get('telebirr_name', ''),
        'amount': amount,
        'transactionId': txn_id,
        'senderName': sender_name,
        'status': 'pending',
        'imageHash': image_hash,
        'imageFileId': photo[-1].file_id,
        'ocr': {
            'status': extracted.get('status', 'unknown'),
            'amount': extracted.get('amount', 0),
            'transactionDate': extracted.get('transaction_date'),
            'transactionType': extracted.get('transaction_type'),
            'receiverName': extracted.get('receiver_name'),
            'transactionRef': extracted.get('transaction_ref'),
            'senderName': extracted.get('sender_name'),
            'rawText': extracted.get('raw_text', ''),
            'confidence': extracted.get('confidence', 0.0),
        },
        'createdAt': datetime.now(tz=timezone.utc),
        'processedAt': None,
        'adminNote': '',
    }
    deposit_ref = db.collection('deposits').document()
    deposit_ref.set(deposit_data)
    deposit_id = deposit_ref.id

    await user_manager.set_awaiting_screenshot(uid, False)

    ocr = deposit_data['ocr']
    amount_text = f"{amount} ETB" if amount else "not detected"
    status_icon = "✅" if ocr['status'] == 'success' else "❌" if ocr['status'] == 'failed' else "❓"
    date_text = ocr['transactionDate'] or "not detected"
    ref_text = txn_id if not txn_id.startswith("IMG-") else "not detected"

    await update.effective_message.reply_text(
        f"✅ Deposit request submitted!\n\n"
        f"💵 Amount: {amount_text}\n"
        f"{status_icon} Status: {ocr['status']}\n"
        f"👤 Receiver: {sender_name}\n"
        f"🔖 Reference: {ref_text}\n"
        f"📅 Date: {date_text}\n"
        f"🆔 `{deposit_id}`",
        reply_markup=MAIN_KEYBOARD, parse_mode='Markdown',
    )

    await _notify_admin_deposit(deposit_data, deposit_id, context)
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════
# 🎰 Withdraw
# ═══════════════════════════════════════════════════════════════════
async def handle_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        return await _show_withdraw_flow(update.callback_query, context)
    return await _show_withdraw_flow_msg(update, context)


async def _show_withdraw_flow_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await user_manager.get_user(uid)
    if not u:
        await update.effective_message.reply_text("Please /start first.", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END

    bal = u.get('balance', 0)
    if bal < MIN_WITHDRAW:
        await update.effective_message.reply_text(
            f"❌ Minimum withdrawal is {MIN_WITHDRAW} ETB.\nYour balance: {bal} ETB",
            reply_markup=MAIN_KEYBOARD,
        )
        return ConversationHandler.END

    await update.effective_message.reply_text(
        f"🎰 *Withdraw*\n\nYour balance: *{bal} ETB*\nMinimum: {MIN_WITHDRAW} ETB\n\nEnter amount:",
        reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown',
    )
    return WITHDRAW_AMOUNT


async def _show_withdraw_flow(query, context):
    uid = query.from_user.id
    u = await user_manager.get_user(uid)
    if not u:
        await query.edit_message_text("Please /start first.")
        return ConversationHandler.END
    bal = u.get('balance', 0)
    if bal < MIN_WITHDRAW:
        await query.edit_message_text(f"❌ Minimum {MIN_WITHDRAW} ETB. Balance: {bal} ETB")
        return ConversationHandler.END
    await query.edit_message_text(f"🎰 Withdraw — Balance: {bal} ETB\n\nEnter amount:")
    return WITHDRAW_AMOUNT


async def withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.strip())
    except ValueError:
        await update.effective_message.reply_text("❌ Enter a valid number.")
        return WITHDRAW_AMOUNT

    uid = update.effective_user.id
    u = await user_manager.get_user(uid)
    bal = u.get('balance', 0) if u else 0

    if amount < MIN_WITHDRAW or amount > bal:
        await update.effective_message.reply_text(f"❌ Enter amount between {MIN_WITHDRAW} and {bal} ETB.")
        return WITHDRAW_AMOUNT

    context.user_data['withdraw_amount'] = amount
    await update.effective_message.reply_text(
        "💰 Please enter your TeleBirr name\n"
        "(The name registered on your TeleBirr account):"
    )
    return WITHDRAW_TELEBIRR_NAME


async def withdraw_telebirr_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['telebirr_name'] = update.message.text.strip()
    uid = update.effective_user.id
    u = await user_manager.get_user(uid)
    amount = context.user_data.get('withdraw_amount', 0)
    phone = u.get('phone', '') if u else ''
    return await _process_withdraw(update, context, uid, amount, phone)


async def _process_withdraw(update, context, uid, amount, phone):
    u = await user_manager.get_user(uid)
    withdrawal_data = {
        'userId': str(uid),
        'username': update.effective_user.username or '',
        'firstName': update.effective_user.first_name or '',
        'telebirrName': context.user_data.get('telebirr_name', '') if u else '',
        'amount': amount,
        'phone': phone,
        'status': 'pending',
        'createdAt': datetime.now(tz=timezone.utc),
        'processedAt': None,
        'adminNote': '',
    }
    ref = db.collection('withdrawals').document()
    ref.set(withdrawal_data)

    await user_manager.deduct_balance(uid, amount)

    await update.effective_message.reply_text(
        f"✅ Withdrawal request submitted!\n\n"
        f"Amount: {amount} ETB\n"
        f"Phone: {phone}\n"
        f"ID: `{ref.id}`\n\n"
        f"Admin will process it shortly.",
        reply_markup=MAIN_KEYBOARD, parse_mode='Markdown',
    )

    await _notify_admin_withdrawal(withdrawal_data, ref.id, context)
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════
# 🎁 Transfer
# ═══════════════════════════════════════════════════════════════════
async def handle_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    uid = update.effective_user.id
    u = await user_manager.get_user(uid)
    if not u:
        await update.effective_message.reply_text("Please /start first.", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END

    bal = u.get('balance', 0)
    if bal < 1:
        await update.effective_message.reply_text(
            f"❌ No balance to transfer.\nYour balance: {bal} ETB",
            reply_markup=MAIN_KEYBOARD,
        )
        return ConversationHandler.END

    await update.effective_message.reply_text(
        f"🎁 *Transfer*\nYour balance: *{bal} ETB*\n\nEnter recipient's Telegram User ID:",
        reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown',
    )
    return TRANSFER_ID


async def transfer_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        recipient_id = int(update.message.text.strip())
    except ValueError:
        await update.effective_message.reply_text("❌ Enter a valid numeric User ID.")
        return TRANSFER_ID

    if recipient_id == update.effective_user.id:
        await update.effective_message.reply_text("❌ You cannot transfer to yourself.")
        return TRANSFER_ID

    recipient = await user_manager.get_user(recipient_id)
    if not recipient:
        await update.effective_message.reply_text("❌ User not found. Check the ID and try again.")
        return TRANSFER_ID

    context.user_data['transfer_to'] = recipient_id
    context.user_data['transfer_to_name'] = recipient.get('first_name', 'Unknown')

    await update.effective_message.reply_text(
        f"👤 Recipient: {recipient.get('first_name', 'Unknown')}\n"
        f"Enter amount to send (ETB):"
    )
    return TRANSFER_AMOUNT


async def transfer_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.strip())
    except ValueError:
        await update.effective_message.reply_text("❌ Enter a valid number.")
        return TRANSFER_AMOUNT

    uid = update.effective_user.id
    u = await user_manager.get_user(uid)
    bal = u.get('balance', 0) if u else 0

    if amount < 1 or amount > bal:
        await update.effective_message.reply_text(f"❌ Enter amount between 1 and {bal} ETB.")
        return TRANSFER_AMOUNT

    context.user_data['transfer_amount'] = amount
    to_name = context.user_data.get('transfer_to_name', 'Unknown')

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirm", callback_data="tf_yes"),
         InlineKeyboardButton("❌ Cancel", callback_data="tf_no")],
    ])
    await update.effective_message.reply_text(
        f"🎁 Send *{amount} ETB* to *{to_name}*?",
        reply_markup=kb, parse_mode='Markdown',
    )
    return TRANSFER_CONFIRM


async def transfer_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "tf_no":
        await query.edit_message_text("❌ Transfer cancelled.")
        return ConversationHandler.END

    uid = query.from_user.id
    recipient_id = context.user_data.get('transfer_to')
    amount = context.user_data.get('transfer_amount', 0)

    success = await user_manager.transfer_funds(uid, recipient_id, amount)
    if success:
        to_name = context.user_data.get('transfer_to_name', 'Unknown')
        await query.edit_message_text(
            f"✅ Sent *{amount} ETB* to *{to_name}* successfully!",
            parse_mode='Markdown',
        )
    else:
        await query.edit_message_text("❌ Transfer failed. Check your balance and try again.")
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════
# 🔄 Convert Bonus
# ═══════════════════════════════════════════════════════════════════
async def handle_convert_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    uid = update.effective_user.id
    u = await user_manager.get_user(uid)
    if not u:
        await update.effective_message.reply_text("Please /start first.", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END

    coins = u.get('bonus', 0)
    if coins <= 0:
        await update.effective_message.reply_text("❌ No bonus coins to convert.", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END

    etb = coins / BONUS_TO_ETB_RATE
    context.user_data['convert_etb'] = etb
    context.user_data['convert_coins'] = coins

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✅ Convert {coins} coins → {etb} ETB", callback_data="bonus_yes"),
         InlineKeyboardButton("❌ Cancel", callback_data="bonus_no")],
    ])
    await update.effective_message.reply_text(
        f"🔄 *Convert Bonus*\n\n"
        f"You have: *{coins} coins*\n"
        f"Rate: {BONUS_TO_ETB_RATE} coins = 1 ETB\n"
        f"You will receive: *{etb} ETB* in Play Wallet",
        reply_markup=kb, parse_mode='Markdown',
    )
    return BONUS_CONFIRM


async def bonus_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "bonus_no":
        await query.edit_message_text("❌ Cancelled.")
        return ConversationHandler.END

    uid = query.from_user.id
    etb = await user_manager.convert_bonus(uid, BONUS_TO_ETB_RATE)
    if etb is not None:
        await query.edit_message_text(f"✅ Converted! +{etb} ETB added to your Play Wallet.")
    else:
        await query.edit_message_text("❌ Conversion failed. No bonus available.")
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════
# 🔗 Invite
# ═══════════════════════════════════════════════════════════════════
async def handle_invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    uid = update.effective_user.id
    link = f"https://t.me/yegarabingobot?start=ref_{uid}"
    await update.effective_message.reply_text(
        f"🔗 *Your Referral Link*\n\n"
        f"{link}\n\n"
        f"📤 Share this link with friends!\n"
        f"💰 You earn *{REFERRAL_BONUS} ETB* for each friend who registers.",
        reply_markup=MAIN_KEYBOARD, parse_mode='Markdown',
    )


# ═══════════════════════════════════════════════════════════════════
# 📖 Instruction
# ═══════════════════════════════════════════════════════════════════
async def handle_instruction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    await update.effective_message.reply_text(
        "📖 *How to Play Yegara Bingo*\n\n"
        "1️⃣ Click *Play* and choose your stake (10 or 20 ETB)\n"
        "2️⃣ Select up to *3 cartelas* (bingo cards)\n"
        "3️⃣ The game board opens — numbers are called every 4 seconds\n"
        "4️⃣ Tap numbers on your card to mark them (or use Auto Mark)\n"
        "5️⃣ Complete a full line (row, column, or diagonal) to win!\n\n"
        "🎯 *Winning:* Complete any row, column, or diagonal\n"
        "🏆 *Prize:* 1.5x your stake\n"
        "⭐ *Free Space:* Center cell is always free\n\n"
        "💰 *Wallets:*\n"
        "• Main Wallet — deposit here via TeleBirr\n"
        "• Play Wallet — transfer from main to play\n"
        "• Bonus — earned from referrals\n\n"
        "📤 *Transfer:* Send funds to any user by ID\n"
        "🔄 *Convert Bonus:* Turn bonus coins into Play Wallet",
        reply_markup=MAIN_KEYBOARD, parse_mode='Markdown',
    )


# ═══════════════════════════════════════════════════════════════════
# 🆘 Contact Support
# ═══════════════════════════════════════════════════════════════════
async def handle_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    await update.effective_message.reply_text(
        f"🆘 ድጋፍ ይፈልጋሉ?\n\n"
        f"👇 ለማንኛውም ጥያቄ ወይም አስተያየት 👇\n\n"
        f"👤 @{SUPPORT_USERNAME}"
    )


# ═══════════════════════════════════════════════════════════════════
# Admin notifications
# ═══════════════════════════════════════════════════════════════════
async def _notify_admin_deposit(deposit_data, deposit_id, context):
    try:
        ocr = deposit_data.get('ocr', {})
        status_icon = "✅" if ocr.get('status') == 'success' else "❌" if ocr.get('status') == 'failed' else "❓"
        date_text = ocr.get('transactionDate') or 'N/A'
        ref_text = deposit_data.get('transactionId', 'N/A')
        receiver_text = ocr.get('receiverName') or deposit_data.get('senderName', 'N/A')
        type_text = ocr.get('transactionType') or 'N/A'
        confidence = ocr.get('confidence', 0)

        text = (
            f"💵 *New Deposit Request*\n\n"
            f"👤 *User:* {deposit_data.get('firstName', 'Unknown')} (@{deposit_data.get('username', '')})\n"
            f"📱 *TeleBirr Name:* {deposit_data.get('telebirrName', 'N/A')}\n\n"
            f"━━━ *Screenshot Parsed* ━━━\n"
            f"{status_icon} *Status:* {ocr.get('status', 'unknown')}\n"
            f"💵 *Amount:* {deposit_data.get('amount', 0)} ETB\n"
            f"📅 *Date:* {date_text}\n"
            f"🔖 *Reference:* {ref_text}\n"
            f"👤 *Receiver:* {receiver_text}\n"
            f"📋 *Type:* {type_text}\n"
            f"📊 *Confidence:* {int(confidence * 100)}%\n\n"
            f"🆔 `{deposit_id}`\n"
            f"🕐 {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Approve", callback_data=f"approve_{deposit_id}"),
             InlineKeyboardButton("❌ Reject", callback_data=f"reject_{deposit_id}")],
        ])
        bot = Bot(token=ADMIN_BOT_TOKEN) if ADMIN_BOT_TOKEN else context.bot
        file_id = deposit_data.get('imageFileId')
        if file_id:
            await bot.send_photo(
                chat_id=_admin_id(), photo=file_id,
                caption=text, reply_markup=kb, parse_mode='Markdown',
            )
        else:
            await bot.send_message(
                chat_id=_admin_id(), text=text,
                reply_markup=kb, parse_mode='Markdown',
            )
    except Exception as e:
        logger.error(f"Failed to notify admin (deposit): {e}")


async def _notify_admin_withdrawal(withdrawal_data, withdrawal_id, context):
    try:
        text = (
            f"🎰 *New Withdrawal Request*\n\n"
            f"👤 {withdrawal_data.get('firstName', 'Unknown')} (@{withdrawal_data.get('username', '')})\n"
            f"💰 TeleBirr Name: {withdrawal_data.get('telebirrName', 'N/A')}\n"
            f"💵 Amount: {withdrawal_data.get('amount', 0)} ETB\n"
            f"📱 Phone: {withdrawal_data.get('phone', 'N/A')}\n"
            f"🆔 {withdrawal_id}\n"
            f"🕐 {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Approve", callback_data=f"approve_withdraw_{withdrawal_id}"),
             InlineKeyboardButton("❌ Reject", callback_data=f"reject_withdraw_{withdrawal_id}")],
        ])
        bot = Bot(token=ADMIN_BOT_TOKEN) if ADMIN_BOT_TOKEN else context.bot
        await bot.send_message(
            chat_id=_admin_id(), text=text,
            reply_markup=kb, parse_mode='Markdown',
        )
    except Exception as e:
        logger.error(f"Failed to notify admin (withdrawal): {e}")


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════
async def _is_admin_online() -> bool:
    def _check():
        try:
            doc = db.collection('system').document('admin_status').get()
            if doc.exists:
                return doc.to_dict().get('online', False)
        except Exception:
            pass
        return True
    return await asyncio.to_thread(_check)


def _extract_text_from_image(image_bytes: bytes) -> dict:
    """Parse TeleBirr payment screenshot via OCR. Extracts all 6 fields."""
    try:
        from PIL import Image
        import pytesseract
        import io
        img = Image.open(io.BytesIO(image_bytes))
        raw_text = pytesseract.image_to_string(img)
    except ImportError:
        return {
            "raw_text": "OCR not available",
            "status": "unknown",
            "amount": 0,
            "transaction_date": None,
            "transaction_type": None,
            "receiver_name": None,
            "transaction_ref": None,
            "sender_name": None,
            "confidence": 0.0,
        }

    result = {
        "raw_text": raw_text,
        "status": "unknown",
        "amount": 0,
        "transaction_date": None,
        "transaction_type": None,
        "receiver_name": None,
        "transaction_ref": None,
        "sender_name": None,
        "confidence": 0.0,
    }

    # ── 1. Status (success/failure) ──
    if re.search(r'ተሳክቷል|Success|Completed|✅', raw_text, re.IGNORECASE):
        result["status"] = "success"
    elif re.search(r'አልተሳካም|Failed|Rejected|❌', raw_text, re.IGNORECASE):
        result["status"] = "failed"

    # ── 2. Amount ──
    for pattern in [
        r'(-?[\d,]+\.?\d*)\s*(?:ETB|ብር)',
        r'(?:Amount|Total|ETB|መጠን|ብር)[:\s]*(-?[\d,]+\.?\d*)',
        r'(-[\d,]+\.?\d*)',
    ]:
        m = re.search(pattern, raw_text, re.IGNORECASE)
        if m:
            try:
                result["amount"] = abs(float(m.group(1).replace(',', '')))
                break
            except ValueError:
                continue

    # ── 3. Transaction Date (የግብይቱ ቀን) ──
    for pattern in [
        r'የግብይቱ\s*ቀን[:\s]*(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})',
        r'(?:Date|Time|Transaction\s*Date)[:\s]*(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})',
        r'(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})',
    ]:
        m = re.search(pattern, raw_text, re.IGNORECASE)
        if m:
            result["transaction_date"] = m.group(1).strip()
            break

    # ── 4. Transaction Type (የግብይቱ ዓይነት) ──
    for pattern in [
        r'የግብይቱ\s*ዓይነት[:\s]*([\w\s\u1200-\u137F]+)',
        r'(?:Type|Transaction\s*Type)[:\s]*([\w\s]+)',
    ]:
        m = re.search(pattern, raw_text, re.IGNORECASE)
        if m:
            result["transaction_type"] = m.group(1).strip()
            break

    # ── 5. Receiver Name (ለምፅብ ስም / ለ接收方) ──
    for pattern in [
        r'ለምፅብ\s*ስም[:\s]*([A-Za-z\s]+)',
        r'ለ接收方\s*ስም[:\s]*([A-Za-z\s]+)',
        r'(?:Receiver|To|Beneficiary)[:\s]*([A-Za-z\s]+)',
    ]:
        m = re.search(pattern, raw_text, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            if len(name) >= 2:
                result["receiver_name"] = name
                break

    # ── 6. Transaction Reference (የግብይት ማጣቀሻ) ──
    for pattern in [
        r'የግብይት\s*ማጣቀሻ[:\s]*([A-Za-z0-9]{8,12})',
        r'(?:Transaction\s*Ref|TXN|Ref|Reference)[:\s]*([A-Za-z0-9]{8,12})',
        r'\b([A-Z0-9]{8,12})\b',
    ]:
        m = re.search(pattern, raw_text, re.IGNORECASE)
        if m:
            result["transaction_ref"] = m.group(1).strip()
            break

    # ── Sender (legacy fallback) ──
    m = re.search(r'(?:From|Sender|Payer)[:\s]*([A-Za-z\s]+)', raw_text, re.IGNORECASE)
    if m:
        result["sender_name"] = m.group(1).strip()

    # ── Confidence score ──
    fields_found = sum(1 for v in [
        result["status"] != "unknown",
        result["amount"] > 0,
        result["transaction_date"] is not None,
        result["transaction_ref"] is not None,
    ] if v)
    result["confidence"] = round(fields_found / 4.0, 2)

    return result


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("Cancelled.", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════
def main():
    import asyncio as _asyncio

    async def _pre_start():
        from telegram import Bot
        import asyncio as _aio
        b = Bot(token=BOT_TOKEN)
        await b.delete_webhook(drop_pending_updates=True)
        await _aio.sleep(5)
        me = await b.get_me()
        logger.info(f"✅ Game bot connected: @{me.username}")

    _asyncio.run(_pre_start())

    app = Application.builder().token(BOT_TOKEN).read_timeout(30).write_timeout(30).connect_timeout(30).pool_timeout(30).build()

    # ─── /start ───
    app.add_handler(CommandHandler("start", start))

    # ─── Simple menu handlers (no conversation needed) ───
    app.add_handler(MessageHandler(filters.Regex("^💵 Check Balance$"), handle_balance))
    app.add_handler(MessageHandler(filters.Regex("^🔗 Invite$"), handle_invite))
    app.add_handler(MessageHandler(filters.Regex("^📖 Instruction$"), handle_instruction))
    app.add_handler(MessageHandler(filters.Regex("^🆘 Contact Support$"), handle_support))

    # ─── Play handler (no conversation — just opens webapp) ───
    app.add_handler(MessageHandler(filters.Regex("^🎮 Play$"), handle_play))
    app.add_handler(CallbackQueryHandler(handle_play, pattern="^menu_play$"))

    # ─── ConversationHandler: Register ───
    reg_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^📝 Register$"), handle_register),
            CallbackQueryHandler(handle_register, pattern="^menu_register$"),
        ],
        per_message=False,
        states={
            REG_CONTACT: [MessageHandler(filters.CONTACT, reg_contact),
                          MessageHandler(filters.TEXT & ~filters.COMMAND, reg_contact)],
        },
        fallbacks=[CommandHandler("start", start), MessageHandler(filters.Regex("^Cancel$"), cancel)],
    )
    app.add_handler(reg_conv, group=2)

    # ─── ConversationHandler: Deposit ───
    deposit_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^💵 Deposit$"), handle_deposit),
            CallbackQueryHandler(handle_deposit, pattern="^menu_deposit$"),
            CallbackQueryHandler(handle_deposit, pattern="^bal_deposit$"),
        ],
        per_message=False,
        states={
            DEPOSIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_amount)],
            DEPOSIT_TELEBIRR_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_telebirr_name)],
            AWAIT_PHOTO: [MessageHandler(filters.PHOTO, handle_screenshot)],
        },
        fallbacks=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex("^Cancel$"), cancel),
            CallbackQueryHandler(handle_deposit, pattern="^menu_deposit$"),
            CallbackQueryHandler(handle_deposit, pattern="^bal_deposit$"),
        ],
    )
    app.add_handler(deposit_conv, group=3)

    # ─── ConversationHandler: Withdraw ───
    withdraw_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🎰 Withdraw$"), handle_withdraw),
            CallbackQueryHandler(handle_withdraw, pattern="^menu_withdraw$"),
            CallbackQueryHandler(handle_withdraw, pattern="^bal_withdraw$"),
        ],
        per_message=False,
        states={
            WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount)],
            WITHDRAW_TELEBIRR_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_telebirr_name)],
        },
        fallbacks=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex("^Cancel$"), cancel),
            CallbackQueryHandler(handle_withdraw, pattern="^menu_withdraw$"),
            CallbackQueryHandler(handle_withdraw, pattern="^bal_withdraw$"),
        ],
    )
    app.add_handler(withdraw_conv, group=4)

    # ─── ConversationHandler: Transfer ───
    transfer_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🎁 Transfer$"), handle_transfer), CallbackQueryHandler(handle_transfer, pattern="^menu_transfer$")],
        per_message=False,
        states={
            TRANSFER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, transfer_id)],
            TRANSFER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, transfer_amount)],
            TRANSFER_CONFIRM: [CallbackQueryHandler(transfer_confirm, pattern="^tf_")],
        },
        fallbacks=[CommandHandler("start", start), MessageHandler(filters.Regex("^Cancel$"), cancel)],
    )
    app.add_handler(transfer_conv, group=5)

    # ─── ConversationHandler: Convert Bonus ───
    bonus_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔄 Convert Bonus$"), handle_convert_bonus), CallbackQueryHandler(handle_convert_bonus, pattern="^menu_bonus$")],
        per_message=False,
        states={
            BONUS_CONFIRM: [CallbackQueryHandler(bonus_confirm, pattern="^bonus_")],
        },
        fallbacks=[CommandHandler("start", start), MessageHandler(filters.Regex("^Cancel$"), cancel)],
    )
    app.add_handler(bonus_conv, group=6)

    # ─── New Inline Menu Callbacks ───
    app.add_handler(CallbackQueryHandler(handle_balance, pattern="^menu_balance$"))
    app.add_handler(CallbackQueryHandler(handle_invite, pattern="^menu_invite$"))
    app.add_handler(CallbackQueryHandler(handle_instruction, pattern="^menu_instruction$"))
    app.add_handler(CallbackQueryHandler(handle_support, pattern="^menu_support$"))

    logger.info("🎯 Yegara Bingo Bot starting...")

    async def _handle_error(update, context):
        from telegram.error import Conflict
        if isinstance(context.error, Conflict):
            return
        logger.error(f"Unhandled exception: {context.error}", exc_info=context.error)

    app.add_error_handler(_handle_error)
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

import logging
import re
import hashlib
import asyncio
from datetime import datetime

from telegram import (
    Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove,
    InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters,
)
from config import (
    BOT_TOKEN, db, ADMIN_CHAT_ID,
    DEFAULT_STAKE_10, DEFAULT_STAKE_20,
    SUPPORT_USERNAME, REFERRAL_BONUS, BONUS_TO_ETB_RATE, MIN_WITHDRAW,
    TELEBIRR_NUMBER,
)
from handlers.user_manager import UserManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

user_manager = UserManager(db)

# ─── Conversation states ───
REG_NAME, REG_PHONE = range(2)
AWAIT_PHOTO = 2
WITHDRAW_AMOUNT, WITHDRAW_PHONE = 3, 4
TRANSFER_ID, TRANSFER_AMOUNT, TRANSFER_CONFIRM = 5, 6, 7
BONUS_CONFIRM = 8
PLAY_STAKE = 9

# ─── Persistent keyboard ───
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🎮 Play"), KeyboardButton("📝 Register")],
        [KeyboardButton("💵 Check Balance"), KeyboardButton("💵 Deposit")],
        [KeyboardButton("🎰 Withdraw"), KeyboardButton("📖 Instruction")],
        [KeyboardButton("🎁 Transfer"), KeyboardButton("🔗 Invite")],
        [KeyboardButton("🔄 Convert Bonus"), KeyboardButton("🆘 Contact Support")],
    ],
    resize_keyboard=True,
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

    text = (
        f"👋 Welcome to Yegara Bingo, {user.first_name}!\n\n"
        f"Choose an option below to get started."
    )
    await update.message.reply_text(text, reply_markup=MAIN_KEYBOARD)

    await update.message.reply_text(
        "🎮 ጨዋታውን ለመጀመር ከታች ያለውን Play የሚለውን ይጫኑ\n"
        "(Click Play below to start the game)"
    )


# ═══════════════════════════════════════════════════════════════════
# 🎮 Play
# ═══════════════════════════════════════════════════════════════════
async def handle_play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await user_manager.get_user(uid)
    if not u:
        await update.message.reply_text("Please /start first.", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END

    if u.get('is_playing'):
        await update.message.reply_text(
            "⚠️ You already have an active game!\nOpen it from the WebApp.",
            reply_markup=MAIN_KEYBOARD,
        )
        return ConversationHandler.END

    pw = u.get('play_wallet', 0)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"10 ETB", callback_data="play_10"),
         InlineKeyboardButton(f"20 ETB", callback_data="play_20")],
        [InlineKeyboardButton("Cancel", callback_data="play_cancel")],
    ])
    await update.message.reply_text(
        f"💰 Your Play Wallet: *{pw} ETB*\n\nChoose your stake:",
        reply_markup=kb, parse_mode='Markdown',
    )
    return PLAY_STAKE


async def handle_play_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "play_cancel":
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END

    stake = DEFAULT_STAKE_10 if data == "play_10" else DEFAULT_STAKE_20
    uid = query.from_user.id
    u = await user_manager.get_user(uid)

    if not u or u.get('play_wallet', 0) < stake:
        await query.edit_message_text("❌ Not enough play wallet balance!")
        return ConversationHandler.END

    # Create game in Firestore
    game_data = {
        'user_id': uid,
        'stake': stake,
        'status': 'active',
        'called_numbers': [],
        'marked_numbers': [],
        'cartelas': [],
        'cartela_numbers': [],
        'cartela_count': 0,
        'cartela_cols': 5,
        'cartela_rows': 5,
        'allow_win': False,
        'win_user_id': None,
        'admin_notified': False,
        'winner': None,
        'prize': 0,
        'game_started_at': None,
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow(),
    }
    game_ref = db.collection('games').document()
    game_ref.set(game_data)
    game_id = game_ref.id

    webapp_url = f"https://t.me/yegarabingobot/game?startapp={game_id}"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Open Game", web_app=WebAppInfo(url=webapp_url))],
    ])
    await query.edit_message_text(
        f"✅ Game created!\n💰 Stake: *{stake} ETB*\n\nTap below to open the game board:",
        reply_markup=kb, parse_mode='Markdown',
    )
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════
# 📝 Register
# ═══════════════════════════════════════════════════════════════════
async def handle_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if await user_manager.is_registered(uid):
        u = await user_manager.get_user(uid)
        await update.message.reply_text(
            f"✅ You are already registered!\n\n"
            f"Name: {u.get('first_name', '')}\n"
            f"Phone: {u.get('phone', '')}",
            reply_markup=MAIN_KEYBOARD,
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "📝 Please enter your full name:", reply_markup=ReplyKeyboardRemove()
    )
    return REG_NAME


async def reg_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['reg_name'] = update.message.text.strip()
    await update.message.reply_text("📱 Please enter your TeleBirr phone number\n(format: +2519XXXXXXXX)")
    return REG_PHONE


async def reg_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    if not re.match(r'^\+251\d{9}$', phone):
        await update.message.reply_text("❌ Invalid phone format.\nPlease use: +2519XXXXXXXX")
        return REG_PHONE

    name = context.user_data.get('reg_name', update.effective_user.first_name)
    await user_manager.register_user(update.effective_user.id, name, phone)
    await update.message.reply_text(
        f"✅ Registration complete!\n\nName: {name}\nPhone: {phone}",
        reply_markup=MAIN_KEYBOARD,
    )
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════
# 💵 Check Balance
# ═══════════════════════════════════════════════════════════════════
async def handle_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    info = await user_manager.get_balance_info(uid)
    if not info:
        await update.message.reply_text("Please /start first.", reply_markup=MAIN_KEYBOARD)
        return

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💵 Deposit", callback_data="bal_deposit"),
         InlineKeyboardButton("🎰 Withdraw", callback_data="bal_withdraw")],
    ])
    await update.message.reply_text(
        f"💼 *Account Info*\n\n"
        f"Name: {info['first_name']}\n"
        f"Main wallet: {info['balance']} ETB\n"
        f"Play wallet: {info['play_wallet']} ETB\n"
        f"Bonus: {info['bonus']} coins",
        reply_markup=kb, parse_mode='Markdown',
    )
    # Auto support follow-up
    await update.message.reply_text(
        f"🆘 Need support?\n"
        f"👇 For any question or feedback:\n"
        f"👉 @{SUPPORT_USERNAME}"
    )


async def balance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "bal_deposit":
        await _show_deposit_flow(query, context)
    elif query.data == "bal_withdraw":
        await _show_withdraw_flow(query, context)


# ═══════════════════════════════════════════════════════════════════
# 💵 Deposit
# ═══════════════════════════════════════════════════════════════════
async def handle_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_deposit_flow_msg(update, context)


async def _show_deposit_flow_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await user_manager.get_user(uid)
    if not u:
        await update.message.reply_text("Please /start first.", reply_markup=MAIN_KEYBOARD)
        return AWAIT_PHOTO

    # Check pending deposits limit
    pending = db.collection('deposits').where('userId', '==', str(uid)).where('status', '==', 'pending').get()
    if len(list(pending)) >= 3:
        await update.message.reply_text(
            "⚠️ You have too many pending deposits.\nWait for them to be processed.",
            reply_markup=MAIN_KEYBOARD,
        )
        return ConversationHandler.END

    await user_manager.set_awaiting_screenshot(uid, True)
    await update.message.reply_text(
        f"💵 *Deposit via TeleBirr*\n\n"
        f"1. Send *{TELEBIRR_NUMBER}* via TeleBirr\n"
        f"2. Take a screenshot of the confirmation\n"
        f"3. Send the screenshot here\n\n"
        f"⏳ Waiting for your screenshot...",
        parse_mode='Markdown',
    )
    return AWAIT_PHOTO


async def _show_deposit_flow(query, context):
    uid = query.from_user.id
    pending = db.collection('deposits').where('userId', '==', str(uid)).where('status', '==', 'pending').get()
    if len(list(pending)) >= 3:
        await query.edit_message_text("⚠️ Too many pending deposits. Wait for processing.")
        return

    await user_manager.set_awaiting_screenshot(uid, True)
    await query.edit_message_text(
        f"💵 *Deposit via TeleBirr*\n\n"
        f"1. Send *{TELEBIRR_NUMBER}* via TeleBirr\n"
        f"2. Take a screenshot of the confirmation\n"
        f"3. Send the screenshot here",
        parse_mode='Markdown',
    )


async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await user_manager.get_user(uid)

    if not u or not u.get('awaiting_screenshot'):
        return

    # Check admin online
    admin_online = await _is_admin_online()
    if not admin_online:
        await update.message.reply_text(
            "⚠️ Admin is offline. Please try again later.",
            reply_markup=MAIN_KEYBOARD,
        )
        await user_manager.set_awaiting_screenshot(uid, False)
        return ConversationHandler.END

    photo = update.message.photo
    if not photo:
        await update.message.reply_text("Please send a photo (screenshot).")
        return AWAIT_PHOTO

    await update.message.reply_text("⏳ Processing your deposit...")

    # Download and hash image
    file = await photo[-1].get_file()
    image_bytes = await file.download_as_bytearray()
    image_hash = hashlib.sha256(bytes(image_bytes)).hexdigest()

    # Check duplicate image
    existing = db.collection('deposits').where('imageHash', '==', image_hash).limit(1).get()
    if not existing.empty:
        await update.message.reply_text("❌ This screenshot was already submitted.", reply_markup=MAIN_KEYBOARD)
        await user_manager.set_awaiting_screenshot(uid, False)
        return ConversationHandler.END

    # OCR extraction
    extracted = await asyncio.to_thread(_extract_text_from_image, bytes(image_bytes))

    txn_id = extracted.get('transaction_id') or f"IMG-{image_hash[:12]}"
    amount = extracted.get('amount') or 0
    sender_name = extracted.get('sender_name') or u.get('first_name', 'Unknown')

    # Check duplicate transaction ID
    if txn_id and not txn_id.startswith("IMG-"):
        dup = db.collection('deposits').where('transactionId', '==', txn_id).limit(1).get()
        if not dup.empty:
            await update.message.reply_text("❌ This transaction was already submitted.", reply_markup=MAIN_KEYBOARD)
            await user_manager.set_awaiting_screenshot(uid, False)
            return ConversationHandler.END

    deposit_data = {
        'userId': str(uid),
        'username': update.effective_user.username or '',
        'firstName': update.effective_user.first_name or '',
        'amount': amount,
        'transactionId': txn_id,
        'senderName': sender_name,
        'status': 'pending',
        'imageHash': image_hash,
        'imageFileId': photo[-1].file_id,
        'extractedText': extracted.get('raw_text', ''),
        'createdAt': datetime.utcnow(),
        'processedAt': None,
        'adminNote': '',
    }
    deposit_ref = db.collection('deposits').document()
    deposit_ref.set(deposit_data)
    deposit_id = deposit_ref.id

    await user_manager.set_awaiting_screenshot(uid, False)

    amount_text = f"{amount} ETB" if amount else "not detected"
    await update.message.reply_text(
        f"✅ Deposit request submitted!\n\n"
        f"Amount: {amount_text}\n"
        f"Sender: {sender_name}\n"
        f"Transaction: {txn_id}\n"
        f"ID: `{deposit_id}`",
        reply_markup=MAIN_KEYBOARD, parse_mode='Markdown',
    )

    await _notify_admin_deposit(deposit_data, deposit_id, context)
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════
# 🎰 Withdraw
# ═══════════════════════════════════════════════════════════════════
async def handle_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_withdraw_flow_msg(update, context)


async def _show_withdraw_flow_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await user_manager.get_user(uid)
    if not u:
        await update.message.reply_text("Please /start first.", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END

    bal = u.get('balance', 0)
    if bal < MIN_WITHDRAW:
        await update.message.reply_text(
            f"❌ Minimum withdrawal is {MIN_WITHDRAW} ETB.\nYour balance: {bal} ETB",
            reply_markup=MAIN_KEYBOARD,
        )
        return ConversationHandler.END

    await update.message.reply_text(
        f"🎰 *Withdraw*\n\nYour balance: *{bal} ETB*\nMinimum: {MIN_WITHDRAW} ETB\n\nEnter amount:",
        reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown',
    )
    return WITHDRAW_AMOUNT


async def _show_withdraw_flow(query, context):
    uid = query.from_user.id
    u = await user_manager.get_user(uid)
    if not u:
        await query.edit_message_text("Please /start first.")
        return
    bal = u.get('balance', 0)
    if bal < MIN_WITHDRAW:
        await query.edit_message_text(f"❌ Minimum {MIN_WITHDRAW} ETB. Balance: {bal} ETB")
        return
    await query.edit_message_text(f"🎰 Withdraw — Balance: {bal} ETB\n\nEnter amount:")
    context.user_data['awaiting_withdraw'] = True


async def withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Enter a valid number.")
        return WITHDRAW_AMOUNT

    uid = update.effective_user.id
    u = await user_manager.get_user(uid)
    bal = u.get('balance', 0) if u else 0

    if amount < MIN_WITHDRAW or amount > bal:
        await update.message.reply_text(f"❌ Enter amount between {MIN_WITHDRAW} and {bal} ETB.")
        return WITHDRAW_AMOUNT

    context.user_data['withdraw_amount'] = amount

    if u.get('phone'):
        return await _process_withdraw(update, context, uid, amount, u['phone'])

    await update.message.reply_text("📱 Enter your TeleBirr phone number (+251...):")
    return WITHDRAW_PHONE


async def withdraw_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    if not re.match(r'^\+251\d{9}$', phone):
        await update.message.reply_text("❌ Invalid format. Use: +2519XXXXXXXX")
        return WITHDRAW_PHONE

    uid = update.effective_user.id
    u = await user_manager.get_user(uid)
    amount = context.user_data.get('withdraw_amount', 0)
    return await _process_withdraw(update, context, uid, amount, phone)


async def _process_withdraw(update, context, uid, amount, phone):
    withdrawal_data = {
        'userId': str(uid),
        'username': update.effective_user.username or '',
        'firstName': update.effective_user.first_name or '',
        'amount': amount,
        'phone': phone,
        'status': 'pending',
        'createdAt': datetime.utcnow(),
        'processedAt': None,
        'adminNote': '',
    }
    ref = db.collection('withdrawals').document()
    ref.set(withdrawal_data)

    await user_manager.deduct_balance(uid, amount)

    await update.message.reply_text(
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
    uid = update.effective_user.id
    u = await user_manager.get_user(uid)
    if not u:
        await update.message.reply_text("Please /start first.", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END

    bal = u.get('balance', 0)
    if bal < 1:
        await update.message.reply_text(
            f"❌ No balance to transfer.\nYour balance: {bal} ETB",
            reply_markup=MAIN_KEYBOARD,
        )
        return ConversationHandler.END

    await update.message.reply_text(
        f"🎁 *Transfer*\nYour balance: *{bal} ETB*\n\nEnter recipient's Telegram User ID:",
        reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown',
    )
    return TRANSFER_ID


async def transfer_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        recipient_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Enter a valid numeric User ID.")
        return TRANSFER_ID

    if recipient_id == update.effective_user.id:
        await update.message.reply_text("❌ You cannot transfer to yourself.")
        return TRANSFER_ID

    recipient = await user_manager.get_user(recipient_id)
    if not recipient:
        await update.message.reply_text("❌ User not found. Check the ID and try again.")
        return TRANSFER_ID

    context.user_data['transfer_to'] = recipient_id
    context.user_data['transfer_to_name'] = recipient.get('first_name', 'Unknown')

    await update.message.reply_text(
        f"👤 Recipient: {recipient.get('first_name', 'Unknown')}\n"
        f"Enter amount to send (ETB):"
    )
    return TRANSFER_AMOUNT


async def transfer_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Enter a valid number.")
        return TRANSFER_AMOUNT

    uid = update.effective_user.id
    u = await user_manager.get_user(uid)
    bal = u.get('balance', 0) if u else 0

    if amount < 1 or amount > bal:
        await update.message.reply_text(f"❌ Enter amount between 1 and {bal} ETB.")
        return TRANSFER_AMOUNT

    context.user_data['transfer_amount'] = amount
    to_name = context.user_data.get('transfer_to_name', 'Unknown')

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirm", callback_data="tf_yes"),
         InlineKeyboardButton("❌ Cancel", callback_data="tf_no")],
    ])
    await update.message.reply_text(
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
    uid = update.effective_user.id
    u = await user_manager.get_user(uid)
    if not u:
        await update.message.reply_text("Please /start first.", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END

    coins = u.get('bonus', 0)
    if coins <= 0:
        await update.message.reply_text("❌ No bonus coins to convert.", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END

    etb = coins / BONUS_TO_ETB_RATE
    context.user_data['convert_etb'] = etb
    context.user_data['convert_coins'] = coins

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✅ Convert {coins} coins → {etb} ETB", callback_data="bonus_yes"),
         InlineKeyboardButton("❌ Cancel", callback_data="bonus_no")],
    ])
    await update.message.reply_text(
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
    uid = update.effective_user.id
    link = f"https://t.me/yegarabingobot?start=ref_{uid}"
    await update.message.reply_text(
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
    await update.message.reply_text(
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
    await update.message.reply_text(
        f"🆘 *Support*\n\n"
        f"👤 Contact: @{SUPPORT_USERNAME}\n\n"
        f"For any question, feedback, or issue — reach out to our support team.",
        reply_markup=MAIN_KEYBOARD, parse_mode='Markdown',
    )


# ═══════════════════════════════════════════════════════════════════
# Admin notifications
# ═══════════════════════════════════════════════════════════════════
async def _notify_admin_deposit(deposit_data, deposit_id, context):
    try:
        text = (
            f"💵 *New Deposit Request*\n\n"
            f"👤 {deposit_data.get('firstName', 'Unknown')} (@{deposit_data.get('username', '')})\n"
            f"💰 Amount: {deposit_data.get('amount', 0)} ETB\n"
            f"🔖 TXN: {deposit_data.get('transactionId', 'N/A')}\n"
            f"👤 Sender: {deposit_data.get('senderName', 'N/A')}\n"
            f"🆔 {deposit_id}\n"
            f"🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Approve", callback_data=f"approve_{deposit_id}"),
             InlineKeyboardButton("❌ Reject", callback_data=f"reject_{deposit_id}")],
        ])
        file_id = deposit_data.get('imageFileId')
        if file_id:
            await context.bot.send_photo(
                chat_id=_admin_id(), photo=file_id,
                caption=text, reply_markup=kb, parse_mode='Markdown',
            )
        else:
            await context.bot.send_message(
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
            f"💰 Amount: {withdrawal_data.get('amount', 0)} ETB\n"
            f"📱 Phone: {withdrawal_data.get('phone', 'N/A')}\n"
            f"🆔 {withdrawal_id}\n"
            f"🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Approve", callback_data=f"approve_withdraw_{withdrawal_id}"),
             InlineKeyboardButton("❌ Reject", callback_data=f"reject_withdraw_{withdrawal_id}")],
        ])
        await context.bot.send_message(
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
    try:
        from PIL import Image
        import pytesseract
        import io
        img = Image.open(io.BytesIO(image_bytes))
        raw_text = pytesseract.image_to_string(img)
    except ImportError:
        return {"raw_text": "OCR not available", "transaction_id": None, "amount": 0, "sender_name": None}

    txn_id = None
    for pattern in [
        r'(?:Transaction\s*ID|TXN|Ref|Reference)[:\s]*([A-Za-z0-9]{8,})',
        r'([A-Za-z0-9]{12,})',
    ]:
        m = re.search(pattern, raw_text, re.IGNORECASE)
        if m:
            txn_id = m.group(1)
            break

    amount = 0
    for pattern in [
        r'(?:Amount|Total|ETB)[:\s]*([\d,]+\.?\d*)',
        r'([\d,]+\.?\d*)\s*ETB',
    ]:
        m = re.search(pattern, raw_text, re.IGNORECASE)
        if m:
            try:
                amount = float(m.group(1).replace(',', ''))
                break
            except ValueError:
                continue

    sender = None
    m = re.search(r'(?:From|Sender|Payer)[:\s]*([A-Za-z\s]+)', raw_text, re.IGNORECASE)
    if m:
        sender = m.group(1).strip()

    return {
        "raw_text": raw_text,
        "transaction_id": txn_id,
        "amount": amount,
        "sender_name": sender,
    }


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # ─── /start ───
    app.add_handler(CommandHandler("start", start))

    # ─── Menu text handlers (persistent keyboard) ───
    app.add_handler(MessageHandler(filters.Regex("^🎮 Play$"), handle_play))
    app.add_handler(MessageHandler(filters.Regex("^📝 Register$"), handle_register))
    app.add_handler(MessageHandler(filters.Regex("^💵 Check Balance$"), handle_balance))
    app.add_handler(MessageHandler(filters.Regex("^💵 Deposit$"), handle_deposit))
    app.add_handler(MessageHandler(filters.Regex("^🎰 Withdraw$"), handle_withdraw))
    app.add_handler(MessageHandler(filters.Regex("^🎁 Transfer$"), handle_transfer))
    app.add_handler(MessageHandler(filters.Regex("^🔄 Convert Bonus$"), handle_convert_bonus))
    app.add_handler(MessageHandler(filters.Regex("^🔗 Invite$"), handle_invite))
    app.add_handler(MessageHandler(filters.Regex("^📖 Instruction$"), handle_instruction))
    app.add_handler(MessageHandler(filters.Regex("^🆘 Contact Support$"), handle_support))

    # ─── ConversationHandler: Play ───
    play_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🎮 Play$"), handle_play)],
        states={
            PLAY_STAKE: [CallbackQueryHandler(handle_play_callback, pattern="^play_")],
        },
        fallbacks=[CommandHandler("start", start)],
    )
    # Replace the simple handler with conversation handler
    app.add_handler(play_conv, group=1)

    # ─── ConversationHandler: Register ───
    reg_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📝 Register$"), handle_register)],
        states={
            REG_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_name)],
            REG_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_phone)],
        },
        fallbacks=[CommandHandler("start", start), MessageHandler(filters.Regex("^Cancel$"), cancel)],
    )
    app.add_handler(reg_conv, group=2)

    # ─── ConversationHandler: Deposit ───
    deposit_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💵 Deposit$"), handle_deposit)],
        states={
            AWAIT_PHOTO: [MessageHandler(filters.PHOTO, handle_screenshot)],
        },
        fallbacks=[CommandHandler("start", start), MessageHandler(filters.Regex("^Cancel$"), cancel)],
    )
    app.add_handler(deposit_conv, group=3)

    # ─── ConversationHandler: Withdraw ───
    withdraw_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🎰 Withdraw$"), handle_withdraw)],
        states={
            WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount)],
            WITHDRAW_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_phone)],
        },
        fallbacks=[CommandHandler("start", start), MessageHandler(filters.Regex("^Cancel$"), cancel)],
    )
    app.add_handler(withdraw_conv, group=4)

    # ─── ConversationHandler: Transfer ───
    transfer_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🎁 Transfer$"), handle_transfer)],
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
        entry_points=[MessageHandler(filters.Regex("^🔄 Convert Bonus$"), handle_convert_bonus)],
        states={
            BONUS_CONFIRM: [CallbackQueryHandler(bonus_confirm, pattern="^bonus_")],
        },
        fallbacks=[CommandHandler("start", start)],
    )
    app.add_handler(bonus_conv, group=6)

    # ─── Balance inline callbacks ───
    app.add_handler(CallbackQueryHandler(balance_callback, pattern="^bal_"))

    # ─── Screenshot handler (non-conversation fallback) ───
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_screenshot))

    logger.info("🎯 Yegara Bingo Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

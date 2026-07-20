import re

def main():
    file_path = "e:/paradox/bingo/bot.py"
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Replace MAIN_KEYBOARD definition and add MAIN_INLINE_KEYBOARD
    new_kb_str = """MAIN_KEYBOARD = ReplyKeyboardRemove()
MAIN_INLINE_KEYBOARD = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("Play 🎮", callback_data="menu_play"), InlineKeyboardButton("Register 📝", callback_data="menu_register")],
        [InlineKeyboardButton("Check Balance 💵", callback_data="menu_balance"), InlineKeyboardButton("Deposit 💵", callback_data="menu_deposit")],
        [InlineKeyboardButton("Contact Support ☎️", callback_data="menu_support"), InlineKeyboardButton("Instruction 📖", callback_data="menu_instruction")],
        [InlineKeyboardButton("Transfer 🎁", callback_data="menu_transfer"), InlineKeyboardButton("Withdraw 🤑", callback_data="menu_withdraw")],
        [InlineKeyboardButton("Invite 🔗", callback_data="menu_invite"), InlineKeyboardButton("Convert Bonus 💸", callback_data="menu_bonus")],
    ]
)"""
    content = re.sub(
        r'MAIN_KEYBOARD\s*=\s*ReplyKeyboardMarkup\([^)]+\)',
        new_kb_str,
        content,
        flags=re.MULTILINE
    )

    # 2. Update `start` handler
    start_replacement = """    text = (
        "👋 Welcome to Kelem Bingo! Choose an Option below."
    )
    banner_path = os.path.join(ASSETS_DIR, 'welcome_banner.png')
    if os.path.exists(banner_path):
        with open(banner_path, 'rb') as photo:
            await update.effective_message.reply_photo(
                photo=photo,
                caption=text,
                reply_markup=MAIN_INLINE_KEYBOARD,
                read_timeout=30,
                write_timeout=30,
                connect_timeout=30
            )
    else:
        await update.effective_message.reply_text(text, reply_markup=MAIN_INLINE_KEYBOARD)

    await update.effective_message.reply_text(
        "🎮 ጨዋታውን ለመጀመር ከታች ያለውን Play የሚለውን ይጫኑ::\\n"
        "(Click Play below to start the game)"
    )"""
    
    # We regex replace the specific text in start
    content = re.sub(
        r'text\s*=\s*\(\s*f"👋 Welcome to Kelem Bingo[^\)]*\)\n.*?\(Click Play below to start the game\)"\n\s*\)',
        start_replacement,
        content,
        flags=re.DOTALL
    )

    # 3. Add timeouts to Application builder in `main`
    content = content.replace(
        "app = Application.builder().token(BOT_TOKEN).build()",
        "app = Application.builder().token(BOT_TOKEN).read_timeout(30).write_timeout(30).connect_timeout(30).pool_timeout(30).build()"
    )

    # 4. Modify all handlers to support CallbackQuery
    # Since these are entry points that expect Update, we can inject `msg = update.effective_message`
    # and `if update.callback_query: await update.callback_query.answer()`
    handlers_to_modify = [
        "handle_play", "handle_register", "handle_balance",
        "handle_deposit", "handle_withdraw", "handle_transfer",
        "handle_convert_bonus", "handle_invite", "handle_instruction",
        "handle_support"
    ]

    for handler in handlers_to_modify:
        sig = f"async def {handler}(update: Update, context: ContextTypes.DEFAULT_TYPE):\n"
        injection = f"""    if update.callback_query:
        await update.callback_query.answer()
"""
        content = content.replace(sig, sig + injection)

    # Replace all `update.message.reply_text` with `update.effective_message.reply_text` inside those handlers
    # Actually, let's just globally replace it since it's safe. Oh wait, `update.message` can be None for callback query.
    # So `update.effective_message.reply_text` is much safer everywhere!
    content = content.replace("update.message.reply_text", "update.effective_message.reply_text")
    content = content.replace("update.message.reply_photo", "update.effective_message.reply_photo")

    # 5. Add CallbackQueryHandlers to main() routing
    # Let's define the new handlers mappings
    new_handlers = """
    # ─── New Inline Menu Callbacks ───
    app.add_handler(CallbackQueryHandler(handle_balance, pattern="^menu_balance$"))
    app.add_handler(CallbackQueryHandler(handle_invite, pattern="^menu_invite$"))
    app.add_handler(CallbackQueryHandler(handle_instruction, pattern="^menu_instruction$"))
    app.add_handler(CallbackQueryHandler(handle_support, pattern="^menu_support$"))
"""
    # Inject before `logger.info("🎯 Kelem Bingo Bot starting...")`
    content = content.replace('logger.info("🎯 Kelem Bingo Bot starting...")', new_handlers + '\n    logger.info("🎯 Kelem Bingo Bot starting...")')

    # Update ConversationHandler entry points
    # PLAY
    content = re.sub(
        r'entry_points=\[MessageHandler\(filters\.Regex\("\^🎮 Play\$"\),\s*handle_play\)\]',
        'entry_points=[MessageHandler(filters.Regex("^🎮 Play$"), handle_play), CallbackQueryHandler(handle_play, pattern="^menu_play$")]',
        content
    )
    # REGISTER
    content = re.sub(
        r'entry_points=\[MessageHandler\(filters\.Regex\("\^📝 Register\$"\),\s*handle_register\)\]',
        'entry_points=[MessageHandler(filters.Regex("^📝 Register$"), handle_register), CallbackQueryHandler(handle_register, pattern="^menu_register$")]',
        content
    )
    # DEPOSIT
    content = re.sub(
        r'entry_points=\[MessageHandler\(filters\.Regex\("\^💵 Deposit\$"\),\s*handle_deposit\)\]',
        'entry_points=[MessageHandler(filters.Regex("^💵 Deposit$"), handle_deposit), CallbackQueryHandler(handle_deposit, pattern="^menu_deposit$")]',
        content
    )
    # WITHDRAW
    content = re.sub(
        r'entry_points=\[MessageHandler\(filters\.Regex\("\^🎰 Withdraw\$"\),\s*handle_withdraw\)\]',
        'entry_points=[MessageHandler(filters.Regex("^🎰 Withdraw$"), handle_withdraw), CallbackQueryHandler(handle_withdraw, pattern="^menu_withdraw$")]',
        content
    )
    # TRANSFER
    content = re.sub(
        r'entry_points=\[MessageHandler\(filters\.Regex\("\^🎁 Transfer\$"\),\s*handle_transfer\)\]',
        'entry_points=[MessageHandler(filters.Regex("^🎁 Transfer$"), handle_transfer), CallbackQueryHandler(handle_transfer, pattern="^menu_transfer$")]',
        content
    )
    # CONVERT BONUS
    content = re.sub(
        r'entry_points=\[MessageHandler\(filters\.Regex\("\^🔄 Convert Bonus\$"\),\s*handle_convert_bonus\)\]',
        'entry_points=[MessageHandler(filters.Regex("^🔄 Convert Bonus$"), handle_convert_bonus), CallbackQueryHandler(handle_convert_bonus, pattern="^menu_bonus$")]',
        content
    )

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    print("Modifications applied successfully.")

if __name__ == "__main__":
    main()

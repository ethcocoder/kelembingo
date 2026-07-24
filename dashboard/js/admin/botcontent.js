// ==================== BOT CONTENT CMS ====================
var _botContentCache = {};
var _currentBotCategory = 'welcome';

var BOT_CONTENT_DEFAULTS = {
    welcome: {
        welcome_registered: { label: 'Welcome (Registered User)', default: '👋 Welcome back, {name}!\n\n💰 Balance: *{balance} ETB*\n\nTap Play to start the game!', vars: 'name, balance' },
        welcome_new: { label: 'Welcome (New User)', default: '👋 Welcome to Kelem Bingo! Choose an Option below.', vars: '' },
        welcome_new_amharic: { label: 'Welcome Amharic', default: '🎮 ጨዋታውን ለመጀመር ከታች ያለውን Play የሚለውን ይጫኑ::\n(Click Play below to start the game)', vars: '' },
    },
    play: {
        play_wallet_info: { label: 'Play Button Info', default: '💰 Your Play Wallet: *{play_wallet} ETB*\n\n🎯 Stake: *10 ETB* per cartela (max 2)\n🏆 Derash: *(Cartelas × Stake × 0.75) / Winners*\n\nTap below to open the game:', vars: 'play_wallet' },
        play_need_start: { label: 'Need /start', default: 'Please /start first.', vars: '' },
        instruction: { label: 'How to Play', default: '📖 *How to Play Kelem Bingo*\n\n1️⃣ Click *Play* and choose your stake (10 or 20 ETB)\n2️⃣ Select up to *3 cartelas* (bingo cards)\n3️⃣ The game board opens — numbers are called every 4 seconds\n4️⃣ Tap numbers on your card to mark them (or use Auto Mark)\n5️⃣ Complete a full line (row, column, or diagonal) to win!\n\n🎯 *Winning:* Complete any row, column, or diagonal\n🏆 *Derash:* 1.5x your stake\n⭐ *Free Space:* Center cell is always free\n\n💰 *Wallet:*\n• Deposit via TeleBirr — funds go directly to your play wallet\n• Bonus — earned from referrals\n\n📤 *Transfer:* Send funds to any user by ID\n🔄 *Convert Bonus:* Turn bonus coins into your wallet', vars: '' },
    },
    register: {
        register_already: { label: 'Already Registered', default: '✅ You are already registered!\n\nName: {name}\nPhone: {phone}', vars: 'name, phone' },
        register_ask_contact: { label: 'Ask Contact', default: '📱 Tap the button below to share your contact:', vars: '' },
        register_complete: { label: 'Registration Complete', default: '✅ Registration complete!\n\nName: {name}\nPhone: {phone}', vars: 'name, phone' },
    },
    deposit: {
        deposit_too_many: { label: 'Too Many Pending', default: '⚠️ You have too many pending deposits.\nWait for them to be processed.', vars: '' },
        deposit_ask_name: { label: 'Ask TeleBirr Name', default: '💰 Please enter your TeleBirr name\n(The name registered on your TeleBirr account):', vars: '' },
        deposit_ask_amount: { label: 'Ask Amount', default: '💰 Enter deposit amount (ETB):', vars: '' },
        deposit_send_to: { label: 'Send To (shows phone)', default: '📱 Send {amount} ETB to this TeleBirr number:\n\n📞 *{phone}*\n\nAfter sending, enter the Transaction Number from your receipt:', vars: 'amount, phone' },
        deposit_phone: { label: 'Admin Phone Number (For Deposits)', default: '0911000000', vars: '' },
        deposit_min_amount: { label: 'Min Amount Error', default: '⚠️ Minimum deposit is 10 ETB. Enter again:', vars: '' },
        deposit_invalid_number: { label: 'Invalid Number', default: '❌ Enter a valid number:', vars: '' },
        deposit_admin_offline: { label: 'Deposit - Admin Offline', default: '⚠️ Admin is offline. Please try again later.', vars: '' },
        deposit_submitted: { label: 'Deposit Submitted', default: '✅ Deposit request submitted!\n\n💵 Amount: {amount} ETB\n👤 Name: {telebirr_name}\n🔢 Transaction: {transaction_id}\n🆔 `{deposit_id}`\n\nAdmin will review and approve shortly.', vars: 'amount, telebirr_name, transaction_id, deposit_id' },
        deposit_approved: { label: 'Deposit Approved', default: '✅ Deposit approved!\n💰 {amount} ETB has been added to your wallet.', vars: 'amount' },
        deposit_rejected: { label: 'Deposit Rejected', default: '❌ Deposit rejected.\nPlease contact support if you need help.', vars: '' },
        deposit_duplicate_txn: { label: 'Duplicate Transaction', default: '❌ This transaction number was already submitted.', vars: '' },
    },
    withdraw: {
        withdraw_min_not_met: { label: 'Minimum Not Met', default: '❌ Minimum withdrawal is {min_withdraw} ETB.\nYour balance: {balance} ETB', vars: 'min_withdraw, balance' },
        withdraw_deposit_required: { label: 'Initial Deposit Required', default: '❌ You must deposit at least {min_deposit} ETB before you can make your first withdrawal.\n\nYour total deposits: {current_deposit} ETB', vars: 'min_deposit, current_deposit' },
        withdraw_ask_amount: { label: 'Ask Amount', default: '🎰 *Withdraw*\n\nYour balance: *{balance} ETB*\nMinimum: {min_withdraw} ETB\n\nEnter amount:', vars: 'balance, min_withdraw' },
        withdraw_invalid_range: { label: 'Invalid Range', default: '❌ Enter amount between {min_withdraw} and {balance} ETB.', vars: 'min_withdraw, balance' },
        withdraw_invalid_number: { label: 'Invalid Number', default: '❌ Enter a valid number.', vars: '' },
        withdraw_ask_name: { label: 'Ask TeleBirr Name', default: '💰 Please enter your TeleBirr name\n(The name registered on your TeleBirr account):', vars: '' },
        withdraw_submitted: { label: 'Withdrawal Submitted', default: '✅ Withdrawal request submitted!\n\nAmount: {amount} ETB\nPhone: {phone}\nID: `{withdrawal_id}`\n\nAdmin will process it shortly.', vars: 'amount, phone, withdrawal_id' },
        withdraw_approved: { label: 'Withdrawal Approved', default: '✅ Withdrawal approved!\n💰 {amount} ETB will be sent to your TeleBirr.', vars: 'amount' },
        withdraw_rejected: { label: 'Withdrawal Rejected', default: '❌ Withdrawal rejected.\n💰 {amount} ETB has been refunded to your balance.', vars: 'amount' },
        withdraw_no_phone: { label: 'No Phone', default: '❌ Please register with your phone number first.\nUse /register to complete registration.', vars: '' },
        withdraw_above_max: { label: 'Above Maximum', default: '❌ Maximum withdrawal is {max} ETB per request.', vars: 'max' },
        withdraw_account_new: { label: 'Account Too New', default: '❌ Your account is too new.\nPlease wait 24 hours after registration before withdrawing.', vars: '' },
        withdraw_pending_exists: { label: 'Pending Exists', default: '❌ You already have a pending withdrawal.\nWait for it to be processed before requesting another.', vars: '' },
        withdraw_daily_limit: { label: 'Daily Limit', default: '❌ Daily withdrawal limit reached.\nYou can make up to {limit} withdrawals per day. Try again tomorrow.', vars: 'limit' },
        withdraw_cooldown: { label: 'Cooldown', default: '⏳ Please wait {minutes} minutes before making another withdrawal.\n(Cooldown: {hours} hours between requests)', vars: 'minutes, hours' },
        withdraw_admin_offline: { label: 'Withdraw - Admin Offline', default: '⚠️ Admin is offline. Withdrawals are temporarily unavailable.', vars: '' },
    },
    transfer: {
        transfer_no_balance: { label: 'No Balance', default: '❌ No balance to transfer.\nYour balance: {balance} ETB', vars: 'balance' },
        transfer_ask_id: { label: 'Ask Recipient ID', default: '🎁 Transfer\nYour balance: {balance} ETB\n\nEnter recipient\'s Telegram User ID:', vars: 'balance' },
        transfer_invalid_id: { label: 'Invalid ID', default: '❌ Enter a valid numeric User ID.', vars: '' },
        transfer_self: { label: 'Self Transfer', default: '❌ You cannot transfer to yourself.', vars: '' },
        transfer_not_found: { label: 'User Not Found', default: '❌ User not found. Check the ID and try again.', vars: '' },
        transfer_ask_amount: { label: 'Ask Amount', default: '👤 Recipient: {name}\n💰 Enter amount to send (ETB):', vars: 'name' },
        transfer_invalid_amount: { label: 'Invalid Amount', default: '❌ Enter a valid number.', vars: '' },
        transfer_amount_range: { label: 'Amount Out of Range', default: '❌ Enter amount between 1 and {balance} ETB.', vars: 'balance' },
        transfer_confirm: { label: 'Confirm Transfer', default: '📤 Send {amount} ETB to {name}?', vars: 'amount, name' },
        transfer_cancelled: { label: 'Transfer Cancelled', default: 'Transfer cancelled.', vars: '' },
        transfer_sent: { label: 'Transfer Sent', default: '✅ Sent {amount} ETB to {name} successfully!', vars: 'amount, name' },
        transfer_failed: { label: 'Transfer Failed', default: '❌ Transfer failed. Check your balance and try again.', vars: '' },
    },
    bonus: {
        bonus_no_coins: { label: 'No Bonus Coins', default: '❌ No bonus coins to convert.', vars: '' },
        bonus_convert_info: { label: 'Convert Info', default: '🔄 Convert Bonus\n\nYou have: {coins} coins\nRate: {rate} coins = 1 ETB\nYou will receive: {etb} ETB in Play Wallet', vars: 'coins, rate, etb' },
        bonus_cancelled: { label: 'Cancelled', default: 'Cancelled.', vars: '' },
        bonus_converted: { label: 'Converted', default: '✅ Converted! +{etb} ETB added to your Play Wallet.', vars: 'etb' },
        bonus_convert_failed: { label: 'Convert Failed', default: '❌ Conversion failed. No bonus available.', vars: '' },
    },
    invite: {
        invite_link: { label: 'Invite Link', default: '🔗 *Invite Friends*\n\nShare your personal link and invite your friends to play Kelem Bingo:\n\n`{link}`\n\n👥 Friends invited: *{count}*\n\nTap *Share invite link* below, or copy the link and send it to your friends!', vars: 'link, count' },
    },
    support: {
        support_info: { label: 'Support Info', default: '🆘 Need help?\n\n👇 For any questions or feedback 👇\n\n👤 @{support_username}', vars: 'support_username' },
    },
    admin: {
        admin_deposit_notification: { label: 'Deposit Notification (Admin)', default: '💵 *New Deposit Request*\n\n👤 *User:* {first_name} (@{username})\n📱 *TeleBirr Name:* {telebirr_name}\n💵 *Amount:* {amount} ETB\n🔢 *Transaction:* {transaction_id}\n\n🆔 `{deposit_id}`\n🕐 {timestamp}', vars: 'first_name, username, telebirr_name, amount, transaction_id, deposit_id, timestamp' },
        admin_withdrawal_notification: { label: 'Withdrawal Notification (Admin)', default: '🎰 *New Withdrawal Request*\n\n👤 {first_name} (@{username})\n💰 TeleBirr Name: {telebirr_name}\n💵 Amount: {amount} ETB\n📱 Phone: {phone}\n🆔 {withdrawal_id}\n🕐 {timestamp}', vars: 'first_name, username, telebirr_name, amount, phone, withdrawal_id, timestamp' },
    },
    stats: {
        stats_title: { label: 'Stats Message', default: '📊 *Your Stats*\n\n🎮 Games Played: {total}\n🏆 Wins: {wins}\n❌ Losses: {losses}\n📈 Win Rate: {win_rate}\n\n💰 Balance: {balance} ETB\n🪙 Bonus Coins: {bonus}', vars: 'total, wins, losses, win_rate, balance, bonus' },
        leaderboard_no_games: { label: 'No Games (Leaderboard)', default: '🏆 No games played yet. Be the first!', vars: '' },
        leaderboard_title: { label: 'Leaderboard Title', default: '🏆 *Top Players*\n', vars: '' },
        history_no_games: { label: 'No History', default: 'No game history yet. Play a game first!', vars: '' },
        history_title: { label: 'History Title', default: '📋 *Your Recent Games*\n', vars: '' },
        cancel: { label: 'Cancel Message', default: 'Cancelled.', vars: '' },
    },
    config: {
        cfg_min_withdraw: { label: '💰 Minimum Withdrawal (ETB)', default: '50', vars: '', type: 'number', description: 'The minimum amount a user can withdraw.' },
        cfg_max_withdraw: { label: '💰 Maximum Withdrawal (ETB)', default: '50000', vars: '', type: 'number', description: 'The maximum amount a user can withdraw per request.' },
        cfg_min_initial_deposit: { label: '💵 Min Deposit Before First Withdrawal (ETB)', default: '50', vars: '', type: 'number', description: 'User must deposit at least this amount before they can withdraw for the first time.' },
        cfg_max_withdraw_per_day: { label: '📊 Max Withdrawals Per Day', default: '3', vars: '', type: 'number', description: 'How many withdrawals a user can make per day.' },
        cfg_withdraw_cooldown_hours: { label: '⏳ Withdrawal Cooldown (Hours)', default: '4', vars: '', type: 'number', description: 'Hours a user must wait between withdrawals.' },
        cfg_referral_bonus: { label: '🎁 Referral Bonus (ETB)', default: '10', vars: '', type: 'number', description: 'ETB earned when a referred user registers.' },
        cfg_bonus_to_etb_rate: { label: '🔄 Bonus Coin to ETB Rate', default: '10', vars: '', type: 'number', description: 'How many bonus coins equal 1 ETB (e.g. 10 coins = 1 ETB).' },
        cfg_support_username: { label: '🆘 Support Username', default: 'kelemsupport', vars: '', type: 'text', description: 'Telegram username for customer support (without @).' },
    }
};

var VAR_SAMPLES = {
    name: 'Abebe', balance: '200', phone: '+251911234567',
    amount: '100', telebirr_name: 'Abebe Kebede', transaction_id: 'DFL35JF5',
    deposit_id: 'abc123', withdrawal_id: 'xyz789', timestamp: '20/07/2026 14:30',
    first_name: 'Abebe', username: 'abebe123', min_withdraw: '50', total: '25',
    wins: '8', losses: '17', win_rate: '32%', bonus: '150', stake: '10',
    players: '12', coins: '500', rate: '10', etb: '50', link: 'https://t.me/YourBotUsername?start=ref_123',
    referral_bonus: '10', support_username: 'kelemsupport', limit: '3',
    minutes: '30', hours: '4', max: '50000', min_deposit: '50', current_deposit: '10', count: '5'
};

var VAR_LABELS = {
    name: 'User Name', balance: 'Balance', play_wallet: 'Play Wallet', phone: 'Phone Number',
    amount: 'Amount', telebirr_name: 'TeleBirr Name', transaction_id: 'Transaction #',
    deposit_id: 'Deposit ID', withdrawal_id: 'Withdrawal ID', timestamp: 'Date & Time',
    first_name: 'First Name', username: 'Username', min_withdraw: 'Min Withdrawal',
    total: 'Total Games', wins: 'Wins', losses: 'Losses', win_rate: 'Win Rate',
    bonus: 'Bonus Coins', stake: 'Stake', players: 'Player Count', coins: 'Bonus Coins',
    rate: 'Conversion Rate', etb: 'ETB Amount', link: 'Referral Link',
    referral_bonus: 'Referral Bonus', support_username: 'Support Username',
    limit: 'Daily Limit', minutes: 'Minutes', hours: 'Hours', max: 'Max Amount', min_deposit: 'Min Deposit', current_deposit: 'Current Deposit', count: 'Friends Invited'
};

// ── Inject CSS for variable chips ──
(function() {
    var style = document.createElement('style');
    style.textContent = [
        '.bce-editor { min-height: 60px; white-space: pre-wrap; word-wrap: break-word; outline: none; line-height: 1.7; }',
        '.bce-editor:empty::before { content: attr(data-placeholder); color: #4B5563; }',
        '.bce-editor:focus { border-color: rgba(16,185,129,0.5) !important; box-shadow: 0 0 0 3px rgba(16,185,129,0.15); }',
        '.var-chip { display: inline; padding: 1px 7px; margin: 0 1px; border-radius: 4px; font-size: 0.8em; font-weight: 600; cursor: default; user-select: all; -webkit-user-select: all; }',
        '.var-chip { background: rgba(168,85,247,0.15); color: #C084FC; border: 1px solid rgba(168,85,247,0.3); }',
        '.var-chip::before { content: attr(data-label) ": "; font-size: 0.85em; opacity: 0.6; font-weight: 400; }',
    ].join('\n');
    document.head.appendChild(style);
})();

/**
 * Convert backend text ({var} placeholders) to rich HTML with variable chips.
 * Each {var} becomes a styled <span> chip showing the sample value + label.
 */
function toDisplayHtml(text) {
    if (!text) return '';
    // First escape HTML in the plain text parts
    var html = escHtml(text);
    // Replace newlines with <br>
    html = html.replace(/\n/g, '<br>');
    // Replace {var} with chips
    html = html.replace(/\{(\w+)\}/g, function(match, key) {
        var sample = VAR_SAMPLES[key] || key;
        var label = VAR_LABELS[key] || key;
        return '<span class="var-chip" contenteditable="false" data-var="' + key + '" data-label="' + escAttr(label) + '">' + escHtml(sample) + '</span>';
    });
    return html;
}

/**
 * Convert rich HTML (with chips) back to backend text with {var} placeholders.
 */
function toBackendText(editorEl) {
    if (!editorEl) return '';
    // Clone the element to avoid modifying the live DOM
    var clone = editorEl.cloneNode(true);
    // Replace all var-chip spans with {var}
    clone.querySelectorAll('.var-chip').forEach(function(chip) {
        var varName = chip.getAttribute('data-var');
        chip.replaceWith('{' + varName + '}');
    });
    // Convert <br> and <div> to newlines
    var html = clone.innerHTML;
    html = html.replace(/<br\s*\/?>/gi, '\n');
    html = html.replace(/<div>/gi, '\n');
    html = html.replace(/<\/div>/gi, '');
    html = html.replace(/<p>/gi, '\n');
    html = html.replace(/<\/p>/gi, '');
    html = html.replace(/&amp;/g, '&');
    html = html.replace(/&lt;/g, '<');
    html = html.replace(/&gt;/g, '>');
    html = html.replace(/&quot;/g, '"');
    html = html.replace(/&#39;/g, "'");
    html = html.replace(/&nbsp;/g, ' ');
    // Clean up multiple consecutive newlines from div wrapping
    html = html.replace(/^\n/, '');
    return html;
}

function escAttr(str) {
    return str.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function loadBotCategory(cat) {
    _currentBotCategory = cat;
    document.querySelectorAll('.botcat-tab').forEach(function(t) {
        t.classList.remove('active');
        t.classList.add('text-gray-400');
    });
    var activeTab = document.querySelector('.botcat-tab[data-cat="' + cat + '"]');
    if (activeTab) {
        activeTab.classList.add('active');
        activeTab.classList.remove('text-gray-400');
    }

    var messages = BOT_CONTENT_DEFAULTS[cat] || {};
    var editor = document.getElementById('botContentEditor');
    if (!editor) return;
    editor.innerHTML = '';

    // Config tab uses simple input fields
    if (cat === 'config') {
        _renderConfigTab(messages, editor);
        return;
    }

    Object.keys(messages).forEach(function(key) {
        var msg = messages[key];
        var currentVal = _botContentCache[key] || msg.default;
        var hasVars = msg.vars && msg.vars.trim().length > 0;

        var card = document.createElement('div');
        card.className = 'mb-6 rounded-xl overflow-hidden';
        card.style.cssText = 'background: linear-gradient(135deg, rgba(255,255,255,0.03), rgba(255,255,255,0.01)); border: 1px solid rgba(255,255,255,0.06);';

        var helperHtml = '';
        if (hasVars) {
            var varList = msg.vars.split(',').map(function(v) { return v.trim(); });
            var chipExamples = varList.map(function(v) {
                var label = VAR_LABELS[v] || v;
                var sample = VAR_SAMPLES[v] || v;
                return '<span style="display:inline-block;padding:0 5px;border-radius:3px;font-size:10px;font-weight:600;background:rgba(168,85,247,0.15);color:#C084FC;border:1px solid rgba(168,85,247,0.25);margin:0 2px;">' + escHtml(label) + ': ' + escHtml(sample) + '</span>';
            }).join(' ');
            helperHtml = '<div class="mt-2 px-2 py-2 rounded-lg" style="background: rgba(168,85,247,0.06); border: 1px solid rgba(168,85,247,0.1);">' +
                '<p class="text-[10px] text-purple-300/70 mb-1">ℹ️ The colored chips below are auto-filled with each user\'s real data. Don\'t delete them — edit the text around them.</p>' +
                '<div class="flex flex-wrap gap-1 mt-1">' + chipExamples + '</div>' +
                '</div>';
        }

        card.innerHTML =
            '<div class="px-4 py-3 flex items-center justify-between" style="background: rgba(255,255,255,0.02); border-bottom: 1px solid rgba(255,255,255,0.04);">' +
                '<div>' +
                    '<span class="text-sm font-semibold text-white">' + escHtml(msg.label) + '</span>' +
                '</div>' +
                '<div class="flex items-center gap-2">' +
                    '<button onclick="saveBotMessage(\'' + key + '\')" class="px-4 py-1.5 rounded-lg text-xs font-semibold transition-all" style="background: rgba(16,185,129,0.15); color: #34D399; border: 1px solid rgba(16,185,129,0.2);">Save</button>' +
                    '<button onclick="resetBotMessage(\'' + key + '\')" class="px-4 py-1.5 rounded-lg text-xs font-semibold transition-all" style="background: rgba(255,255,255,0.05); color: #9CA3AF; border: 1px solid rgba(255,255,255,0.08);">Reset</button>' +
                '</div>' +
            '</div>' +
            '<div class="p-4">' +
                '<label class="text-[10px] text-gray-500 uppercase tracking-wider mb-1.5 block">Message Editor</label>' +
                '<div id="bce-' + key + '" contenteditable="true" ' +
                    'class="bce-editor w-full rounded-lg px-3 py-2.5 text-sm text-white border" ' +
                    'style="background: #0D1117; border-color: rgba(255,255,255,0.08);" ' +
                    'data-placeholder="Type your message here..." ' +
                    'data-key="' + key + '"' +
                '>' + toDisplayHtml(currentVal) + '</div>' +
                helperHtml +
                '<div id="bce-status-' + key + '" class="text-[10px] text-gray-500 mt-2 h-4"></div>' +
            '</div>';
        editor.appendChild(card);
    });

    loadBotContentFromFirestore();
}

function _renderConfigTab(configs, editor) {
    // Header
    var header = document.createElement('div');
    header.className = 'mb-6 px-2';
    header.innerHTML = '<div class="flex items-center gap-2 mb-2"><span style="font-size:20px;">⚙️</span><span class="text-lg font-bold text-white">System Configuration</span></div>' +
        '<p class="text-xs text-gray-400">Change game rules, limits, and settings. Values are applied instantly across the bot and web app.</p>';
    editor.appendChild(header);

    Object.keys(configs).forEach(function(key) {
        var cfg = configs[key];
        var currentVal = _botContentCache[key] || cfg.default;
        var inputType = cfg.type || 'text';

        var card = document.createElement('div');
        card.className = 'mb-4 rounded-xl overflow-hidden';
        card.style.cssText = 'background: linear-gradient(135deg, rgba(255,255,255,0.03), rgba(255,255,255,0.01)); border: 1px solid rgba(255,255,255,0.06);';

        card.innerHTML =
            '<div class="px-4 py-3 flex items-center justify-between">' +
                '<div class="flex-1 mr-4">' +
                    '<div class="text-sm font-semibold text-white mb-1">' + escHtml(cfg.label) + '</div>' +
                    '<div class="text-[11px] text-gray-500">' + escHtml(cfg.description || '') + '</div>' +
                '</div>' +
                '<div class="flex items-center gap-2">' +
                    '<input id="bce-' + key + '" type="' + inputType + '" value="' + escAttr(currentVal) + '" ' +
                        'class="rounded-lg px-3 py-2 text-sm text-white border font-semibold text-center" ' +
                        'style="background: #0D1117; border-color: rgba(255,255,255,0.1); width: 120px;" />' +
                    '<button onclick="saveConfigValue(\'' + key + '\')" class="px-3 py-2 rounded-lg text-xs font-semibold transition-all" ' +
                        'style="background: rgba(16,185,129,0.15); color: #34D399; border: 1px solid rgba(16,185,129,0.2);">Save</button>' +
                    '<button onclick="resetConfigValue(\'' + key + '\')" class="px-3 py-2 rounded-lg text-xs font-semibold transition-all" ' +
                        'style="background: rgba(255,255,255,0.05); color: #9CA3AF; border: 1px solid rgba(255,255,255,0.08);">Reset</button>' +
                '</div>' +
            '</div>' +
            '<div id="bce-status-' + key + '" class="text-[10px] text-gray-500 px-4 pb-2 h-4"></div>';
        editor.appendChild(card);
    });

    // Load live values from Firestore
    db.collection('bot_content').get().then(function(snap) {
        snap.forEach(function(doc) {
            _botContentCache[doc.id] = doc.data().content;
            var input = document.getElementById('bce-' + doc.id);
            if (input && input.tagName === 'INPUT') {
                input.value = doc.data().content;
            }
        });
    }).catch(function(e) { console.warn('Failed to load config:', e); });
}

function saveConfigValue(key) {
    var input = document.getElementById('bce-' + key);
    if (!input) return;
    var value = input.value.trim();
    var statusEl = document.getElementById('bce-status-' + key);

    db.collection('bot_content').doc(key).set({
        key: key,
        content: value,
        category: 'config',
        updatedAt: new Date()
    }).then(function() {
        _botContentCache[key] = value;
        if (statusEl) {
            statusEl.textContent = '✓ Saved — active now';
            statusEl.className = 'text-[10px] text-[#10B981] px-4 pb-2';
            setTimeout(function() { statusEl.textContent = ''; }, 3000);
        }
    }).catch(function(e) {
        if (statusEl) {
            statusEl.textContent = 'Error: ' + e.message;
            statusEl.className = 'text-[10px] text-red-400 px-4 pb-2';
        }
    });
}

function resetConfigValue(key) {
    var configs = BOT_CONTENT_DEFAULTS.config || {};
    var cfg = configs[key];
    if (!cfg) return;
    var input = document.getElementById('bce-' + key);
    if (input) input.value = cfg.default;
    db.collection('bot_content').doc(key).delete().catch(function() {});
    delete _botContentCache[key];
    var statusEl = document.getElementById('bce-status-' + key);
    if (statusEl) {
        statusEl.textContent = '✓ Reset to default (' + cfg.default + ')';
        statusEl.className = 'text-[10px] text-[#FF8C00] px-4 pb-2';
        setTimeout(function() { statusEl.textContent = ''; }, 3000);
    }
}

function loadBotContentFromFirestore() {
    db.collection('bot_content').get().then(function(snap) {
        snap.forEach(function(doc) {
            _botContentCache[doc.id] = doc.data().content;
            var editorEl = document.getElementById('bce-' + doc.id);
            if (editorEl) {
                editorEl.innerHTML = toDisplayHtml(doc.data().content);
            }
        });
    }).catch(function(e) { console.warn('Failed to load bot_content:', e); });
}

function saveBotMessage(key) {
    var editorEl = document.getElementById('bce-' + key);
    if (!editorEl) return;
    var value = toBackendText(editorEl);
    var statusEl = document.getElementById('bce-status-' + key);

    db.collection('bot_content').doc(key).set({
        key: key,
        content: value,
        category: _currentBotCategory,
        updatedAt: new Date()
    }).then(function() {
        _botContentCache[key] = value;
        if (statusEl) {
            statusEl.textContent = '✓ Saved';
            statusEl.className = 'text-[10px] text-[#10B981] ml-2';
            setTimeout(function() { statusEl.textContent = ''; }, 2000);
        }
    }).catch(function(e) {
        if (statusEl) {
            statusEl.textContent = 'Error: ' + e.message;
            statusEl.className = 'text-[10px] text-red-400 ml-2';
        }
    });
}

function resetBotMessage(key) {
    var messages = BOT_CONTENT_DEFAULTS[_currentBotCategory] || {};
    var msg = messages[key];
    if (!msg) return;
    var editorEl = document.getElementById('bce-' + key);
    if (editorEl) {
        editorEl.innerHTML = toDisplayHtml(msg.default);
    }
    db.collection('bot_content').doc(key).delete().catch(function() {});
    delete _botContentCache[key];
    var statusEl = document.getElementById('bce-status-' + key);
    if (statusEl) {
        statusEl.textContent = '✓ Reset to default';
        statusEl.className = 'text-[10px] text-[#FF8C00] ml-2';
        setTimeout(function() { statusEl.textContent = ''; }, 2000);
    }
}

function escHtml(str) {
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function seedBotContent() {
    if (!confirm('This will populate all bot messages with defaults. Existing customizations will be preserved. Continue?')) return;
    var apiBase = window.BACKEND_URL || window.API_BASE || '';
    fetch(apiBase + '/api/admin/bot-content/seed', { method: 'POST' })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            alert('Seeded ' + (data.seeded || 0) + ' messages!');
            loadBotContentFromFirestore();
        })
        .catch(function(e) { alert('Error: ' + e.message); });
}

// ==================== WALLET ====================
function openDepositBot() {
    if (tg) { tg.openTelegramLink('https://t.me/kelembingobot'); }
    else { window.open('https://t.me/kelembingobot', '_blank'); }
}

function requestWithdrawal() {
    const bal = currentUser ? currentUser.balance || 0 : 0;
    document.getElementById('withdraw-available').textContent = bal + ' ETB';
    document.getElementById('withdrawModal').classList.remove('hidden');
}

async function submitWithdrawal() {
    const amount = parseInt(document.getElementById('withdrawAmount').value);
    const phone = document.getElementById('withdrawTelebirr').value.trim();
    const name = document.getElementById('withdrawTelebirrName').value.trim();
    if (!amount || amount < 50) { showToast('Minimum withdrawal: 50 ETB'); return; }
    if (!phone) { showToast('Enter phone number'); return; }
    try {
        const apiBase = window.API_BASE || window.location.origin || (window.location.protocol + '//' + window.location.host);
        try {
            const valRes = await fetch(apiBase + '/api/validate-withdrawal/' + currentUser.id + '?amount=' + amount);
            const val = await valRes.json();
            if (!val.ok) {
                const errorMessages = {
                    below_min: 'Minimum withdrawal is ' + (val.min || 50) + ' ETB',
                    insufficient: 'Insufficient balance! Your balance: ' + (val.balance || 0) + ' ETB',
                    above_max: 'Maximum withdrawal is ' + (val.max || 50000) + ' ETB',
                    no_phone: 'Please register with your phone number first',
                    account_new: 'Your account is too new. Wait 24 hours after registration.',
                    pending_exists: 'You already have a pending withdrawal. Wait for it to be processed.',
                    daily_limit: 'Daily withdrawal limit reached (' + (val.limit || 3) + '/day). Try again tomorrow.',
                    cooldown: 'Please wait ' + (val.minutes || 0) + ' minutes before another withdrawal.',
                };
                showToast(errorMessages[val.error] || 'Withdrawal not allowed');
                return;
            }
        } catch (e) { console.warn('Validation API failed, proceeding:', e); }
        const userRef = db.collection('users').doc(String(currentUser.id));
        const snap = await userRef.get();
        const bal = (snap.data().balance || 0);
        if (amount > bal) { showToast('Insufficient balance!'); return; }
        await userRef.update({
            balance: bal - amount,
            updated_at: firebase.firestore.FieldValue.serverTimestamp()
        });
        const withdrawRef = await db.collection('withdrawals').add({
            userId: String(currentUser.id),
            firstName: currentUser.first_name,
            username: currentUser.username,
            amount: amount,
            phone: phone,
            telebirrName: name,
            status: 'pending',
            createdAt: firebase.firestore.FieldValue.serverTimestamp()
        });
        try {
            await fetch(apiBase + '/api/admin/withdrawals/notify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    withdrawal_id: withdrawRef.id,
                    user_id: currentUser.id,
                    first_name: currentUser.first_name,
                    username: currentUser.username,
                    amount: amount,
                    phone: phone,
                    telebirr_name: name
                })
            });
        } catch (e) { console.warn('Admin notification failed:', e); }
        hideScreen('withdrawModal');
        showToast('Withdrawal request submitted!');
    } catch (err) { showToast('Error: ' + err.message); }
}

function showTransferModal() { document.getElementById('transfer-modal').classList.remove('hidden'); }
function hideTransferModal() { document.getElementById('transfer-modal').classList.add('hidden'); }

async function transferFunds(direction) {
    const amount = parseInt(document.getElementById('transfer-amount').value);
    if (!amount || amount < 1) { showToast('Enter a valid amount'); return; }
    const userRef = db.collection('users').doc(String(currentUser.id));
    try {
        const snap = await userRef.get();
        const u = snap.data();
        if (direction === 'toPlay') {
            if ((u.balance || 0) < amount) { showToast('Insufficient balance!'); return; }
            await userRef.update({
                balance: (u.balance || 0) - amount,
                play_wallet: (u.play_wallet || 0) + amount,
                updated_at: firebase.firestore.FieldValue.serverTimestamp()
            });
        } else {
            if ((u.play_wallet || 0) < amount) { showToast('Insufficient play wallet!'); return; }
            await userRef.update({
                play_wallet: (u.play_wallet || 0) - amount,
                balance: (u.balance || 0) + amount,
                updated_at: firebase.firestore.FieldValue.serverTimestamp()
            });
        }
        hideTransferModal();
        showToast('Transfer successful!');
        document.getElementById('transfer-amount').value = '';
    } catch (err) { showToast('Error: ' + err.message); }
}

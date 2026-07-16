// ==================== WALLET ====================
function openDepositBot() {
    if (tg) { tg.openTelegramLink('https://t.me/yegarabingobot'); }
    else { window.open('https://t.me/yegarabingobot', '_blank'); }
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
    if (!amount || amount < 10) { showToast('Min withdrawal: 10 ETB'); return; }
    if (!phone) { showToast('Enter phone number'); return; }
    const bal = currentUser.balance || 0;
    if (amount > bal) { showToast('Insufficient balance!'); return; }
    try {
        await db.collection('users').doc(String(currentUser.id)).update({
            balance: bal - amount,
            updated_at: firebase.firestore.FieldValue.serverTimestamp()
        });
        await db.collection('withdrawals').add({
            userId: String(currentUser.id),
            firstName: currentUser.first_name,
            username: currentUser.username,
            amount: amount,
            phone: phone,
            telebirrName: name,
            status: 'pending',
            createdAt: firebase.firestore.FieldValue.serverTimestamp()
        });
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

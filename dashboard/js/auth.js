// ==================== AUTH / USER ====================
function getTelegramUser() {
    if (tg && tg.initDataUnsafe && tg.initDataUnsafe.user && tg.initDataUnsafe.user.id) return tg.initDataUnsafe.user;
    if (tg && tg.initData && tg.initData.length > 10) {
        try { const p = new URLSearchParams(tg.initData); const u = p.get('user'); if (u) return JSON.parse(u); } catch(e) {}
    }
    return null;
}

async function initUser() {
    // Sync server clock before anything else
    await syncServerTime();

    if (!tg) {
        document.getElementById('user-greeting').textContent = '';
        const hero = document.querySelector('#screen-home .glass.rounded-2xl.p-5');
        if (hero) hero.innerHTML = '<div class="text-3xl mb-2">📱</div><h2 class="text-lg font-bold text-white mb-2">Open from Telegram</h2><p class="text-sm text-white/60 mb-4">Please open this game from the Telegram bot.</p><a href="https://t.me/yegarabingobot" target="_blank" class="inline-block gradient-orange text-white px-6 py-3 rounded-xl font-semibold text-sm">Open Bot</a>';
        return;
    }

    let tgUser = getTelegramUser();
    if (!tgUser || !tgUser.id) {
        for (let i = 0; i < 20; i++) {
            await new Promise(r => setTimeout(r, 250));
            tgUser = getTelegramUser();
            if (tgUser && tgUser.id) break;
        }
    }
    if (!tgUser || !tgUser.id) {
        document.getElementById('user-greeting').innerHTML = 'Error loading user. <a href="javascript:location.reload()" style="color:#FF8C00;text-decoration:underline;">Tap to retry</a>';
        return;
    }

    const uid = tgUser.id;
    try {
        const userDoc = await db.collection('users').doc(String(uid)).get();
        if (userDoc.exists) {
            currentUser = { id: uid, ...userDoc.data() };
        } else {
            const newUser = {
                user_id: uid,
                first_name: tgUser.first_name || 'Player',
                username: tgUser.username || 'player' + uid,
                phone: '', balance: 0, play_wallet: 0, bonus: 0,
                total_games: 0, wins: 0, losses: 0, is_playing: false,
                created_at: firebase.firestore.FieldValue.serverTimestamp(),
                updated_at: firebase.firestore.FieldValue.serverTimestamp()
            };
            await db.collection('users').doc(String(uid)).set(newUser);
            currentUser = { id: uid, ...newUser };
        }
        updateAllDisplays();
        listenToUserData();
        startStatsListener();
        if (!currentUser.phone) showRegistration();
    } catch (err) {
        console.error('Error initializing user:', err);
        document.getElementById('user-greeting').textContent = 'Error: ' + err.message;
    }
}

function showRegistration() {
    document.getElementById('regName').value = currentUser.first_name || '';
    document.getElementById('regPhone').value = currentUser.phone || '';
    document.getElementById('registerModal').classList.remove('hidden');
}

async function submitRegistration() {
    const name = document.getElementById('regName').value.trim();
    const phone = document.getElementById('regPhone').value.trim();
    if (!name) { showToast('Please enter your name'); return; }
    if (!phone || !phone.startsWith('+251')) { showToast('Enter valid phone (+251...)'); return; }
    try {
        await db.collection('users').doc(String(currentUser.id)).update({
            first_name: name, phone: phone, registered: true,
            updated_at: firebase.firestore.FieldValue.serverTimestamp()
        });
        currentUser.first_name = name;
        currentUser.phone = phone;
        updateAllDisplays();
        document.getElementById('registerModal').classList.add('hidden');
        showToast('Profile complete!');
    } catch (err) { showToast('Error saving profile.'); }
}

function listenToUserData() {
    if (userUnsubscribe) userUnsubscribe();
    userUnsubscribe = db.collection('users').doc(String(currentUser.id)).onSnapshot(doc => {
        if (doc.exists) { currentUser = { id: currentUser.id, ...doc.data() }; updateAllDisplays(); }
    });
}

function startStatsListener() {
    if (statsUnsubscribe) statsUnsubscribe();
    statsUnsubscribe = db.collection('rounds').where('status', 'in', ['selecting', 'playing']).onSnapshot(snap => {
        let totalPlayers = 0;
        snap.forEach(doc => { totalPlayers += (doc.data().player_count || 0); });
        document.getElementById('stat-players').textContent = totalPlayers;
    });
    function refreshCompletedStats() {
        db.collection('rounds').where('status', '==', 'completed').get().then(snap => {
            document.getElementById('stat-games').textContent = snap.size;
        }).catch(() => {});
        const today = new Date(); today.setHours(0, 0, 0, 0);
        db.collection('rounds').where('status', '==', 'completed').get().then(snap => {
            let winners = 0;
            snap.forEach(doc => {
                const d = doc.data();
                if (d.winners && d.winners.length > 0) {
                    const ca = d.completed_at;
                    if (ca) {
                        const dt = ca.toDate ? ca.toDate() : new Date(ca);
                        if (dt >= today) winners += d.winners.length;
                    }
                }
            });
            document.getElementById('stat-winners').textContent = winners;
        }).catch(() => {});
    }
    refreshCompletedStats();
    setInterval(refreshCompletedStats, 30000);
}

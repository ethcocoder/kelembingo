// ==================== PLAY NOW ====================
async function playNow() {
    if (!currentUser) { showToast('Loading user data...'); return; }
    const pw = currentUser.play_wallet || 0;
    if (pw < STAKE) {
        showToast('Not enough balance! Need at least ' + STAKE + ' ETB');
        return;
    }

    showLoading('Finding game...');
    try {
        // Find current active round (selecting or playing)
        let roundSnap = await db.collection('rounds')
            .where('status', 'in', ['selecting', 'playing'])
            .orderBy('created_at', 'desc')
            .limit(1).get();

        let roundData, roundId;
        if (roundSnap.empty) {
            // No active round yet. Create one immediately so the user doesn't have to wait.
            roundData = {
                status: 'selecting',
                stake: STAKE,
                players: {},
                player_count: 0,
                taken_cartelas: [],
                called_numbers: [],
                winners: [],
                prize_per_winner: 0,
                admin_profit: 0,
                created_at: firebase.firestore.FieldValue.serverTimestamp(),
                completed_at: null,
            };
            const ref = await db.collection('rounds').add(roundData);
            roundId = ref.id;
            currentRoundId = roundId;
            
            hideLoading();
            showCardSelection(roundId, roundData);
            return;
        }

        const doc = roundSnap.docs[0];
        roundData = doc.data();
        roundId = doc.id;
        currentRoundId = roundId;

        if (roundData.status === 'playing') {
            // Already checking if they played
            if (roundData.players && roundData.players[String(currentUser.id)]) {
                hideLoading();
                showToast('Rejoining current game!');
                await navigateTo('game');
                await loadMyCartelas(roundData);
                listenToRound(roundId);
                return;
            } else {
                hideLoading();
                showToast('Round in progress! Spectator mode.');
                isSpectator = true;
                await navigateTo('game');
                setupGameBoard();
                listenToRound(roundId);
                return;
            }
        } else {
            // Selecting status
            if (roundData.players && roundData.players[String(currentUser.id)]) {
                hideLoading();
                showToast('You already joined this round!');
                await navigateTo('game');
                await loadMyCartelas(roundData);
                listenToRound(roundId);
                return;
            }
            
            hideLoading();
            showCardSelection(roundId, roundData);
        }
    } catch (err) {
        hideLoading();
        console.error('Error finding round:', err);
        showToast('Error: ' + err.message);
    }
}

// ==================== CARD SELECTION ====================
async function showCardSelection(roundId, roundData) {
    selectedCartelas = [];
    listenerReady = false;
    updateSelectedInfo();

    // Calculate estimated derash: player_count * stake * 0.75
    const playerCount = roundData.player_count || 0;
    const estimatedDerash = Math.round((playerCount || 1) * STAKE * 0.75);
    document.getElementById('cs-stake').textContent = STAKE + ' ETB';
    document.getElementById('cs-derash').textContent = estimatedDerash + ' ETB';
    document.getElementById('cs-main-wallet').textContent = (currentUser.balance || 0) + ' ETB';
    document.getElementById('cs-play-wallet').textContent = (currentUser.play_wallet || 0) + ' ETB';
    document.getElementById('cs-preview-container').classList.add('hidden');
    document.getElementById('card-select-screen').classList.remove('hidden');

    const grid = document.getElementById('card-select-grid');
    grid.innerHTML = '<div class="col-span-8 text-center py-8"><div class="text-3xl mb-2 float-anim">🃏</div><p class="text-white/50 text-sm">Loading cartelas...</p></div>';

    try {
        const masterSnap = await db.collection('cartelas_master').orderBy('number').get();
        if (masterSnap.empty) {
            grid.innerHTML = '<div class="col-span-8 text-center py-12 px-4"><div class="text-4xl mb-3">😓</div><p class="text-white/80 text-sm font-bold mb-1">No Cards Generated</p><p class="text-white/40 text-xs">Admin needs to generate cartelas first.</p></div>';
            return;
        }

        const takenSet = new Set(roundData.taken_cartelas || []);

        grid.innerHTML = '';
        masterSnap.forEach(doc => {
            const d = doc.data();
            const num = d.number;
            const cell = document.createElement('div');
            cell.className = 'card-tile';
            cell.textContent = num;
            cell.dataset.num = num;

            if (takenSet.has(num)) {
                cell.classList.add('taken');
            } else {
                cell.onclick = () => toggleCardSelection(num, cell);
            }
            grid.appendChild(cell);
        });

        if (roundUnsubscribe) roundUnsubscribe();
        roundUnsubscribe = db.collection('rounds').doc(roundId).onSnapshot(snap => {
            if (!snap.exists) return;
            const rd = snap.data();
            const nowTaken = new Set(rd.taken_cartelas || []);
            grid.querySelectorAll('.card-tile').forEach(cell => {
                const n = parseInt(cell.dataset.num);
                if (nowTaken.has(n) && !selectedCartelas.includes(n)) {
                    cell.className = 'card-tile taken';
                    cell.onclick = null;
                }
            });

            if (!listenerReady) {
                listenerReady = true;
                return;
            }

            if (rd.status === 'completed' || rd.status === 'cancelled') {
                const selectScreen = document.getElementById('card-select-screen');
                if (selectScreen && !selectScreen.classList.contains('hidden')) {
                    if (roundUnsubscribe) { roundUnsubscribe(); roundUnsubscribe = null; }
                    playNow();
                    return;
                }
            }

            if (rd.status === 'playing') {
                const uid = String(currentUser.id);
                if (rd.players && rd.players[uid]) {
                    document.getElementById('card-select-screen').classList.add('hidden');
                    await navigateTo('game');
                    loadMyCartelas(rd);
                    listenToRound(roundId);
                } else {
                    document.getElementById('card-select-screen').classList.add('hidden');
                    await navigateTo('game');
                    setupGameBoard();
                    listenToRound(roundId);
                }
            }
        });
    } catch (err) {
        console.error('Error loading cartelas:', err);
        grid.innerHTML = '<div class="col-span-8 text-center py-8"><p class="text-red-400 text-sm">Error: ' + err.message + '</p></div>';
    }
}

function toggleCardSelection(num, cell) {
    const idx = selectedCartelas.indexOf(num);
    if (idx > -1) {
        selectedCartelas.splice(idx, 1);
        cell.className = 'card-tile';
        cell.style.boxShadow = '';
        if (selectedCartelas.length > 0) {
            renderCardSelectPreview(selectedCartelas[selectedCartelas.length - 1]);
        } else {
            document.getElementById('cs-preview-container').classList.add('hidden');
        }
    } else {
        if (selectedCartelas.length >= MAX_CARTELAS) {
            showToast('Maximum ' + MAX_CARTELAS + ' cartelas!');
            return;
        }
        const budgetMax = Math.floor((currentUser.play_wallet || 0) / STAKE);
        if (selectedCartelas.length >= budgetMax) {
            showToast('Not enough balance for more cards!');
            return;
        }
        selectedCartelas.push(num);
        cell.className = 'card-tile selected';
        renderCardSelectPreview(num);
    }
    updateSelectedInfo();
}

async function renderCardSelectPreview(num) {
    const container = document.getElementById('cs-preview-container');
    const grid = document.getElementById('cs-preview-grid');
    const title = document.getElementById('cs-preview-title');
    if (!num) {
        container.classList.add('hidden');
        return;
    }
    container.classList.remove('hidden');
    title.textContent = 'Cartela No : ' + num;
    grid.innerHTML = '<div class="col-span-5 text-center text-xs py-2 text-gray-500 font-normal">Loading card numbers...</div>';
    try {
        const doc = await db.collection('cartelas_master').doc(String(num)).get();
        if (doc.exists) {
            const data = doc.data();
            const flat = data.cartela || [];
            grid.innerHTML = '';
            for (let i = 0; i < 25; i++) {
                const val = flat[i];
                const cell = document.createElement('div');
                cell.className = 'py-2 rounded-lg bg-white/5 border border-white/10 text-gray-300 font-bold text-xs flex items-center justify-center';
                if (val === 0) {
                    cell.innerHTML = '✨';
                    cell.className = 'py-2 rounded-lg border border-emerald-500 text-white font-bold text-xs flex items-center justify-center bg-emerald-600';
                } else {
                    cell.textContent = val;
                }
                grid.appendChild(cell);
            }
        } else {
            grid.innerHTML = '<div class="col-span-5 text-center text-xs py-2 text-red-400 font-normal">Card numbers not found</div>';
        }
    } catch(err) {
        console.error(err);
        grid.innerHTML = '<div class="col-span-5 text-center text-xs py-2 text-red-500 font-normal">Error loading card</div>';
    }
}

function updateSelectedInfo() {
    const count = selectedCartelas.length;
    const info = document.getElementById('cs-selected-info');
    const btn = document.getElementById('cs-confirm-btn');
    if (count > 0) {
        info.classList.remove('hidden');
        if(btn) btn.classList.remove('hidden');
        document.getElementById('cs-selected-count').textContent = count + '/' + MAX_CARTELAS;
        document.getElementById('cs-selected-total').textContent = (count * STAKE) + ' ETB';
    } else {
        info.classList.add('hidden');
        if(btn) btn.classList.add('hidden');
    }
}

// ==================== SPECTATOR / CANCEL ====================
function cancelCardSelect() {
    selectedCartelas = [];
    document.getElementById('cs-preview-container').classList.add('hidden');
    if (roundUnsubscribe) { roundUnsubscribe(); roundUnsubscribe = null; }
    document.getElementById('card-select-screen').classList.add('hidden');
}

function enterSpectatorMode() {
    isSpectator = true;
    document.getElementById('card-select-screen').classList.add('hidden');
    navigateTo('game');
    setupGameBoard();
    listenToRound(currentRoundId);
    showToast('Spectating...');
}

function refreshCardSelect() {
    if (currentRoundId) {
        db.collection('rounds').doc(currentRoundId).get().then(doc => {
            if (doc.exists) showCardSelection(currentRoundId, doc.data());
        });
    }
}

// ==================== CONFIRM SELECTION & JOIN ROUND ====================
async function confirmSelection() {
    if (selectedCartelas.length === 0) { showToast('Select at least one card!'); return; }
    isSpectator = false;
    showLoading('Joining round...');

    try {
        const totalCost = selectedCartelas.length * STAKE;
        const uidStr = String(currentUser.id);
        const roundRef = db.collection('rounds').doc(currentRoundId);
        const userRef = db.collection('users').doc(uidStr);

        await db.runTransaction(async (txn) => {
            const roundSnap = await txn.get(roundRef);
            const userSnap = await txn.get(userRef);
            if (!roundSnap.exists) throw new Error('Round not found.');
            const rd = roundSnap.data();
            if (rd.status !== 'selecting' && rd.status !== 'playing') throw new Error('Round already finished or cancelled.');
            if (rd.players && rd.players[uidStr]) throw new Error('Already joined.');
            const pw = userSnap.data().play_wallet || 0;
            if (pw < totalCost) throw new Error('Not enough balance.');

            txn.update(userRef, {
                play_wallet: pw - totalCost,
                is_playing: true,
                updated_at: firebase.firestore.FieldValue.serverTimestamp()
            });

            const players = rd.players || {};
            players[uidStr] = {
                cartelas: selectedCartelas,
                name: currentUser.first_name || 'Player',
                joined_at: new Date().toISOString()
            };
            const takenSet = new Set(rd.taken_cartelas || []);
            selectedCartelas.forEach(n => takenSet.add(n));

            txn.update(roundRef, {
                players: players,
                player_count: Object.keys(players).length,
                taken_cartelas: Array.from(takenSet),
            });
        });

        for (const num of selectedCartelas) {
            const cartelaDoc = await db.collection('cartelas_master').doc(String(num)).get();
            if (cartelaDoc.exists) {
                myCartelas[num] = cartelaDoc.data().cartela;
            }
        }

        hideLoading();
        document.getElementById('cs-preview-container').classList.add('hidden');
        document.getElementById('card-select-screen').classList.add('hidden');
        await navigateTo('game');
        setupGameBoard();
        listenToRound(currentRoundId);
        showToast('Joined! Waiting for game to start...');
    } catch (err) {
        hideLoading();
        console.error('Error joining round:', err);
        showToast('Error: ' + err.message);
    }
}

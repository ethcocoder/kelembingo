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

        if (roundSnap.empty) {
            hideLoading();
            showToast('Waiting for the next round to start...');
            // The backend monitor will automatically create the round shortly
            return;
        }

        const doc = roundSnap.docs[0];
        const roundData = doc.data();
        const roundId = doc.id;
        currentRoundId = roundId;

        if (roundData.status === 'playing') {
            // Already checking if they played
            if (roundData.players && roundData.players[String(currentUser.id)]) {
                hideLoading();
                showToast('Rejoining current game!');
                navigateTo('game');
                await loadMyCartelas(roundData);
                listenToRound(roundId);
                return;
            } else {
                hideLoading();
                showToast('Round in progress! Spectator mode.');
                isSpectator = true;
                navigateTo('game');
                setupGameBoard();
                listenToRound(roundId);
                return;
            }
        } else {
            // Selecting status
            if (roundData.players && roundData.players[String(currentUser.id)]) {
                hideLoading();
                showToast('You already joined this round!');
                navigateTo('game');
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

// ==================== CARD SELECTION (35s timer) ====================
async function showCardSelection(roundId, roundData) {
    selectedCartelas = [];
    listenerReady = false;
    updateSelectedInfo();

    document.getElementById('cs-stake').textContent = STAKE + ' ETB';
    document.getElementById('cs-main-wallet').textContent = (currentUser.balance || 0) + ' ETB';
    document.getElementById('cs-play-wallet').textContent = (currentUser.play_wallet || 0) + ' ETB';
    document.getElementById('cs-preview-container').classList.add('hidden');
    document.getElementById('card-select-screen').classList.remove('hidden');

    const grid = document.getElementById('card-select-grid');
    grid.innerHTML = '<div class="text-center py-8 col-span-10"><div class="text-3xl mb-2 float-anim">🃏</div><p class="text-white/50 text-sm">Loading cartelas...</p></div>';

    try {
        const masterSnap = await db.collection('cartelas_master').orderBy('number').get();
        if (masterSnap.empty) {
            grid.innerHTML = '<div class="col-span-10 text-center py-12 px-4"><div class="text-4xl mb-3">😓</div><p class="text-white/80 text-sm font-bold mb-1">No Cards Generated</p><p class="text-white/40 text-xs">Admin needs to generate cartelas first.</p></div>';
            return;
        }

        const takenSet = new Set(roundData.taken_cartelas || []);

        grid.innerHTML = '';
        masterSnap.forEach(doc => {
            const d = doc.data();
            const num = d.number;
            const cell = document.createElement('div');
            cell.className = 'card-num';
            cell.textContent = num;
            cell.dataset.num = num;

            if (takenSet.has(num)) {
                cell.classList.add('taken');
            } else {
                cell.onclick = () => toggleCardSelection(num, cell);
            }
            grid.appendChild(cell);
        });

        const deadline = roundData.selection_deadline;
        if (deadline) {
            const deadlineMs = deadline.toDate ? deadline.toDate().getTime() : new Date(deadline).getTime();
            selectionDeadline = deadlineMs;
        } else {
            selectionDeadline = Date.now() + SELECTION_SECONDS * 1000;
        }
        startSelectionTimer();

        if (roundUnsubscribe) roundUnsubscribe();
        roundUnsubscribe = db.collection('rounds').doc(roundId).onSnapshot(snap => {
            if (!snap.exists) return;
            const rd = snap.data();
            const nowTaken = new Set(rd.taken_cartelas || []);
            grid.querySelectorAll('.card-num').forEach(cell => {
                const n = parseInt(cell.dataset.num);
                if (nowTaken.has(n) && !selectedCartelas.includes(n)) {
                    cell.className = 'card-num taken';
                    cell.onclick = null;
                }
            });

            if (!listenerReady) {
                listenerReady = true;
                return;
            }

            if (rd.status === 'playing') {
                const uid = String(currentUser.id);
                if (rd.players && rd.players[uid]) {
                    stopSelectionTimer();
                    selectionHandled = true;
                    document.getElementById('card-select-screen').classList.add('hidden');
                    navigateTo('game');
                    loadMyCartelas(rd);
                    listenToRound(roundId);
                } else if (!selectionHandled && selectedCartelas.length > 0) {
                    stopSelectionTimer();
                    selectionHandled = true;
                    document.getElementById('card-select-screen').classList.add('hidden');
                    navigateTo('game');
                    isSpectator = true;
                    setupGameBoard();
                    listenToRound(roundId);
                    showToast('Round already started — spectating');
                    for (const num of selectedCartelas) {
                        db.collection('cartelas_master').doc(String(num)).get().then(cartelaDoc => {
                            if (cartelaDoc.exists) {
                                myCartelas[num] = cartelaDoc.data().cartela;
                                setupGameBoard();
                            }
                        });
                    }
                } else if (!selectionHandled) {
                    stopSelectionTimer();
                    selectionHandled = true;
                    enterSpectatorMode();
                }
            }
        });
    } catch (err) {
        console.error('Error loading cartelas:', err);
        grid.innerHTML = '<div class="text-center py-8"><p class="text-red-400 text-sm">Error: ' + err.message + '</p></div>';
    }
}

function toggleCardSelection(num, cell) {
    const idx = selectedCartelas.indexOf(num);
    if (idx > -1) {
        selectedCartelas.splice(idx, 1);
        cell.className = 'card-num';
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
        cell.className = 'card-num selected';
        cell.style.boxShadow = '0 0 15px rgba(16,185,129,0.5)';
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
                cell.className = 'py-1.5 rounded bg-white/5 border border-white/5 text-gray-300 font-bold text-xs flex items-center justify-center';
                if (val === 0) {
                    cell.innerHTML = '✨';
                    cell.className = 'py-1.5 rounded border border-emerald-500 text-white font-bold text-xs flex items-center justify-center bg-emerald-600';
                } else {
                    cell.textContent = val;
                }
                grid.appendChild(cell);
            }
        } else {
            grid.innerHTML = '<div class="col-span-10 text-center text-xs py-2 text-red-400 font-normal">Card numbers not found</div>';
        }
    } catch(err) {
        console.error(err);
        grid.innerHTML = '<div class="col-span-10 text-center text-xs py-2 text-red-500 font-normal">Error loading card</div>';
    }
}

function updateSelectedInfo() {
    const count = selectedCartelas.length;
    const info = document.getElementById('cs-selected-info');
    const btn = document.getElementById('cs-confirm-btn');
    if (count > 0) {
        info.classList.remove('hidden');
        if(btn) btn.classList.add('hidden'); // explicitly keep hidden
        document.getElementById('cs-selected-count').textContent = count + '/' + MAX_CARTELAS;
        document.getElementById('cs-selected-total').textContent = (count * STAKE) + ' ETB';
    } else {
        info.classList.add('hidden');
        if(btn) btn.classList.add('hidden');
    }
}

// ==================== SELECTION TIMER ====================
function startSelectionTimer() {
    stopSelectionTimer();
    selectionHandled = false;
    const timerEl = document.getElementById('cs-timer');
    timerEl.classList.remove('text-red-400');
    selectionTimer = setInterval(() => {
        const rem = Math.max(0, Math.ceil((selectionDeadline - Date.now()) / 1000));
        timerEl.textContent = rem;
        if (rem <= 5) timerEl.classList.add('text-red-400');
        if (rem <= 0) {
            stopSelectionTimer();
            if (selectionHandled) return;
            selectionHandled = true;
            if (selectedCartelas.length > 0) {
                confirmSelection();
            } else {
                enterSpectatorMode();
            }
        }
    }, 200);
}

function stopSelectionTimer() {
    if (selectionTimer) { clearInterval(selectionTimer); selectionTimer = null; }
}

// ==================== GAME COUNTDOWN ====================
function startGameCountdown(nextMs) {
    if (gameCountdownInterval) clearInterval(gameCountdownInterval);
    const timerEl = document.getElementById('game-timer');
    gameCountdownInterval = setInterval(() => {
        const rem = Math.max(0, Math.ceil((nextMs - Date.now()) / 1000));
        timerEl.textContent = rem + 's';
        if (rem <= 1) timerEl.textContent = '...';
        if (rem <= 0) {
            timerEl.textContent = '...';
            clearInterval(gameCountdownInterval);
            gameCountdownInterval = null;
        }
    }, 200);
}

function stopGameCountdown() {
    if (gameCountdownInterval) { clearInterval(gameCountdownInterval); gameCountdownInterval = null; }
}

function startSelectionCountdownOnGame(dlMs) {
    if (gameCountdownInterval) clearInterval(gameCountdownInterval);
    const banner = document.getElementById('game-countdown');
    const timerEl = document.getElementById('game-timer');
    gameCountdownInterval = setInterval(() => {
        const rem = Math.max(0, Math.ceil((dlMs - Date.now()) / 1000));
        banner.textContent = 'Game starts in ' + rem + 's';
        timerEl.textContent = rem + 's';
        if (rem <= 0) {
            banner.textContent = 'Game starting...';
            timerEl.textContent = '...';
            clearInterval(gameCountdownInterval);
            gameCountdownInterval = null;
        }
    }, 200);
}

// ==================== SPECTATOR / CANCEL ====================
function cancelCardSelect() {
    stopSelectionTimer();
    selectedCartelas = [];
    document.getElementById('cs-preview-container').classList.add('hidden');
    if (roundUnsubscribe) { roundUnsubscribe(); roundUnsubscribe = null; }
    document.getElementById('card-select-screen').classList.add('hidden');
}

function enterSpectatorMode() {
    isSpectator = true;
    stopSelectionTimer();
    selectionHandled = true;
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
    stopSelectionTimer();
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
            if (rd.status !== 'selecting') throw new Error('Round already started.');
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
        navigateTo('game');
        setupGameBoard();
        listenToRound(currentRoundId);
        showToast('Joined! Waiting for game to start...');
    } catch (err) {
        hideLoading();
        console.error('Error joining round:', err);
        showToast('Error: ' + err.message);
    }
}

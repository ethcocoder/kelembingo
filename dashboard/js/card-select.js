// ==================== PLAY NOW ====================
async function playNow() {
    if (!currentUser) { showToast('Loading user data...'); return; }
    var pw = currentUser.play_wallet || 0;
    var hasBalance = pw >= STAKE;

    showLoading('Finding game...');
    try {
        var roundSnap = await db.collection('rounds')
            .where('status', 'in', ['selecting', 'playing'])
            .orderBy('created_at', 'desc')
            .limit(1).get();

        var roundData, roundId;
        if (roundSnap.empty) {
            var nowMs = serverNow();
            selectedCartelas = [];
            myCartelas = {};
            calledNumbers = new Set();
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
                selection_deadline: new Date(nowMs + SELECTION_DURATION * 1000).toISOString(),
                created_at: firebase.firestore.FieldValue.serverTimestamp(),
                completed_at: null,
            };
            var ref = await db.collection('rounds').add(roundData);
            roundId = ref.id;
            currentRoundId = roundId;
            
            hideLoading();
            showCardSelection(roundId, roundData);
            return;
        }

        var doc = roundSnap.docs[0];
        roundData = doc.data();
        roundId = doc.id;
        currentRoundId = roundId;

        // Already playing — check if user is a player
        if (roundData.status === 'playing') {
            if (roundData.players && roundData.players[String(currentUser.id)]) {
                hideLoading();
                showToast('Rejoining current game!');
                await navigateTo('game');
                await loadMyCartelas(roundData);
                listenToRound(roundId);
                return;
            } else {
                // Spectator mode for everyone (with or without balance)
                hideLoading();
                isSpectator = true;
                await navigateTo('game');
                setupGameBoard();
                listenToRound(roundId);
                showToast('Round in progress — spectating...');
                return;
            }
        }

        // Round is in 'selecting' state
        if (roundData.players && roundData.players[String(currentUser.id)]) {
            hideLoading();
            showToast('You already joined this round!');
            await navigateTo('game');
            await loadMyCartelas(roundData);
            listenToRound(roundId);
            return;
        }

        hideLoading();

        // Check if selection timer has already expired
        var deadline = roundData.selection_deadline;
        if (deadline) {
            var dlMs;
            if (typeof deadline === 'object' && deadline.toDate) dlMs = deadline.toDate().getTime();
            else if (typeof deadline === 'string') dlMs = new Date(deadline).getTime();
            else if (typeof deadline === 'object' && deadline._iso) dlMs = new Date(deadline._iso).getTime();
            else if (typeof deadline === 'object' && deadline.seconds) dlMs = deadline.seconds * 1000;
            else dlMs = new Date(deadline).getTime();
            if (!isNaN(dlMs) && serverNow() >= dlMs) {
                // Timer expired — only spectate if players already joined
                var pc = roundData.player_count || 0;
                if (pc > 0) {
                    isSpectator = true;
                    await navigateTo('game');
                    setupGameBoard();
                    listenToRound(roundId);
                    showToast('Selection ended. Spectating...');
                    return;
                }
            }
        }

        // Show card selection, wait for timer to hit 0
        showCardSelection(roundId, roundData);
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

    var playerCount = roundData.player_count || 0;
    var estimatedDerash = Math.round((playerCount || 1) * STAKE * 0.75);
    var el;
    if (el = document.getElementById('cs-stake')) el.textContent = STAKE + ' ETB';
    if (el = document.getElementById('cs-derash')) el.textContent = estimatedDerash + ' ETB';
    if (el = document.getElementById('cs-main-wallet')) el.textContent = (currentUser.balance || 0) + ' ETB';
    if (el = document.getElementById('cs-play-wallet')) el.textContent = (currentUser.play_wallet || 0) + ' ETB';
    if (el = document.getElementById('cs-preview-container')) el.classList.add('hidden');
    if (el = document.getElementById('card-select-screen')) el.classList.remove('hidden');

    // Start selection timer based on server selection_deadline
    var selectionDeadline = roundData.selection_deadline;
    if (selectionDeadline) {
        var dlMs;
        if (typeof selectionDeadline === 'object' && selectionDeadline.toDate) {
            dlMs = selectionDeadline.toDate().getTime();
        } else if (typeof selectionDeadline === 'string') {
            dlMs = new Date(selectionDeadline).getTime();
        } else if (typeof selectionDeadline === 'object' && selectionDeadline._iso) {
            dlMs = new Date(selectionDeadline._iso).getTime();
        } else if (typeof selectionDeadline === 'object' && selectionDeadline.seconds) {
            dlMs = selectionDeadline.seconds * 1000;
        } else {
            dlMs = new Date(selectionDeadline).getTime();
        }
        if (!isNaN(dlMs)) {
            startSelectionCountdown(dlMs);
        }
    }

    var grid = document.getElementById('card-select-grid');
    if (grid) grid.innerHTML = '<div class="col-span-8 text-center py-8"><div class="text-3xl mb-2 float-anim">🃏</div><p class="text-white/50 text-sm">Loading cartelas...</p></div>';

    try {
        var masterSnap = await db.collection('cartelas_master').orderBy('number').get();
        if (masterSnap.empty) {
            if (grid) grid.innerHTML = '<div class="col-span-8 text-center py-12 px-4"><div class="text-4xl mb-3">😓</div><p class="text-white/80 text-sm font-bold mb-1">No Cards Generated</p><p class="text-white/40 text-xs">Admin needs to generate cartelas first.</p></div>';
            return;
        }

        var takenSet = new Set(roundData.taken_cartelas || []);

        if (grid) grid.innerHTML = '';
        masterSnap.forEach(function(doc) {
            var d = doc.data();
            var num = d.number;
            var cell = document.createElement('div');
            cell.className = 'card-tile';
            cell.textContent = num;
            cell.dataset.num = num;

            if (takenSet.has(num)) {
                cell.classList.add('taken');
            } else {
                cell.onclick = (function(n, c) { return function() { toggleCardSelection(n, c); }; })(num, cell);
            }
            if (grid) grid.appendChild(cell);
        });

        if (roundUnsubscribe) roundUnsubscribe();
        roundUnsubscribe = db.collection('rounds').doc(roundId).onSnapshot(function(snap) {
            if (!snap.exists) return;
            var rd = snap.data();
            var nowTaken = new Set(rd.taken_cartelas || []);
            if (grid) {
                grid.querySelectorAll('.card-tile').forEach(function(cell) {
                    var n = parseInt(cell.dataset.num);
                    if (nowTaken.has(n) && !selectedCartelas.includes(n)) {
                        cell.className = 'card-tile taken';
                        cell.onclick = null;
                    }
                });
            }

            if (!listenerReady) {
                listenerReady = true;
                return;
            }

            if (rd.status === 'completed' || rd.status === 'cancelled') {
                var selectScreen = document.getElementById('card-select-screen');
                if (selectScreen && !selectScreen.classList.contains('hidden')) {
                    if (roundUnsubscribe) { roundUnsubscribe(); roundUnsubscribe = null; }
                    selectedCartelas = [];
                    myCartelas = {};
                    calledNumbers = new Set();
                    playNow();
                    return;
                }
            }

            if (rd.status === 'playing') {
                var uid = String(currentUser.id);
                if (rd.players && rd.players[uid]) {
                    document.getElementById('card-select-screen').classList.add('hidden');
                    stopSelectionCountdown();
                    navigateTo('game').then(function() {
                        loadMyCartelas(rd);
                        listenToRound(roundId);
                    });
                } else {
                    document.getElementById('card-select-screen').classList.add('hidden');
                    stopSelectionCountdown();
                    isSpectator = true;
                    navigateTo('game').then(function() {
                        setupGameBoard();
                        listenToRound(roundId);
                    });
                }
            }
        });
    } catch (err) {
        console.error('Error loading cartelas:', err);
        if (grid) grid.innerHTML = '<div class="col-span-8 text-center py-8"><p class="text-red-400 text-sm">Error: ' + err.message + '</p></div>';
    }
}

function toggleCardSelection(num, cell) {
    var idx = selectedCartelas.indexOf(num);
    if (idx > -1) {
        selectedCartelas.splice(idx, 1);
        cell.className = 'card-tile';
        cell.style.boxShadow = '';
        if (selectedCartelas.length > 0) {
            renderCardSelectPreview(selectedCartelas[selectedCartelas.length - 1]);
        } else {
            var pc = document.getElementById('cs-preview-container');
            if (pc) pc.classList.add('hidden');
        }
    } else {
        if (selectedCartelas.length >= MAX_CARTELAS) {
            showToast('Maximum ' + MAX_CARTELAS + ' cartelas!');
            return;
        }
        var budgetMax = Math.floor((currentUser.play_wallet || 0) / STAKE);
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
    var container = document.getElementById('cs-preview-container');
    var grid = document.getElementById('cs-preview-grid');
    var title = document.getElementById('cs-preview-title');
    if (!num) {
        if (container) container.classList.add('hidden');
        return;
    }
    if (container) container.classList.remove('hidden');
    if (title) title.textContent = 'Cartela No : ' + num;
    if (grid) grid.innerHTML = '<div class="col-span-5 text-center text-xs py-2 text-gray-500 font-normal">Loading card numbers...</div>';
    try {
        var doc = await db.collection('cartelas_master').doc(String(num)).get();
        if (doc.exists) {
            var data = doc.data();
            var flat = data.cartela || [];
            if (grid) grid.innerHTML = '';
            for (var i = 0; i < 25; i++) {
                var val = flat[i];
                var cell = document.createElement('div');
                cell.className = 'py-2 rounded-lg bg-white/5 border border-white/10 text-gray-300 font-bold text-xs flex items-center justify-center';
                if (val === 0) {
                    cell.innerHTML = '✨';
                    cell.className = 'py-2 rounded-lg border border-emerald-500 text-white font-bold text-xs flex items-center justify-center bg-emerald-600';
                } else {
                    cell.textContent = val;
                }
                if (grid) grid.appendChild(cell);
            }
        } else {
            if (grid) grid.innerHTML = '<div class="col-span-5 text-center text-xs py-2 text-red-400 font-normal">Card numbers not found</div>';
        }
    } catch (err) {
        console.error('Error loading cartelas:', err);
        if (grid) grid.innerHTML = '<div class="col-span-8 text-center py-8"><p class="text-red-400 text-sm">Error: ' + err.message + '</p></div>';
    }

    // Socket.IO dedicated cartela pool listener for faster updates
    if (window._bingoSocket) {
        window._bingoSocket.emit('subscribe', { collection: 'rounds', doc_id: roundId });
        window._bingoSocket.on('cartela_pool', function(msg) {
            if (msg.round_id !== roundId) return;
            var nowTaken = new Set(msg.taken_cartelas || []);
            if (grid) {
                grid.querySelectorAll('.card-tile').forEach(function(cell) {
                    var n = parseInt(cell.dataset.num);
                    if (nowTaken.has(n) && !selectedCartelas.includes(n)) {
                        cell.className = 'card-tile taken';
                        cell.onclick = null;
                    }
                });
            }
            var pc = document.getElementById('cs-player-count');
            if (pc) pc.textContent = msg.player_count || 0;
        });
    }
}

function updateSelectedInfo() {
    var count = selectedCartelas.length;
    var info = document.getElementById('cs-selected-info');
    if (count > 0) {
        if (info) info.classList.remove('hidden');
        var sc = document.getElementById('cs-selected-count');
        var st = document.getElementById('cs-selected-total');
        if (sc) sc.textContent = count + '/' + MAX_CARTELAS;
        if (st) st.textContent = (count * STAKE) + ' ETB';
    } else {
        if (info) info.classList.add('hidden');
    }
}

// ==================== SPECTATOR / CANCEL ====================
function cancelCardSelect() {
    selectedCartelas = [];
    stopSelectionCountdown();
    var pc = document.getElementById('cs-preview-container');
    if (pc) pc.classList.add('hidden');
    if (roundUnsubscribe) { roundUnsubscribe(); roundUnsubscribe = null; }
    // Unsubscribe from Socket.IO rooms
    if (window._bingoSocket && currentRoundId) {
        window._bingoSocket.emit('unsubscribe', { collection: 'rounds', doc_id: currentRoundId });
        window._bingoSocket.off('cartela_pool');
    }
    var cs = document.getElementById('card-select-screen');
    if (cs) cs.classList.add('hidden');
}

async function enterSpectatorMode() {
    isSpectator = true;
    var cs = document.getElementById('card-select-screen');
    if (cs) cs.classList.add('hidden');
    stopSelectionCountdown();
    await navigateTo('game');
    setupGameBoard();
    listenToRound(currentRoundId);
    showToast('Spectating...');
}

// ==================== CONFIRM SELECTION & JOIN ROUND ====================
async function confirmSelection() {
    if (selectedCartelas.length === 0) return;
    isSpectator = false;
    showLoading('Joining round...');

    try {
        var totalCost = selectedCartelas.length * STAKE;
        var uidStr = String(currentUser.id);
        var roundRef = db.collection('rounds').doc(currentRoundId);
        var userRef = db.collection('users').doc(uidStr);

        await db.runTransaction(async function(txn) {
            var roundSnap = await txn.get(roundRef);
            var userSnap = await txn.get(userRef);
            if (!roundSnap.exists) throw new Error('Round not found.');
            var rd = roundSnap.data();
            if (rd.status !== 'selecting') throw new Error('Round already started or finished.');
            // Block join if selection timer expired and round already has players
            var dl = rd.selection_deadline;
            if (dl) {
                var dlMs;
                if (typeof dl === 'object' && dl.toDate) dlMs = dl.toDate().getTime();
                else if (typeof dl === 'string') dlMs = new Date(dl).getTime();
                else if (typeof dl === 'object' && dl._iso) dlMs = new Date(dl._iso).getTime();
                else if (typeof dl === 'object' && dl.seconds) dlMs = dl.seconds * 1000;
                else dlMs = new Date(dl).getTime();
                if (!isNaN(dlMs) && serverNow() >= dlMs) {
                    var pc = rd.player_count || 0;
                    if (pc > 0) throw new Error('Selection ended. Spectating.');
                }
            }
            if (rd.players && rd.players[uidStr]) throw new Error('Already joined.');
            var pw = userSnap.data().play_wallet || 0;
            if (pw < totalCost) throw new Error('Not enough balance.');

            txn.update(userRef, {
                play_wallet: pw - totalCost,
                is_playing: true,
                updated_at: firebase.firestore.FieldValue.serverTimestamp()
            });

            var players = rd.players || {};
            players[uidStr] = {
                cartelas: selectedCartelas,
                name: currentUser.first_name || 'Player',
                joined_at: new Date().toISOString()
            };
            var takenSet = new Set(rd.taken_cartelas || []);
            selectedCartelas.forEach(function(n) { takenSet.add(n); });

            txn.update(roundRef, {
                players: players,
                player_count: Object.keys(players).length,
                taken_cartelas: Array.from(takenSet),
            });
        });

        for (var i = 0; i < selectedCartelas.length; i++) {
            var num = selectedCartelas[i];
            var cartelaDoc = await db.collection('cartelas_master').doc(String(num)).get();
            if (cartelaDoc.exists) {
                myCartelas[num] = cartelaDoc.data().cartela;
            }
        }

        hideLoading();
        var pc = document.getElementById('cs-preview-container');
        if (pc) pc.classList.add('hidden');
        var cs = document.getElementById('card-select-screen');
        if (cs) cs.classList.add('hidden');
        stopSelectionCountdown();
        await navigateTo('game');
        setupGameBoard();
        listenToRound(currentRoundId);
        showToast('Joined! Waiting for game to start...');
    } catch (err) {
        hideLoading();
        console.error('Error joining round:', err);
        if (err.message && err.message.indexOf('Spectating') !== -1) {
            isSpectator = true;
            var cs = document.getElementById('card-select-screen');
            if (cs) cs.classList.add('hidden');
            stopSelectionCountdown();
            await navigateTo('game');
            setupGameBoard();
            listenToRound(currentRoundId);
            showToast('Selection ended. Spectating...');
        } else {
            showToast('Error: ' + err.message);
        }
    }
}

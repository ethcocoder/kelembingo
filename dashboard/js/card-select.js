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
            _previewCache = {};
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
                var pc = roundData.player_count || 0;
                if (pc > 0) {
                    isSpectator = true;
                    await navigateTo('game');
                    setupGameBoard();
                    listenToRound(roundId);
                    showToast('Selection ended. Spectating...');
                    return;
                }
                // Stale round with no players — mark completed and create new round
                db.collection('rounds').doc(roundId).update({
                    status: 'completed',
                    winners: [],
                    winner_name: 'No players',
                    prize_per_winner: 0,
                    admin_profit: 0,
                    payout_processed: true,
                    completed_at: firebase.firestore.FieldValue.serverTimestamp()
                }).catch(function() {});
                hideLoading();
                playNow();
                return;
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
    var estimatedDerash = Math.round(playerCount * STAKE * 0.75);
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
                var changed = false;
                grid.querySelectorAll('.card-tile').forEach(function(cell) {
                    var n = parseInt(cell.dataset.num);
                    if (nowTaken.has(n)) {
                        if (!cell.classList.contains('taken')) {
                            cell.className = 'card-tile taken';
                            cell.onclick = null;
                            var selIdx = selectedCartelas.indexOf(n);
                            if (selIdx > -1) {
                                selectedCartelas.splice(selIdx, 1);
                                changed = true;
                            }
                        }
                    }
                });
                if (changed) {
                    updateSelectedInfo();
                    renderAllPreviews();
                }
            }

            if (!listenerReady) {
                listenerReady = true;
            }

            var livePlayerCount = rd.player_count || 0;
            var liveDerash = Math.round(livePlayerCount * STAKE * 0.75);
            var derashEl;
            if (derashEl = document.getElementById('cs-derash')) derashEl.textContent = liveDerash + ' ETB';

            if (rd.status === 'completed' || rd.status === 'cancelled') {
                var selectScreen = document.getElementById('card-select-screen');
                if (selectScreen && !selectScreen.classList.contains('hidden')) {
                    if (roundUnsubscribe) { roundUnsubscribe(); roundUnsubscribe = null; }
                    stopSelectionCountdown();
                    selectedCartelas = [];
                    myCartelas = {};
                    calledNumbers = new Set();
                    _previewCache = {};
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
    }
    updateSelectedInfo();
    renderAllPreviews();
}

var _previewCache = {};
async function renderAllPreviews() {
    var container = document.getElementById('cs-preview-container');
    var cardsDiv = document.getElementById('cs-preview-cards');
    if (!container || !cardsDiv) return;

    if (selectedCartelas.length === 0) {
        container.classList.add('hidden');
        return;
    }
    container.classList.remove('hidden');
    cardsDiv.innerHTML = '';

    for (var i = 0; i < selectedCartelas.length; i++) {
        var num = selectedCartelas[i];
        var card = document.createElement('div');
        card.className = 'preview-card' + (i === selectedCartelas.length - 1 ? ' active' : '');
        card.dataset.num = num;
        card.onclick = (function(n) { return function() {
            document.querySelectorAll('.preview-card').forEach(function(c) { c.classList.remove('active'); });
            this.classList.add('active');
        }; })(num);

        var title = document.createElement('div');
        title.className = 'preview-card-title';
        title.textContent = '#' + num;
        card.appendChild(title);

        var headers = document.createElement('div');
        headers.className = 'preview-card-headers';
        var letters = [['B','#3B82F6'],['I','#8B5CF6'],['N','#D946EF'],['G','#10B981'],['O','#F97316']];
        for (var h = 0; h < 5; h++) {
            var sp = document.createElement('span');
            sp.textContent = letters[h][0];
            sp.style.background = letters[h][1];
            headers.appendChild(sp);
        }
        card.appendChild(headers);

        var grid = document.createElement('div');
        grid.className = 'preview-card-grid';
        grid.id = 'preview-grid-' + num;
        card.appendChild(grid);
        cardsDiv.appendChild(card);

        if (_previewCache[num]) {
            _renderPreviewGrid(grid, _previewCache[num]);
        } else {
            grid.innerHTML = '<div class="pc-cell" style="grid-column:span 5;color:#666">...</div>';
            _loadPreviewCard(num, grid);
        }
    }
}

async function _loadPreviewCard(num, grid) {
    try {
        var doc = await db.collection('cartelas_master').doc(String(num)).get();
        if (doc.exists) {
            var flat = doc.data().cartela || [];
            _previewCache[num] = flat;
            if (grid.parentElement) _renderPreviewGrid(grid, flat);
        }
    } catch (e) {}
}

function _renderPreviewGrid(grid, flat) {
    grid.innerHTML = '';
    for (var i = 0; i < 25; i++) {
        var val = flat[i];
        var cell = document.createElement('div');
        cell.className = 'pc-cell' + (val === 0 ? ' free' : '');
        cell.textContent = val === 0 ? '★' : val;
        grid.appendChild(cell);
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
        var msg = err.message || '';
        if (msg.indexOf('Spectating') !== -1 || msg.indexOf('already started') !== -1 || msg.indexOf('finished') !== -1) {
            showToast('Round ended. Finding new game...');
            if (roundUnsubscribe) { roundUnsubscribe(); roundUnsubscribe = null; }
            playNow();
        } else {
            showToast('Error: ' + msg);
        }
    }
}

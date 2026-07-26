// ==================== HELPERS ====================
var _originalPlayWallet = 0;

function calcDerash(existingCartelas, mySelections, stake) {
    var totalCartelas = (existingCartelas || 0) + (mySelections || 0);
    if (totalCartelas < 1) return 0;
    return Math.round(totalCartelas * (stake || 10) * 0.75 * 10) / 10;
}

// ==================== PLAY NOW ====================
var _playNowRunning = false;
async function playNow(stake) {
    if (_playNowRunning) return;
    _playNowRunning = true;
    if (!currentUser) { showToast('Loading user data...'); _playNowRunning = false; return; }
    stake = stake || currentStake || 10;
    if (VALID_STAKES.indexOf(stake) === -1) stake = 10;
    currentStake = stake;
    var pw = currentUser.play_wallet || 0;
    var hasBalance = pw >= stake;

    showLoading('Finding game...');
    try {
        var roundSnap = await db.collection('rounds')
            .where('status', 'in', ['selecting', 'playing'])
            .where('stake', '==', stake)
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
                stake: stake,
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
            var pc = roundData.player_count || 0;
            if (pc <= 0) {
                // 0-player round in playing state — cancel and restart
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
                playNow(stake);
                return;
            }
            if (roundData.players && roundData.players[String(currentUser.id)]) {
                hideLoading();
                showToast('Rejoining current game!');
                await navigateTo('game');
                var freshSnap = await db.collection('rounds').doc(roundId).get();
                var freshData = freshSnap.exists ? freshSnap.data() : roundData;
                await loadMyCartelas(freshData);
                listenToRound(roundId);
                return;
            } else {
                // Spectator mode — only for rounds with actual players
                hideLoading();
                isSpectator = true;
                await navigateTo('game');
                var freshSpecSnap = await db.collection('rounds').doc(roundId).get();
                var freshSpecData = freshSpecSnap.exists ? freshSpecSnap.data() : roundData;
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
            var freshJoinSnap = await db.collection('rounds').doc(roundId).get();
            var freshJoinData = freshJoinSnap.exists ? freshJoinSnap.data() : roundData;
            await loadMyCartelas(freshJoinData);
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
                playNow(currentStake);
                return;
            }
        }

        // Show card selection, wait for timer to hit 0
        showCardSelection(roundId, roundData);
    } catch (err) {
        hideLoading();
        console.error('Error finding round:', err);
        showToast('Error: ' + err.message);
    } finally {
        _playNowRunning = false;
    }
}

// ==================== CARD SELECTION ====================
async function showCardSelection(roundId, roundData) {
    _stopRoundPolling();
    selectedCartelas = [];
    _originalPlayWallet = currentUser.play_wallet || 0;
    listenerReady = false;
    updateSelectedInfo();

    var playerCount = roundData.player_count || 0;
    _lastKnownPlayerCount = playerCount;
    var estimatedETB = calcDerash(playerCount, selectedCartelas.length, currentStake);
    var el;
    if (el = document.getElementById('cs-stake')) el.textContent = currentStake + ' ETB';
    if (el = document.getElementById('cs-derash')) el.textContent = estimatedETB + ' ETB';
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

        var takenSet = new Set((roundData.taken_cartelas || []).map(function(v) { return parseInt(v) || v; }));

        if (grid) grid.innerHTML = '';
        masterSnap.forEach(function(doc) {
            var d = doc.data();
            var num = d.number;
            var cell = document.createElement('div');
            cell.className = 'card-tile';
            cell.textContent = num;
            cell.dataset.num = num;

            if (takenSet.has(num) || takenSet.has(String(num))) {
                cell.classList.add('taken', 'taken-flash');
                cell.onclick = (function(n) { return function() { showToast('Card #' + n + ' is already taken by another player'); }; })(num);
            } else {
                cell.onclick = (function(n, c) { return function() { toggleCardSelection(n, c); }; })(num, cell);
            }
            if (grid) grid.appendChild(cell);
        });

        if (roundUnsubscribe) roundUnsubscribe();
        roundUnsubscribe = db.collection('rounds').doc(roundId).onSnapshot(function(snap) {
            if (!snap.exists) return;
            var rd = snap.data();
            var rawTaken = rd.taken_cartelas || [];
            var nowTaken = new Set(rawTaken.map(function(v) { return parseInt(v) || v; }));
            if (grid) {
                var changed = false;
                grid.querySelectorAll('.card-tile').forEach(function(cell) {
                    var n = parseInt(cell.dataset.num);
                    if (nowTaken.has(n) || nowTaken.has(String(n))) {
                        if (!cell.classList.contains('taken')) {
                            cell.className = 'card-tile taken taken-flash';
                            cell.onclick = (function(num) { return function() { showToast('Card #' + num + ' is already taken by another player'); }; })(n);
                            var selIdx = selectedCartelas.indexOf(n);
                            if (selIdx > -1) {
                                selectedCartelas.splice(selIdx, 1);
                                changed = true;
                                showToast('Card #' + n + ' was taken by another player!');
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
            _lastKnownPlayerCount = livePlayerCount;
            var liveETB = calcDerash(livePlayerCount, selectedCartelas.length, currentStake);
    var derashEl;
    if (derashEl = document.getElementById('cs-derash')) derashEl.textContent = liveETB + ' ETB';

            if (rd.status === 'completed' || rd.status === 'cancelled') {
                var selectScreen = document.getElementById('card-select-screen');
                if (selectScreen && selectScreen.classList.contains('hidden')) return;
                if (selectScreen && !selectScreen.classList.contains('hidden')) {
                    _stopRoundPolling();
                    if (roundUnsubscribe) { roundUnsubscribe(); roundUnsubscribe = null; }
                    stopSelectionCountdown();
                    selectedCartelas = [];
                    myCartelas = {};
                    calledNumbers = new Set();
                    _previewCache = {};
                    playNow(currentStake);
                    return;
                }
            }

            if (rd.status === 'playing') {
                var cs = document.getElementById('card-select-screen');
                if (cs && cs.classList.contains('hidden')) return;
                _stopRoundPolling();
                var livePC = rd.player_count || 0;
                if (livePC <= 0) {
                    // 0-player round started playing — cancel and restart
                    if (roundUnsubscribe) { roundUnsubscribe(); roundUnsubscribe = null; }
                    stopSelectionCountdown();
                    selectedCartelas = [];
                    myCartelas = {};
                    calledNumbers = new Set();
                    _previewCache = {};
                    db.collection('rounds').doc(roundId).update({
                        status: 'completed',
                        winners: [],
                        winner_name: 'No players',
                        prize_per_winner: 0,
                        admin_profit: 0,
                        payout_processed: true,
                        completed_at: firebase.firestore.FieldValue.serverTimestamp()
                    }).catch(function() {});
                    playNow(currentStake);
                    return;
                }
                var uid = String(currentUser.id);
                if (rd.players && rd.players[uid]) {
                    document.getElementById('card-select-screen').classList.add('hidden');
                    stopSelectionCountdown();
                    navigateTo('game').then(function() {
                        loadMyCartelas(rd);
                        listenToRound(roundId);
                    });
                } else {
                    // User is in a round with players but has no cards — spectate
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

        // Polling fallback for taken cartelas
        _startRoundPolling(roundId, grid);

    } catch (err) {
        console.error('Error loading cartelas:', err);
        if (grid) grid.innerHTML = '<div class="col-span-8 text-center py-8"><p class="text-red-400 text-sm">Error: ' + err.message + '</p></div>';
    }
}

var _roundPollTimer = null;
function _stopRoundPolling() {
    if (_roundPollTimer) { clearInterval(_roundPollTimer); _roundPollTimer = null; }
}
async function _pollRound(roundId, grid) {
    try {
        if (!grid || !grid.parentNode) { _stopRoundPolling(); return; }
        var doc = await db.collection('rounds').doc(roundId).get();
        if (!doc.exists) return;
        var rd = doc.data();

        // 1) Handle status transitions (completed/playing)
        if (rd.status === 'completed' || rd.status === 'cancelled') {
            var sc = document.getElementById('card-select-screen');
            if (sc && !sc.classList.contains('hidden')) {
                _stopRoundPolling();
                if (roundUnsubscribe) { roundUnsubscribe(); roundUnsubscribe = null; }
                stopSelectionCountdown();
                selectedCartelas = [];
                myCartelas = {};
                calledNumbers = new Set();
                _previewCache = {};
                playNow(currentStake);
            }
            return;
        }
        if (rd.status === 'playing') {
            var cs = document.getElementById('card-select-screen');
            if (cs && !cs.classList.contains('hidden')) {
                _stopRoundPolling();
                stopSelectionCountdown();
                var livePC = rd.player_count || 0;
                if (livePC <= 0) {
                    if (roundUnsubscribe) { roundUnsubscribe(); roundUnsubscribe = null; }
                    selectedCartelas = [];
                    myCartelas = {};
                    calledNumbers = new Set();
                    _previewCache = {};
                    db.collection('rounds').doc(roundId).update({
                        status: 'completed', winners: [], winner_name: 'No players',
                        prize_per_winner: 0, admin_profit: 0, payout_processed: true,
                        completed_at: firebase.firestore.FieldValue.serverTimestamp()
                    }).catch(function() {});
                    playNow(currentStake);
                } else {
                    var uid = String(currentUser.id);
                    cs.classList.add('hidden');
                    if (rd.players && rd.players[uid]) {
                        navigateTo('game').then(function() { loadMyCartelas(rd); listenToRound(roundId); });
                    } else {
                        isSpectator = true;
                        navigateTo('game').then(function() { setupGameBoard(); listenToRound(roundId); });
                    }
                }
            }
            return;
        }

        // 2) Update taken cartelas on the grid
        var rawTaken = rd.taken_cartelas || [];
        var nowTaken = new Set(rawTaken.map(function(v) { return parseInt(v) || v; }));
        var changed = false;
        grid.querySelectorAll('.card-tile').forEach(function(cell) {
            var n = parseInt(cell.dataset.num);
            if (nowTaken.has(n) || nowTaken.has(String(n))) {
                if (!cell.classList.contains('taken')) {
                    cell.classList.add('taken', 'taken-flash');
                    cell.onclick = function() { showToast('Card #' + n + ' is already taken by another player'); };
                    var idx = selectedCartelas.indexOf(n);
                    if (idx > -1) {
                        selectedCartelas.splice(idx, 1);
                        changed = true;
                    }
                }
            }
        });
        if (changed) {
            updateSelectedInfo();
            renderAllPreviews();
        }

        // 3) Update player count / derash
        _lastKnownPlayerCount = rd.player_count || 0;
        var liveETB = calcDerash(_lastKnownPlayerCount, selectedCartelas.length, currentStake);
        var derEl = document.getElementById('cs-derash');
        if (derEl) derEl.textContent = liveETB + ' ETB';
    } catch(e) {}
}
function _startRoundPolling(roundId, grid) {
    _stopRoundPolling();
    if (!roundId || !grid) return;
    _pollRound(roundId, grid); // immediate first poll
    _roundPollTimer = setInterval(function() { _pollRound(roundId, grid); }, 1500);
        try {
            if (!grid || !grid.parentNode) { _stopRoundPolling(); return; }
            var doc = await db.collection('rounds').doc(roundId).get();
            if (!doc.exists) return;
            var rd = doc.data();

            // 1) Handle status transitions (completed/playing)
            if (rd.status === 'completed' || rd.status === 'cancelled') {
                var sc = document.getElementById('card-select-screen');
                if (sc && !sc.classList.contains('hidden')) {
                    _stopRoundPolling();
                    if (roundUnsubscribe) { roundUnsubscribe(); roundUnsubscribe = null; }
                    stopSelectionCountdown();
                    selectedCartelas = [];
                    myCartelas = {};
                    calledNumbers = new Set();
                    _previewCache = {};
                    playNow(currentStake);
                }
                return;
            }
            if (rd.status === 'playing') {
                var cs = document.getElementById('card-select-screen');
                if (cs && !cs.classList.contains('hidden')) {
                    _stopRoundPolling();
                    stopSelectionCountdown();
                    var livePC = rd.player_count || 0;
                    if (livePC <= 0) {
                        if (roundUnsubscribe) { roundUnsubscribe(); roundUnsubscribe = null; }
                        selectedCartelas = [];
                        myCartelas = {};
                        calledNumbers = new Set();
                        _previewCache = {};
                        db.collection('rounds').doc(roundId).update({
                            status: 'completed', winners: [], winner_name: 'No players',
                            prize_per_winner: 0, admin_profit: 0, payout_processed: true,
                            completed_at: firebase.firestore.FieldValue.serverTimestamp()
                        }).catch(function() {});
                        playNow(currentStake);
                    } else {
                        var uid = String(currentUser.id);
                        cs.classList.add('hidden');
                        if (rd.players && rd.players[uid]) {
                            navigateTo('game').then(function() { loadMyCartelas(rd); listenToRound(roundId); });
                        } else {
                            isSpectator = true;
                            navigateTo('game').then(function() { setupGameBoard(); listenToRound(roundId); });
                        }
                    }
                }
                return;
            }

            // 2) Update taken cartelas on the grid
            var rawTaken = rd.taken_cartelas || [];
            var nowTaken = new Set(rawTaken.map(function(v) { return parseInt(v) || v; }));
            var changed = false;
            grid.querySelectorAll('.card-tile').forEach(function(cell) {
                var n = parseInt(cell.dataset.num);
                if (nowTaken.has(n) || nowTaken.has(String(n))) {
                    if (!cell.classList.contains('taken')) {
                        cell.classList.add('taken', 'taken-flash');
                        cell.onclick = function() { showToast('Card #' + n + ' is already taken by another player'); };
                        var idx = selectedCartelas.indexOf(n);
                        if (idx > -1) {
                            selectedCartelas.splice(idx, 1);
                            changed = true;
                        }
                    }
                }
            });
            if (changed) {
                updateSelectedInfo();
                renderAllPreviews();
            }

            // 3) Update player count / derash
            _lastKnownPlayerCount = rd.player_count || 0;
            var liveETB = calcDerash(_lastKnownPlayerCount, selectedCartelas.length, currentStake);
            var derEl = document.getElementById('cs-derash');
            if (derEl) derEl.textContent = liveETB + ' ETB';
        } catch(e) {}
    }, 1500);
}

var _confirming = false;
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
        var budgetMax = Math.floor((currentUser.play_wallet || 0) / currentStake);
        if (selectedCartelas.length >= budgetMax) {
            showToast('Not enough balance for more cards!');
            return;
        }
        selectedCartelas.push(num);
        cell.className = 'card-tile selected';
    }
    updateSelectedInfo();
    schedulePreviewRender();
}

var _previewDebounce = null;
function schedulePreviewRender() {
    if (_previewDebounce) clearTimeout(_previewDebounce);
    _previewDebounce = setTimeout(function() {
        _previewDebounce = null;
        renderAllPreviews();
    }, 150);
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
        if (st) st.textContent = (count * currentStake) + ' ETB';
    } else {
        if (info) info.classList.add('hidden');
    }

    // Update PLAY WALLET to show pending deduction
    var pendingCost = count * currentStake;
    var originalBalance = _originalPlayWallet || (currentUser.play_wallet || 0);
    var remaining = originalBalance - pendingCost;
    if (remaining < 0) remaining = 0;
    var pwEl = document.getElementById('cs-play-wallet');
    if (pwEl) {
        pwEl.textContent = remaining + ' ETB';
        if (pendingCost > 0 && remaining < currentStake) {
            pwEl.style.color = '#EF4444';
        } else {
            pwEl.style.color = '';
        }
    }

    // Update DERASH: total pool = all cartelas * stake * 0.75
    var liveDerashEl = document.getElementById('cs-derash');
    if (liveDerashEl) {
        var baseCount = _lastKnownPlayerCount || 0;
        var totalCartelas = baseCount + count;
        var totalPool = totalCartelas * currentStake * 0.75;
        liveDerashEl.textContent = Math.round(totalPool * 10) / 10 + ' ETB';
    }

    // Update per-player DERASH: what this player would win
    var perPlayerEl = document.getElementById('cs-per-player');
    if (perPlayerEl) {
        var baseCount2 = _lastKnownPlayerCount || 0;
        var totalCartelas2 = baseCount2 + count;
        var totalPool2 = totalCartelas2 * currentStake * 0.75;
        // Assume at least 1 winner (this player), split by estimated winners
        var perPlayer = count > 0 ? Math.round(totalPool2 * 10) / 10 : 0;
        perPlayerEl.textContent = perPlayer + ' ETB';
    }
}

// ==================== SPECTATOR / CANCEL ====================
function cancelCardSelect() {
    _stopRoundPolling();
    selectedCartelas = [];
    _originalPlayWallet = 0;
    stopSelectionCountdown();
    var pc = document.getElementById('cs-preview-container');
    if (pc) pc.classList.add('hidden');
    var pwEl = document.getElementById('cs-play-wallet');
    if (pwEl) pwEl.style.color = '';
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
    _stopRoundPolling();
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
    if (_confirming) return;
    _confirming = true;
    if (_confirmDebounce) { clearTimeout(_confirmDebounce); _confirmDebounce = null; }
    
    // Hard client-side validation
    var currentRoundData = null;
    try {
        var roundDoc = await db.collection('rounds').doc(currentRoundId).get();
        if (roundDoc.exists) currentRoundData = roundDoc.data();
    } catch(e) {}
    
    if (currentRoundData) {
        var takenNow = new Set((currentRoundData.taken_cartelas || []).map(function(v) { return parseInt(v) || v; }));
        for (var i = 0; i < selectedCartelas.length; i++) {
            var cn = selectedCartelas[i];
            if (takenNow.has(cn) || takenNow.has(String(cn))) {
                showToast('Card #' + cn + ' was just taken! Removing...');
                selectedCartelas.splice(i, 1);
                i--;
            }
        }
        if (selectedCartelas.length === 0) {
            showToast('All selected cards are taken. Pick different cards.');
            return;
        }
        var uniqueCheck = {};
        for (var j = 0; j < selectedCartelas.length; j++) {
            if (uniqueCheck[selectedCartelas[j]]) {
                showToast('Duplicate card detected. Please reselect.');
                selectedCartelas = [];
                return;
            }
            uniqueCheck[selectedCartelas[j]] = true;
        }
    }
    
    isSpectator = false;
    showLoading('Joining round...');

    try {
        var apiBase = window.API_BASE || window.location.origin || (window.location.protocol + '//' + window.location.host);
        var res = await fetch(apiBase + '/api/rounds/' + currentRoundId + '/join', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: currentUser.id,
                cartela_numbers: selectedCartelas,
                user_name: currentUser.first_name || 'Player'
            })
        });

        var data = await res.json();
        if (!res.ok) {
            throw new Error(data.detail || data.error || 'Error joining round');
        }

        for (var i = 0; i < selectedCartelas.length; i++) {
            var num = selectedCartelas[i];
            if (_previewCache[num]) {
                myCartelas[num] = _previewCache[num];
            } else {
                var cartelaDoc = await db.collection('cartelas_master').doc(String(num)).get();
                if (cartelaDoc.exists) {
                    myCartelas[num] = cartelaDoc.data().cartela;
                    _previewCache[num] = cartelaDoc.data().cartela;
                }
            }
        }

        hideLoading();
        var pc = document.getElementById('cs-preview-container');
        if (pc) pc.classList.add('hidden');
        var cs = document.getElementById('card-select-screen');
        if (cs) cs.classList.add('hidden');
        _stopRoundPolling();
        stopSelectionCountdown();
        if (roundUnsubscribe) { roundUnsubscribe(); roundUnsubscribe = null; }
        await navigateTo('game');
        setupGameBoard();
        listenToRound(currentRoundId);
        showToast('Joined! Waiting for game to start...');
    } catch (err) {
        hideLoading();
        console.error('Error joining round:', err);
        var msg = err.message || '';
        if (msg.indexOf('Spectating') !== -1 || msg.indexOf('already started') !== -1 || msg.indexOf('finished') !== -1) {
            showToast('Round ended just before your pick was confirmed. Finding new game...');
            if (roundUnsubscribe) { roundUnsubscribe(); roundUnsubscribe = null; }
            playNow(currentStake);
        } else {
            showToast('Error: ' + msg);
        }
    }
    _confirming = false;
}

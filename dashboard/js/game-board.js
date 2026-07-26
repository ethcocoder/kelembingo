// ==================== GAME BOARD ====================
var _announceTimeout = null;
function setupGameBoard() {
    const nums = Object.keys(myCartelas).map(Number);
    calledNumbers = new Set();
    _bingoDetected = false;
    stopGameCountdown();

    var el;
    if (el = document.getElementById('game-id-display')) el.textContent = '#' + (currentRoundId || '---').substring(0, 6);
    if (el = document.getElementById('game-stake')) el.textContent = currentStake + ' ETB';
    if (el = document.getElementById('game-called-count')) el.textContent = '0';
    if (el = document.getElementById('game-timer')) el.textContent = '--';
    if (el = document.getElementById('game-players')) el.textContent = '...';
    if (el = document.getElementById('game-derash')) el.textContent = '--';
    if (el = document.getElementById('game-countdown')) el.classList.add('hidden');

    // Show/hide spectator message vs cartela area
    var spectatorMsg = document.getElementById('spectator-message');
    var cartelaArea = document.getElementById('cartela-area');
    var wrap1 = document.getElementById('cartela-wrap-1');
    var wrap2 = document.getElementById('cartela-wrap-2');

    if (spectatorMsg && cartelaArea) {
        if (nums.length === 0 || isSpectator) {
            spectatorMsg.classList.remove('hidden');
            cartelaArea.classList.add('hidden');
        } else {
            spectatorMsg.classList.add('hidden');
            cartelaArea.classList.remove('hidden');
        }
    }

    buildMasterGrid();

    // Reset number announce
    var numAnnounce = document.getElementById('number-announce');
    if (numAnnounce) numAnnounce.classList.add('hidden');

    if (wrap1) {
        if (nums.length > 0) {
            wrap1.classList.remove('hidden');
            var cn1 = document.getElementById('cartela-number-1');
            if (cn1) cn1.textContent = nums[0];
            buildCartelaGrid('cartela-grid-1', myCartelas[nums[0]]);
        } else {
            wrap1.classList.add('hidden');
        }
    }
    if (wrap2) {
        if (nums.length >= 2) {
            wrap2.classList.remove('hidden');
            var cn2 = document.getElementById('cartela-number-2');
            if (cn2) cn2.textContent = nums[1];
            buildCartelaGrid('cartela-grid-2', myCartelas[nums[1]]);
        } else {
            wrap2.classList.add('hidden');
        }
    }

    var calledTags = document.getElementById('called-tags');
    if (calledTags) calledTags.innerHTML = '';
}

// ==================== GAME COUNTDOWN (5s between calls) ====================
function startGameCountdown(nextMs) {
    stopGameCountdown();
    gameCountdownInterval = setInterval(function() {
        var remaining = Math.max(0, Math.ceil((nextMs - serverNow()) / 1000));
        var timerEl = document.getElementById('game-timer');
        if (timerEl) {
            timerEl.textContent = remaining > 0 ? remaining + 's' : 'GO!';
            if (remaining <= 3 && remaining > 0) {
                timerEl.style.color = '#EF4444';
                timerEl.style.fontWeight = '900';
            } else {
                timerEl.style.color = '';
                timerEl.style.fontWeight = '';
            }
        }
        if (remaining <= 0) {
            stopGameCountdown();
        }
    }, 200);
}

function stopGameCountdown() {
    if (gameCountdownInterval) {
        clearInterval(gameCountdownInterval);
        gameCountdownInterval = null;
    }
}

// ==================== SELECTION COUNTDOWN (35s) ====================
function startSelectionCountdown(deadlineMs) {
    stopSelectionCountdown();
    selectionCountdownInterval = setInterval(function() {
        var remaining = Math.max(0, Math.ceil((deadlineMs - serverNow()) / 1000));
        var el = document.getElementById('cs-timer');
        if (el) el.textContent = remaining > 0 ? remaining + 's' : 'Starting...';
        var bar = document.getElementById('cs-timer-bar');
        if (bar) {
            var pct = Math.max(0, (remaining / SELECTION_DURATION) * 100);
            bar.style.width = pct + '%';
            if (remaining <= 10 && remaining > 0) {
                bar.style.background = 'linear-gradient(90deg, #EF4444, #F87171)';
            }
        }
        if (remaining <= 0) {
            stopSelectionCountdown();
            if (selectedCartelas.length > 0 && typeof confirmSelection === 'function') {
                confirmSelection();
            } else {
                var cs = document.getElementById('card-select-screen');
                if (cs && !cs.classList.contains('hidden')) {
                    cs.classList.add('hidden');
                    playNow(currentStake);
                }
            }
        }
    }, 200);
}

function stopSelectionCountdown() {
    if (selectionCountdownInterval) {
        clearInterval(selectionCountdownInterval);
        selectionCountdownInterval = null;
    }
}

function buildMasterGrid() {
    var grid = document.getElementById('master-grid');
    if (!grid) return;
    grid.innerHTML = '';
    var letters = ['b', 'i', 'n', 'g', 'o'];
    for (var row = 0; row < 15; row++) {
        for (var col = 0; col < 5; col++) {
            var num = col * 15 + row + 1;
            var cell = document.createElement('div');
            cell.className = 'master-cell letter-' + letters[col] + ' text-center rounded font-semibold transition-all flex items-center justify-center';
            cell.textContent = num;
            cell.id = 'master-' + num;
            grid.appendChild(cell);
        }
    }
}

function buildCartelaGrid(gridId, flat) {
    var grid = document.getElementById(gridId);
    if (!grid) return;
    grid.innerHTML = '';
    if (!flat || flat.length < 25) return;
    for (var i = 0; i < 25; i++) {
        var num = flat[i];
        var cell = document.createElement('div');
        cell.className = 'cartela-cell text-[10px] font-bold text-center py-1.5 rounded cursor-pointer transition-all';
        cell.dataset.num = num;
        if (num === 0) {
            cell.textContent = '★';
            cell.classList.add('free-space');
            cell.classList.add('marked');
        } else {
            cell.textContent = num;
            if (calledNumbers.has(num)) {
                markCartelaCell(cell, num);
            }
            cell.onclick = (function(c, n) { return function() { manualMark(c, n); }; })(cell, num);
        }
        grid.appendChild(cell);
    }
}

function markCartelaCell(cell, num) {
    cell.classList.add('marked');
    cell.style.background = 'linear-gradient(135deg, #10B981, #059669)';
    cell.style.color = '#fff';
    cell.style.transform = 'scale(1.05)';
    cell.style.boxShadow = '0 0 8px rgba(16,185,129,0.3)';
    setTimeout(function() { cell.style.transform = ''; }, 200);
}

function manualMark(cell, num) {
    if (!calledNumbers.has(num)) {
        showToast('Number ' + num + ' not called yet!');
        return;
    }
    if (cell.classList.contains('marked')) return;
    markCartelaCell(cell, num);
    playMarkSound();
    // Sync marked numbers to server
    _syncMarkedToServer();
}

var _markedNumbers = new Set();
var _syncDebounce = null;

function _syncMarkedToServer() {
    // Collect all marked numbers from all cartelas
    _markedNumbers.clear();
    document.querySelectorAll('.cartela-cell.marked').forEach(function(cell) {
        var n = parseInt(cell.dataset.num);
        if (n > 0) _markedNumbers.add(n);
    });
    
    // Debounce sync to server
    if (_syncDebounce) clearTimeout(_syncDebounce);
    _syncDebounce = setTimeout(function() {
        _syncDebounce = null;
        _sendMarksToServer();
    }, 500);
}

async function _sendMarksToServer() {
    if (!currentUser || !currentRoundId) return;
    try {
        var apiBase = window.API_BASE || window.location.origin || (window.location.protocol + '//' + window.location.host);
        await fetch(apiBase + '/api/rounds/' + currentRoundId + '/sync-marks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: currentUser.id,
                marked_numbers: Array.from(_markedNumbers)
            })
        });
    } catch(e) {
        console.error('Failed to sync marks:', e);
    }
}

function highlightMasterNumber(num, isLast) {
    var cell = document.getElementById('master-' + num);
    if (!cell) return;
    var letter = getNumberLetter(num);
    var color = getLetterColor(letter);
    cell.style.backgroundColor = color;
    cell.style.color = '#fff';
    cell.classList.add('called');
    if (isLast) {
        document.querySelectorAll('.master-cell.last-called').forEach(function(el) {
            el.classList.remove('last-called');
        });
        cell.classList.add('last-called');
    }
}

function addCalledNumberTag(num) {
    var strip = document.getElementById('called-tags');
    if (!strip) return;
    var letter = getNumberLetter(num);
    var letterLower = letter.toLowerCase();
    var el = document.createElement('span');
    el.className = 'called-tag tag-' + letterLower;
    el.innerHTML = '<div class="tag-letter" style="color:inherit">' + letter + '</div>' +
                   '<div class="tag-number">' + num + '</div>';
    strip.appendChild(el);
}

function autoMarkAllCartelas(num) {
    if (!autoMarkEnabled) return;
    var gridIds = ['cartela-grid-1', 'cartela-grid-2'];
    var marked = false;
    for (var gi = 0; gi < gridIds.length; gi++) {
        var grid = document.getElementById(gridIds[gi]);
        if (!grid) continue;
        grid.querySelectorAll('.cartela-cell').forEach(function(cell) {
            if (parseInt(cell.dataset.num) === num && !cell.classList.contains('marked')) {
                markCartelaCell(cell, num);
                marked = true;
            }
        });
    }
    if (marked) _syncMarkedToServer();
}

function toggleAutoMark() {
    autoMarkEnabled = !autoMarkEnabled;
    var toggle = document.getElementById('auto-toggle');
    if (toggle) toggle.classList.toggle('on', autoMarkEnabled);
    showToast(autoMarkEnabled ? 'Auto-mark ON' : 'Auto-mark OFF');
    if (autoMarkEnabled) {
        calledNumbers.forEach(function(num) { autoMarkAllCartelas(num); });
    }
}

// ==================== LISTEN TO ROUND (real-time) ====================
function listenToRound(roundId) {
    if (roundUnsubscribe) roundUnsubscribe();

    roundUnsubscribe = db.collection('rounds').doc(roundId).onSnapshot(function(snap) {
        if (!snap.exists) return;
        var data = snap.data();

        var elPlayers = document.getElementById('game-players');
        var elDerash = document.getElementById('game-derash');
        var elCalledCount = document.getElementById('game-called-count');
        var elCountdown = document.getElementById('game-countdown');

        var playerCount = data.player_count || 0;
        var roundStake = data.stake || currentStake || 10;
        var totalPool = Math.round(playerCount * roundStake * 0.75 * 10) / 10;
        var numWinners = (data.winners || []).length;
        var perPlayer = numWinners > 0 ? Math.round(totalPool / numWinners * 10) / 10 : totalPool;
        
        if (elPlayers) elPlayers.textContent = playerCount;
        if (elDerash) elDerash.textContent = totalPool + ' ETB';
        if (elCalledCount) elCalledCount.textContent = (data.called_numbers || []).length;
        
        // Show per-player DERASH
        var elPerPlayer = document.getElementById('game-per-player');
        if (elPerPlayer) {
            if (numWinners > 0) {
                elPerPlayer.textContent = perPlayer + ' ETB each';
            } else {
                elPerPlayer.textContent = totalPool + ' ETB';
            }
        }

        if (data.status === 'selecting') {
            if (elCountdown) {
                elCountdown.classList.remove('hidden');
                elCountdown.textContent = 'Waiting for players...';
            }
        } else if (data.status === 'playing') {
            if (elCountdown) elCountdown.classList.add('hidden');

            if (playerCount <= 0) {
                if (roundUnsubscribe) { roundUnsubscribe(); roundUnsubscribe = null; }
                isSpectator = false;
                showToast('No players in this round. Starting new game...');
                setTimeout(async function() { await playNow(currentStake); }, 1500);
                return;
            }

            var nextAt = data.next_number_at;
            if (nextAt) {
                var nextMs;
                if (typeof nextAt === 'object' && nextAt.toDate) {
                    nextMs = nextAt.toDate().getTime();
                } else if (typeof nextAt === 'string') {
                    nextMs = new Date(nextAt).getTime();
                } else if (typeof nextAt === 'object' && nextAt._iso) {
                    nextMs = new Date(nextAt._iso).getTime();
                } else if (typeof nextAt === 'object' && nextAt.seconds) {
                    nextMs = nextAt.seconds * 1000;
                } else {
                    nextMs = new Date(nextAt).getTime();
                }
                if (!isNaN(nextMs)) {
                    startGameCountdown(nextMs);
                }
            }

            var called = data.called_numbers || [];
            var prevCount = calledNumbers.size;
            for (var i = prevCount; i < called.length; i++) {
                var num = called[i];
                if (!calledNumbers.has(num)) {
                    calledNumbers.add(num);
                    var isLast = (i === called.length - 1);
                    highlightMasterNumber(num, isLast);
                    addCalledNumberTag(num);
                    autoMarkAllCartelas(num);
                    var _strip = document.getElementById('called-tags');
                    if (_strip) _strip.scrollLeft = _strip.scrollWidth;
                    if (isLast) {
                        showNumberAnnouncement(num);
                        playNumberSound(num);
                    }
                }
            }

            if (called.length >= 4 && !isSpectator) {
                checkMyBingo();
            }
        } else if (data.status === 'completed') {
            handleRoundCompleted(data);
        }
    });
}

function showNumberAnnouncement(num) {
    var letter = getNumberLetter(num);
    var color = getLetterColor(letter);
    var al = document.getElementById('announce-letter');
    var an = document.getElementById('announce-number');
    var na = document.getElementById('number-announce');
    if (al) { al.textContent = letter; al.style.color = color; }
    if (an) an.textContent = num;
    if (na) na.classList.remove('hidden');
    if (_announceTimeout) clearTimeout(_announceTimeout);
    _announceTimeout = setTimeout(function() {
        if (na) na.classList.add('hidden');
        _announceTimeout = null;
    }, 4500);
}

// ==================== BINGO CHECK ====================
var _bingoDetected = false;
async function checkMyBingo() {
    if (_bingoDetected) return;
    try {
        var calledArr = Array.from(calledNumbers);
        for (var cartelaNum in myCartelas) {
            if (myCartelas.hasOwnProperty(cartelaNum)) {
                if (checkBingoLocal(myCartelas[cartelaNum], calledArr)) {
                    _bingoDetected = true;
                    playBingoAnnouncement(cartelaNum);
                    showToast('BINGO! Waiting for confirmation...');
                    return;
                }
            }
        }
    } catch (err) {
        console.error('checkMyBingo unexpected error:', err);
    }
}

function checkBingoLocal(flat, called) {
    var calledSet = new Set(called);
    var grid = [];
    for (var r = 0; r < 5; r++) grid.push(flat.slice(r * 5, r * 5 + 5));
    var isM = function(n) { return n === 0 || calledSet.has(n); };
    for (var ri = 0; ri < 5; ri++) { if (grid[ri].every(isM)) return true; }
    for (var c = 0; c < 5; c++) { if (grid.every(function(row) { return isM(row[c]); })) return true; }
    if ([0,1,2,3,4].every(function(i) { return isM(grid[i][i]); })) return true;
    if ([0,1,2,3,4].every(function(i) { return isM(grid[i][4-i]); })) return true;
    return false;
}

// ==================== ROUND COMPLETED ====================
function handleRoundCompleted(data) {
    if (roundUnsubscribe) { roundUnsubscribe(); roundUnsubscribe = null; }
    stopGameCountdown();
    var na = document.getElementById('number-announce');
    if (na) na.classList.add('hidden');
    listenerReady = false;
    if (!currentUser) return;
    var uidStr = String(currentUser.id);
    var isWinner = (data.winners || []).includes(uidStr);
    var noWinner = !data.winners || data.winners.length === 0;

    if (isWinner) {
        setTimeout(function() { showWinModal(data); }, 5000);
    } else if (noWinner) {
        var winnerName = data.winner_name || '';
        if (winnerName === 'No players') {
            isSpectator = false;
            showToast('No players joined. Starting new game...');
            setTimeout(async function() { await playNow(currentStake); }, 1500);
            return;
        } else {
            showToast('All numbers called! No winner this round.');
        }
        setTimeout(async function() { isSpectator = false; await navigateTo('home'); }, 4000);
    } else if (isSpectator) {
        var winnerName = data.winner_name || 'Unknown';
        var prize = Math.round((data.prize_per_winner || 0) * 10) / 10;
        var winnerCount = (data.winners || []).length;
        if (winnerCount > 1) {
            showToast(winnerCount + ' winners split ' + prize + ' ETB each!');
        } else {
            showToast(winnerName + ' won ' + prize + ' ETB!');
        }
        setTimeout(async function() { isSpectator = false; await navigateTo('home'); }, 5000);
    } else {
        showToast('Game over! Better luck next time.');
        setTimeout(async function() { await navigateTo('home'); }, 3000);
    }
}

function showWinModal(data) {
    var wn = document.getElementById('winner-name');
    var wc = document.getElementById('winner-cartela');
    var wp = document.getElementById('winner-prize');
    if (wn) wn.textContent = (currentUser ? currentUser.first_name : 'Player') || 'Player';
    var cartelaNum = Array.isArray(data.winning_cartela) ? data.winning_cartela[0] : data.winning_cartela;
    if (wc) wc.textContent = cartelaNum || '?';
    if (wp) wp.textContent = (Math.round((data.prize_per_winner || 0) * 10) / 10) + ' ETB';

    var flat = myCartelas[cartelaNum];
    var winGrid = document.getElementById('win-cartela-grid');
    if (winGrid) {
        winGrid.innerHTML = '';
        if (flat) {
            var calledArr = data.called_numbers || [];
            var calledSet = new Set(calledArr);
            for (var i = 0; i < 25; i++) {
                var num = flat[i];
                var cell = document.createElement('div');
                cell.className = 'rounded text-[9px] font-bold text-center py-1';
                if (num === 0) {
                    cell.textContent = '★';
                    cell.style.background = 'rgba(255,140,0,0.5)';
                    cell.style.color = '#fff';
                } else if (calledSet.has(num)) {
                    cell.textContent = num;
                    cell.style.background = 'rgba(16,185,129,0.5)';
                    cell.style.color = '#fff';
                } else {
                    cell.textContent = num;
                    cell.style.background = 'rgba(255,255,255,0.1)';
                    cell.style.color = 'rgba(255,255,255,0.5)';
                }
                winGrid.appendChild(cell);
            }
        }
    }

    var winModal = document.getElementById('win-modal');
    var winCountdown = document.getElementById('win-countdown');
    if (winModal) winModal.classList.remove('hidden');
    var secs = 8;
    if (winCountdown) winCountdown.textContent = secs;
    winCountdownInterval = setInterval(function() {
        secs--;
        if (winCountdown) winCountdown.textContent = secs;
        if (secs <= 0) {
            clearInterval(winCountdownInterval);
            if (winModal) winModal.classList.add('hidden');
            navigateTo('home');
        }
    }, 1000);
}

function loadMyCartelas(roundData) {
    if (!currentUser) { isSpectator = true; return Promise.resolve(); }
    var uidStr = String(currentUser.id);
    var playerInfo = roundData.players ? roundData.players[uidStr] : null;
    if (!playerInfo) {
        isSpectator = true;
        return Promise.resolve();
    }
    myCartelas = {};
    var promises = (playerInfo.cartelas || []).map(function(num) {
        return db.collection('cartelas_master').doc(String(num)).get().then(function(doc) {
            if (doc.exists) myCartelas[num] = doc.data().cartela;
        });
    });
    return Promise.all(promises).then(function() {
        setupGameBoard();
        var called = roundData.called_numbers || [];
        var el;
        if (el = document.getElementById('game-called-count')) el.textContent = called.length;
        var pc = roundData.player_count || 0;
        var roundStake = roundData.stake || currentStake || 10;
        var dr = Math.round(pc * roundStake * 0.75 * 10) / 10;
        if (el = document.getElementById('game-players')) el.textContent = pc;
        if (el = document.getElementById('game-derash')) el.textContent = dr + ' ETB';
        called.forEach(function(num, idx) {
            calledNumbers.add(num);
            highlightMasterNumber(num, idx === called.length - 1);
            addCalledNumberTag(num);
            var strip = document.getElementById('called-tags');
            if (strip) strip.scrollLeft = strip.scrollWidth;
            autoMarkAllCartelas(num);
        });
    }).catch(function(err) {
        console.error('Error loading cartelas:', err);
        showToast('Error loading cartela data');
    });
}

function leaveGame() {
    isSpectator = false;
    listenerReady = false;
    if (roundUnsubscribe) { roundUnsubscribe(); roundUnsubscribe = null; }
    if (_announceTimeout) { clearTimeout(_announceTimeout); _announceTimeout = null; }
    // Unsubscribe from Socket.IO rooms
    if (window._bingoSocket && currentRoundId) {
        window._bingoSocket.emit('unsubscribe', { collection: 'rounds', doc_id: currentRoundId });
        window._bingoSocket.off('cartela_pool');
    }
    try { stopGameCountdown(); } catch(e) {}
    try { stopSelectionCountdown(); } catch(e) {}
    if (winCountdownInterval) { clearInterval(winCountdownInterval); winCountdownInterval = null; }
    myCartelas = {};
    calledNumbers = new Set();
    selectedCartelas = [];
    autoMarkEnabled = false;
    stopBgMusic();
}

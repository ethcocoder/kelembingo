// ==================== GAME BOARD ====================
function setupGameBoard() {
    const nums = Object.keys(myCartelas).map(Number);
    calledNumbers = new Set();
    stopGameCountdown();

    document.getElementById('game-id-display').textContent = '#' + (currentRoundId || '---').substring(0, 6);
    document.getElementById('game-stake').textContent = STAKE + ' ETB';
    document.getElementById('game-called-count').textContent = '0';
    document.getElementById('game-timer').textContent = '--';
    document.getElementById('game-players').textContent = '...';
    document.getElementById('game-derash').textContent = Math.round(STAKE * PRIZE_MULTIPLIER) + ' ETB';
    document.getElementById('game-countdown').classList.add('hidden');

    // Show/hide spectator message vs cartela area
    const spectatorMsg = document.getElementById('spectator-message');
    const cartelaArea = document.getElementById('cartela-area');
    const wrap1 = document.getElementById('cartela-wrap-1');
    const wrap2 = document.getElementById('cartela-wrap-2');

    if (nums.length === 0 || isSpectator) {
        spectatorMsg.classList.remove('hidden');
        cartelaArea.classList.add('hidden');
    } else {
        spectatorMsg.classList.add('hidden');
        cartelaArea.classList.remove('hidden');
    }

    buildMasterGrid();

    // Reset number announce
    document.getElementById('number-announce').classList.add('hidden');
    document.getElementById('number-waiting').classList.remove('hidden');

    if (nums.length > 0) {
        wrap1.classList.remove('hidden');
        document.getElementById('cartela-number-1').textContent = nums[0];
        buildCartelaGrid('cartela-grid-1', myCartelas[nums[0]]);
    } else {
        wrap1.classList.add('hidden');
    }
    if (nums.length >= 2) {
        wrap2.classList.remove('hidden');
        document.getElementById('cartela-number-2').textContent = nums[1];
        buildCartelaGrid('cartela-grid-2', myCartelas[nums[1]]);
    } else {
        wrap2.classList.add('hidden');
    }

    document.getElementById('called-tags').innerHTML = '';
}

function buildMasterGrid() {
    const grid = document.getElementById('master-grid');
    grid.innerHTML = '';
    const colColors = ['#3B82F6', '#8B5CF6', '#D946EF', '#10B981', '#F97316'];
    // Arrange column-wise: B(1-15), I(16-30), N(31-45), G(46-60), O(61-75)
    for (let row = 0; row < 15; row++) {
        for (let col = 0; col < 5; col++) {
            const num = col * 15 + row + 1;
            const cell = document.createElement('div');
            cell.className = 'master-cell text-center rounded-sm font-black transition-all flex items-center justify-center';
            cell.style.background = 'rgba(30, 35, 64, 0.4)';
            cell.style.color = colColors[col] + '55';
            cell.style.fontSize = '9px';
            cell.textContent = num;
            cell.id = 'master-' + num;
            grid.appendChild(cell);
        }
    }
}

function buildCartelaGrid(gridId, flat) {
    const grid = document.getElementById(gridId);
    grid.innerHTML = '';
    if (!flat || flat.length < 25) return;
    for (let i = 0; i < 25; i++) {
        const num = flat[i];
        const cell = document.createElement('div');
        cell.className = 'cartela-cell text-[10px] font-bold text-center py-1.5 rounded-sm cursor-pointer transition-all';
        cell.dataset.num = num;
        if (num === 0) {
            cell.textContent = '★';
            cell.style.background = 'rgba(255,140,0,0.3)';
            cell.style.color = '#FF8C00';
            cell.classList.add('marked');
        } else {
            cell.textContent = num;
            cell.style.background = 'rgba(255,255,255,0.06)';
            cell.style.color = 'rgba(255,255,255,0.7)';
            if (calledNumbers.has(num)) {
                markCartelaCell(cell, num);
            }
            cell.onclick = () => manualMark(cell, num);
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
    setTimeout(() => { cell.style.transform = ''; }, 200);
}

function manualMark(cell, num) {
    if (!calledNumbers.has(num)) {
        showToast('Number ' + num + ' not called yet!');
        return;
    }
    if (cell.classList.contains('marked')) return;
    markCartelaCell(cell, num);
    playMarkSound();
}

function highlightMasterNumber(num, isLast) {
    const cell = document.getElementById('master-' + num);
    if (!cell) return;
    const letter = getNumberLetter(num);
    const color = getLetterColor(letter);
    cell.style.backgroundColor = color;
    cell.style.color = '#fff';
    cell.classList.add('called');
    if (isLast) {
        document.querySelectorAll('.master-cell.last-called').forEach(el => {
            el.classList.remove('last-called');
        });
        cell.classList.add('last-called');
    }
}

function addCalledNumberTag(num) {
    const strip = document.getElementById('called-tags');
    const letter = getNumberLetter(num);
    const color = getLetterColor(letter);
    const el = document.createElement('span');
    el.className = 'called-tag';
    el.style.background = color + '22';
    el.style.border = '1px solid ' + color + '44';
    el.innerHTML = '<div class="tag-letter" style="color:' + color + '">' + letter + '</div>' +
                   '<div class="tag-number">' + num + '</div>';
    strip.appendChild(el);
}

function autoMarkAllCartelas(num) {
    if (!autoMarkEnabled) return;
    const gridIds = ['cartela-grid-1', 'cartela-grid-2'];
    for (const gridId of gridIds) {
        const grid = document.getElementById(gridId);
        if (!grid) continue;
        grid.querySelectorAll('.cartela-cell').forEach(cell => {
            if (parseInt(cell.dataset.num) === num && !cell.classList.contains('marked')) {
                markCartelaCell(cell, num);
            }
        });
    }
}

function toggleAutoMark() {
    autoMarkEnabled = !autoMarkEnabled;
    const toggle = document.getElementById('auto-toggle');
    toggle.classList.toggle('on', autoMarkEnabled);
    showToast(autoMarkEnabled ? 'Auto-mark ON' : 'Auto-mark OFF');
    if (autoMarkEnabled) {
        calledNumbers.forEach(num => autoMarkAllCartelas(num));
    }
}

// ==================== LISTEN TO ROUND (real-time) ====================
function listenToRound(roundId) {
    if (roundUnsubscribe) roundUnsubscribe();
    let prevCalledCount = calledNumbers.size;

    roundUnsubscribe = db.collection('rounds').doc(roundId).onSnapshot(snap => {
        if (!snap.exists) return;
        const data = snap.data();

        document.getElementById('game-players').textContent = data.player_count || 0;
        document.getElementById('game-derash').textContent = Math.round((data.player_count || 0) * STAKE * 0.75) + ' ETB';
        document.getElementById('game-called-count').textContent = (data.called_numbers || []).length;

        if (data.status === 'selecting') {
            document.getElementById('game-countdown').classList.remove('hidden');
            const deadline = data.selection_deadline;
            if (deadline) {
                let dlMs;
                if (typeof deadline === 'object' && deadline.toDate) {
                    dlMs = deadline.toDate().getTime();
                } else if (typeof deadline === 'string') {
                    dlMs = new Date(deadline).getTime();
                } else if (typeof deadline === 'object' && deadline._iso) {
                    dlMs = new Date(deadline._iso).getTime();
                } else if (typeof deadline === 'object' && deadline.seconds) {
                    dlMs = deadline.seconds * 1000;
                } else {
                    dlMs = new Date(deadline).getTime();
                }
                if (!isNaN(dlMs)) {
                    startSelectionCountdownOnGame(dlMs);
                } else {
                    document.getElementById('game-countdown').textContent = 'Waiting for players...';
                }
            } else {
                document.getElementById('game-countdown').textContent = 'Waiting for players...';
            }
        } else if (data.status === 'playing') {
            document.getElementById('game-countdown').classList.add('hidden');

            const nextAt = data.next_number_at;
            if (nextAt) {
                let nextMs;
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

            const called = data.called_numbers || [];
            for (let i = prevCalledCount; i < called.length; i++) {
                const num = called[i];
                if (!calledNumbers.has(num)) {
                    calledNumbers.add(num);
                    const isLast = (i === called.length - 1);
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
            prevCalledCount = called.length;

            if (called.length >= 4 && !isSpectator) {
                checkMyBingo();
            }
        } else if (data.status === 'completed') {
            handleRoundCompleted(data);
        }
    });
}

function showNumberAnnouncement(num) {
    const letter = getNumberLetter(num);
    const color = getLetterColor(letter);
    document.getElementById('announce-letter').textContent = letter;
    document.getElementById('announce-letter').style.color = color;
    document.getElementById('announce-number').textContent = num;
    document.getElementById('number-announce').classList.remove('hidden');
    document.getElementById('number-waiting').classList.add('hidden');
    setTimeout(() => {
        document.getElementById('number-announce').classList.add('hidden');
        document.getElementById('number-waiting').classList.remove('hidden');
    }, 3500);
}

// ==================== BINGO CHECK ====================
async function checkMyBingo() {
    try {
        const calledArr = Array.from(calledNumbers);
        for (const [cartelaNum, flat] of Object.entries(myCartelas)) {
            if (checkBingoLocal(flat, calledArr)) {
                try {
                    const roundRef = db.collection('rounds').doc(currentRoundId);
                    const uidStr = String(currentUser.id);

                    await db.runTransaction(async (txn) => {
                        const roundSnap = await txn.get(roundRef);
                        if (!roundSnap.exists) return;
                        const rd = roundSnap.data();
                        if (rd.status === 'completed') return;
                        const currentWinners = rd.winners || [];
                        if (currentWinners.includes(uidStr)) return;

                        const newWinners = [...currentWinners, uidStr];
                        
                        const userRef = db.collection('users').doc(uidStr);
                        const userDoc = await txn.get(userRef);
                        const ud = userDoc.data();
                        
                        txn.update(userRef, {
                            wins: (ud.wins || 0) + 1,
                            total_games: (ud.total_games || 0) + 1,
                            is_playing: false,
                            updated_at: firebase.firestore.FieldValue.serverTimestamp()
                        });

                        for (const pid of Object.keys(rd.players || {})) {
                            if (pid !== uidStr) {
                                const ref2 = db.collection('users').doc(pid);
                                const d2 = await txn.get(ref2);
                                if (d2.exists) {
                                    txn.update(ref2, {
                                        losses: (d2.data().losses || 0) + 1,
                                        total_games: (d2.data().total_games || 0) + 1,
                                        is_playing: false,
                                        updated_at: firebase.firestore.FieldValue.serverTimestamp()
                                    });
                                }
                            }
                        }

                        txn.update(roundRef, {
                            status: 'completed',
                            winners: newWinners,
                            winner_name: currentUser.first_name || 'Player',
                            winning_cartela: parseInt(cartelaNum),
                            completed_at: firebase.firestore.FieldValue.serverTimestamp()
                        });
                    });
                } catch (err) {
                    console.error('Error claiming bingo:', err);
                }
                return;
            }
        }
    } catch (err) {
        console.error('checkMyBingo unexpected error:', err);
    }
}

function checkBingoLocal(flat, called) {
    const calledSet = new Set(called);
    const grid = [];
    for (let r = 0; r < 5; r++) grid.push(flat.slice(r * 5, r * 5 + 5));
    const isM = n => n === 0 || calledSet.has(n);
    for (const row of grid) { if (row.every(isM)) return true; }
    for (let c = 0; c < 5; c++) { if (grid.every(row => isM(row[c]))) return true; }
    if ([0,1,2,3,4].every(i => isM(grid[i][i]))) return true;
    if ([0,1,2,3,4].every(i => isM(grid[i][4-i]))) return true;
    return false;
}

// ==================== ROUND COMPLETED ====================
function handleRoundCompleted(data) {
    if (roundUnsubscribe) { roundUnsubscribe(); roundUnsubscribe = null; }
    stopGameCountdown();
    document.getElementById('number-announce').classList.add('hidden');
    document.getElementById('number-waiting').classList.remove('hidden');
    listenerReady = false;
    const uidStr = String(currentUser.id);
    const isWinner = (data.winners || []).includes(uidStr);
    const noWinner = !data.winners || data.winners.length === 0;

    if (isWinner) {
        playWinSound();
        showWinModal(data);
    } else if (noWinner) {
        showToast('All numbers called! No winner this round.');
        setTimeout(() => { isSpectator = false; navigateTo('home'); }, 4000);
    } else if (isSpectator) {
        const winnerName = data.winner_name || 'Unknown';
        const prize = Math.round(data.prize_per_winner || 0);
        showToast(`${winnerName} won ${prize} ETB!`);
        setTimeout(() => { isSpectator = false; navigateTo('home'); }, 5000);
    } else {
        showToast('Game over! Better luck next time.');
        setTimeout(() => navigateTo('home'), 3000);
    }
}

function showWinModal(data) {
    document.getElementById('winner-name').textContent = currentUser.first_name || 'Player';
    document.getElementById('winner-cartela').textContent = data.winning_cartela || '?';
    document.getElementById('winner-prize').textContent = Math.round(data.prize_per_winner || 0) + ' ETB';

    const cartelaNum = data.winning_cartela;
    const flat = myCartelas[cartelaNum];
    const winGrid = document.getElementById('win-cartela-grid');
    winGrid.innerHTML = '';
    if (flat) {
        const calledArr = data.called_numbers || [];
        const calledSet = new Set(calledArr);
        for (let i = 0; i < 25; i++) {
            const num = flat[i];
            const cell = document.createElement('div');
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

    document.getElementById('win-modal').classList.remove('hidden');
    let secs = 8;
    document.getElementById('win-countdown').textContent = secs;
    winCountdownInterval = setInterval(() => {
        secs--;
        document.getElementById('win-countdown').textContent = secs;
        if (secs <= 0) {
            clearInterval(winCountdownInterval);
            document.getElementById('win-modal').classList.add('hidden');
            navigateTo('home');
        }
    }, 1000);
}

function loadMyCartelas(roundData) {
    const uidStr = String(currentUser.id);
    const playerInfo = roundData.players ? roundData.players[uidStr] : null;
    if (!playerInfo) {
        isSpectator = true;
        return Promise.resolve();
    }
    myCartelas = {};
    const promises = (playerInfo.cartelas || []).map(num =>
        db.collection('cartelas_master').doc(String(num)).get().then(doc => {
            if (doc.exists) myCartelas[num] = doc.data().cartela;
        })
    );
    return Promise.all(promises).then(() => {
        setupGameBoard();
        const called = roundData.called_numbers || [];
        called.forEach((num, idx) => {
            calledNumbers.add(num);
            highlightMasterNumber(num, idx === called.length - 1);
                    addCalledNumberTag(num);
                    const strip = document.getElementById('called-tags');
                    if (strip) strip.scrollLeft = strip.scrollWidth;
                    autoMarkAllCartelas(num);
        });
    }).catch(err => {
        console.error('Error loading cartelas:', err);
        showToast('Error loading cartela data');
    });
}

function leaveGame() {
    isSpectator = false;
    listenerReady = false;
    if (roundUnsubscribe) { roundUnsubscribe(); roundUnsubscribe = null; }
    if (numberCallInterval) { clearInterval(numberCallInterval); numberCallInterval = null; }
    stopGameCountdown();
    if (winCountdownInterval) { clearInterval(winCountdownInterval); winCountdownInterval = null; }
    if (selectionTimer) { stopSelectionTimer(); }
    myCartelas = {};
    calledNumbers = new Set();
    selectedCartelas = [];
    autoMarkEnabled = false;
    stopBgMusic();
}

function refreshGame() {
    if (currentRoundId) {
        db.collection('rounds').doc(currentRoundId).get().then(doc => {
            if (doc.exists) {
                const data = doc.data();
                calledNumbers = new Set();
                setupGameBoard();
                const called = data.called_numbers || [];
                called.forEach((num, idx) => {
                    calledNumbers.add(num);
                    highlightMasterNumber(num, idx === called.length - 1);
                    addCalledNumberTag(num);
                    autoMarkAllCartelas(num);
                });
                document.getElementById('game-called-count').textContent = (data.called_numbers || []).length;
            }
        });
    }
}

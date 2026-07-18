// ==================== HISTORY ====================
async function loadHistory() {
    if (!currentUser) return;
    
    var list = document.getElementById('history-list');
    var loading = document.getElementById('history-loading');
    var empty = document.getElementById('history-empty');
    
    if (loading) loading.classList.remove('hidden');
    if (empty) empty.classList.add('hidden');
    
    try {
        // 1. Get 3 most recent winners (motivational)
        var winnerSnap = await db.collection('rounds')
            .where('status', '==', 'completed')
            .orderBy('created_at', 'desc')
            .limit(30).get();
        
        if (loading) loading.classList.add('hidden');
        
        var recentWinners = [];
        winnerSnap.forEach(function(doc) {
            var d = doc.data();
            if (d.winners && d.winners.length > 0 && d.winner_name) {
                var date = '';
                if (d.completed_at) {
                    var dt = d.completed_at.toDate ? d.completed_at.toDate() : new Date(d.completed_at);
                    date = dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                }
                if (recentWinners.length < 3) {
                    recentWinners.push({
                        name: d.winner_name,
                        prize: Math.round(d.prize_per_winner || 0),
                        date: date,
                        cartela: d.winning_cartela || '?'
                    });
                }
            }
        });
        
        if (!list) return;
        list.innerHTML = '';
        
        // Render winners section
        if (recentWinners.length > 0) {
            var winnersHeader = document.createElement('div');
            winnersHeader.className = 'mb-3';
            winnersHeader.innerHTML = '<h3 class="text-sm font-bold text-amber-400 mb-2 flex items-center gap-2">' +
                '<svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/></svg>' +
                'Recent Winners</h3>';
            list.appendChild(winnersHeader);
            
            recentWinners.forEach(function(w) {
                var el = document.createElement('div');
                el.className = 'glass rounded-xl p-3 flex items-center justify-between';
                el.innerHTML = '<div class="flex items-center gap-3">' +
                    '<div class="w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold" style="background: linear-gradient(135deg, #FFD700, #FF8C00); color: #1a1a2e;">🏆</div>' +
                    '<div>' +
                    '<div class="text-sm font-bold text-white">' + w.name + '</div>' +
                    '<div class="text-[10px] text-white/40">Cartela #' + w.cartela + ' · ' + w.date + '</div>' +
                    '</div>' +
                    '</div>' +
                    '<div class="text-right">' +
                    '<div class="text-sm font-bold text-bingo-green">' + w.prize + ' ETB</div>' +
                    '<div class="text-[10px] text-amber-400/60">Winner!</div>' +
                    '</div>';
                list.appendChild(el);
            });
            
            var divider = document.createElement('div');
            divider.className = 'border-t border-white/5 my-3';
            list.appendChild(divider);
        }
        
        // 2. Individual history
        var uidStr = String(currentUser.id);
        var myRounds = [];
        winnerSnap.forEach(function(doc) {
            var d = doc.data();
            var wasPlayer = d.players && d.players[uidStr];
            if (wasPlayer) myRounds.push({ id: doc.id, data: d });
        });
        
        if (myRounds.length > 0) {
            var myHeader = document.createElement('div');
            myHeader.className = 'mb-3';
            myHeader.innerHTML = '<h3 class="text-sm font-bold text-white/60 mb-2">Your Games</h3>';
            list.appendChild(myHeader);
            
            myRounds.forEach(function(item) {
                var d = item.data;
                var isWinner = (d.winners || []).includes(uidStr);
                var el = document.createElement('div');
                el.className = 'glass rounded-xl p-3';
                var prize = isWinner ? Math.round(d.prize_per_winner || 0) : 0;
                var date = '';
                if (d.created_at) {
                    var dt = d.created_at.toDate ? d.created_at.toDate() : new Date(d.created_at);
                    date = dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                }
                el.innerHTML = '<div class="flex items-center justify-between mb-1">' +
                    '<span class="text-sm font-bold ' + (isWinner ? 'text-bingo-green' : 'text-red-400') + '">' + (isWinner ? '🏆 Won!' : '❌ Lost') + '</span>' +
                    '<span class="text-xs text-white/40">' + date + '</span>' +
                    '</div>' +
                    '<div class="flex items-center justify-between text-xs text-white/60">' +
                    '<span>Players: ' + (d.player_count || 0) + '</span>' +
                    '<span>Prize: ' + prize + ' ETB</span>' +
                    '</div>';
                list.appendChild(el);
            });
        } else if (recentWinners.length === 0) {
            if (empty) empty.classList.remove('hidden');
        }
    } catch (err) {
        if (loading) loading.classList.add('hidden');
        console.error('History error:', err);
    }
}

// ==================== HISTORY ====================
async function loadHistory() {
    const list = document.getElementById('history-list');
    document.getElementById('history-loading').classList.remove('hidden');
    document.getElementById('history-empty').classList.add('hidden');
    try {
        const snap = await db.collection('rounds')
            .where('status', '==', 'completed')
            .orderBy('created_at', 'desc')
            .limit(20).get();

        document.getElementById('history-loading').classList.add('hidden');
        if (snap.empty) {
            document.getElementById('history-empty').classList.remove('hidden');
            return;
        }

        list.innerHTML = '';
        const uidStr = String(currentUser.id);
        snap.forEach(doc => {
            const d = doc.data();
            const isWinner = (d.winners || []).includes(uidStr);
            const wasPlayer = d.players && d.players[uidStr];
            if (!wasPlayer) return;

            const el = document.createElement('div');
            el.className = 'glass rounded-xl p-4';
            const prize = isWinner ? Math.round(d.prize_per_winner || 0) : 0;
            const date = d.created_at ? (d.created_at.toDate ? d.created_at.toDate().toLocaleDateString() : '') : '';
            el.innerHTML = '<div class="flex items-center justify-between mb-2">' +
                '<span class="text-sm font-bold ' + (isWinner ? 'text-bingo-green' : 'text-red-400') + '">' + (isWinner ? '🏆 Won!' : '❌ Lost') + '</span>' +
                '<span class="text-xs text-white/40">' + date + '</span>' +
                '</div>' +
                '<div class="flex items-center justify-between text-xs text-white/60">' +
                '<span>Players: ' + (d.player_count || 0) + '</span>' +
                '<span>Prize: ' + prize + ' ETB</span>' +
                '</div>';
            list.appendChild(el);
        });
    } catch (err) {
        document.getElementById('history-loading').classList.add('hidden');
        console.error('History error:', err);
    }
}

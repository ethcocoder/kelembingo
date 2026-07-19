// ==================== DASHBOARD ====================
function processDashboardData() {
    var totalUsersEl = document.getElementById('statTotalUsers');
    animateNum(totalUsersEl, allUsers.length, 800);

    activeRoundsCount = 0;
    totalRevenue = 0;
    winnersToday = 0;
    var today = new Date(); today.setHours(0, 0, 0, 0);

    allRounds.forEach(function (g) {
        var hasPlayers = (g.player_count || 0) > 0;
        if ((g.status === 'selecting' || g.status === 'playing') && hasPlayers) activeRoundsCount++;
        if (hasPlayers) totalRevenue += (g.stake || 0) * (g.player_count || 0);
        if (g.status === 'completed' && g.winners && g.winners.length > 0) {
            try {
                var gDate = g.created_at && g.created_at.toDate ? g.created_at.toDate() : (g.created_at ? new Date(g.created_at) : null);
                if (gDate && gDate >= today) winnersToday++;
            } catch (e) { }
        }
    });

    animateNum(document.getElementById('statActiveGames'), activeRoundsCount, 800);
    animateNum(document.getElementById('statRevenue'), Math.floor(totalRevenue), 800);
    animateNum(document.getElementById('statWinnersToday'), winnersToday, 800);

    document.getElementById('notifBadge').textContent = activeRoundsCount;

    var sorted = allRounds.slice().sort(function (a, b) {
        var ta = a.created_at ? (a.created_at.seconds || 0) : 0;
        var tb = b.created_at ? (b.created_at.seconds || 0) : 0;
        return tb - ta;
    });
    var recent = sorted.filter(function (g) { return (g.player_count || 0) > 0; }).slice(0, 10);
    var tbody = document.getElementById('recentGamesTable');
    var empty = document.getElementById('recentGamesEmpty');
    if (!tbody) return;

    if (recent.length === 0) {
        tbody.innerHTML = '';
        empty.classList.remove('hidden');
        return;
    }
    empty.classList.add('hidden');

    tbody.innerHTML = recent.map(function (g) {
        var id = g.id || '-';
        var shortId = typeof id === 'string' ? id.substring(0, 8) : id;
        var players = g.player_count || 0;
        var stake = g.stake || 0;
        var status = g.status || '-';
        var statusColor = status === 'completed' ? 'text-[#10B981] bg-[#10B981]/10' : (status === 'playing' ? 'text-[#FF8C00] bg-[#FF8C00]/10' : 'text-[#3B82F6] bg-[#3B82F6]/10');
        return '<tr class="tbl-row border-b border-white/[0.03]">' +
            '<td class="px-3 py-3 text-sm font-mono text-gray-400">#' + shortId + '</td>' +
            '<td class="px-3 py-3 text-sm">' + players + '</td>' +
            '<td class="px-3 py-3 text-sm text-[#FF8C00] font-semibold">' + stake + ' ETB</td>' +
            '<td class="px-3 py-3"><span class="text-xs font-semibold px-2 py-1 rounded-full ' + statusColor + '">' + status + '</span></td>' +
            '<td class="px-3 py-3 text-xs text-gray-500">' + fmtTimeShort(g.created_at) + '</td>' +
            '</tr>';
    }).join('');

    buildActivityFeed(sorted);
}

function buildActivityFeed(sortedRounds) {
    var feed = document.getElementById('activityFeed');
    var emptyEl = document.getElementById('activityEmpty');
    if (!feed) return;

    var items = [];
    sortedRounds.forEach(function (g) {
        if ((g.player_count || 0) === 0) return;
        var id = g.id || '';
        var shortId = typeof id === 'string' ? id.substring(0, 8) : id;
        if (g.status === 'completed' && g.winners && g.winners.length > 0) {
            items.push({
                text: '<span class="font-semibold text-[#10B981]">Winner</span> Round #' + shortId + ' — ' + (g.winner_name || 'User') + ' won ' + (g.prize_per_winner || 0) + ' ETB',
                border: 'border-[#10B981]',
                time: fmtTimeShort(g.created_at)
            });
        } else if (g.status === 'playing') {
            items.push({
                text: '<span class="font-semibold text-[#FF8C00]">Round</span> #' + shortId + ' is playing — ' + (g.player_count || 0) + ' players',
                border: 'border-[#FF8C00]',
                time: fmtTimeShort(g.created_at)
            });
        } else if (g.status === 'selecting') {
            items.push({
                text: '<span class="font-semibold text-[#3B82F6]">Round</span> #' + shortId + ' selecting players',
                border: 'border-[#3B82F6]',
                time: fmtTimeShort(g.created_at)
            });
        }
    });

    if (items.length === 0) {
        feed.innerHTML = '';
        emptyEl.classList.remove('hidden');
        return;
    }
    emptyEl.classList.add('hidden');

    feed.innerHTML = items.slice(0, 20).map(function (item) {
        return '<div class="rounded-lg px-3 py-2.5 border-l-2 ' + item.border + ' hover:bg-white/[0.02] transition-all">' +
            '<div class="flex items-center justify-between">' +
            '<p class="text-sm">' + item.text + '</p>' +
            '<span class="text-[10px] text-gray-600 flex-shrink-0 ml-2">' + item.time + '</span>' +
            '</div></div>';
    }).join('');
}

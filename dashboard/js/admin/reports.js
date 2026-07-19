// ==================== REPORTS ====================
function updateReports() {
    var validRounds = allRounds.filter(function (g) { return (g.player_count || 0) > 0; });
    var completed = validRounds.filter(function (g) { return g.status === 'completed'; });
    var totalGames = validRounds.length;
    var totalStakes = 0;
    var totalPlayers = 0;
    validRounds.forEach(function (g) {
        totalStakes += (g.stake || 0) * (g.player_count || 0);
        totalPlayers += (g.player_count || 0);
    });
    var avgPlayers = totalGames > 0 ? Math.round(totalPlayers / totalGames) : 0;
    var completionRate = totalGames > 0 ? Math.round((completed.length / totalGames) * 100) : 0;

    document.getElementById('reportTotalGames').textContent = totalGames.toLocaleString();
    document.getElementById('reportTotalStakes').textContent = totalStakes.toLocaleString() + ' ETB';
    document.getElementById('reportAvgPlayers').textContent = avgPlayers;
    document.getElementById('reportCompletionRate').textContent = completionRate + '%';

    var days = [];
    for (var i = 6; i >= 0; i--) {
        var d = new Date();
        d.setDate(d.getDate() - i);
        d.setHours(0, 0, 0, 0);
        days.push({ date: d, games: 0, revenue: 0 });
    }

    validRounds.forEach(function (g) {
        var gDate = null;
        try {
            gDate = g.created_at && g.created_at.toDate ? g.created_at.toDate() : (g.created_at ? new Date(g.created_at) : null);
        } catch (e) { }
        if (!gDate) return;
        gDate.setHours(0, 0, 0, 0);
        for (var j = 0; j < days.length; j++) {
            if (gDate.getTime() === days[j].date.getTime()) {
                days[j].games++;
                days[j].revenue += (g.stake || 0) * (g.player_count || 0);
                break;
            }
        }
    });

    var maxGames = Math.max.apply(null, days.map(function (d) { return d.games; }));
    if (maxGames === 0) maxGames = 1;
    var maxRev = Math.max.apply(null, days.map(function (d) { return d.revenue; }));
    if (maxRev === 0) maxRev = 1;

    var chartColors = ['#FF8C00', '#3B82F6', '#10B981', '#8B5CF6', '#14B8A6', '#FF8C00', '#3B82F6'];

    document.getElementById('reportGamesChart').innerHTML = days.map(function (d, idx) {
        var pct = (d.games / maxGames * 100);
        var dayName = d.date.toLocaleDateString('en', { weekday: 'short' });
        return '<div class="flex-1 flex flex-col items-center gap-1">' +
            '<div class="w-full rounded-t chart-bar" style="height:' + pct + '%;background:linear-gradient(to top,' + chartColors[idx] + ',' + chartColors[idx] + '80);"></div>' +
            '<span class="text-[9px] text-gray-600">' + dayName + '</span>' +
            '<span class="text-[9px] text-gray-500 font-semibold">' + d.games + '</span>' +
            '</div>';
    }).join('');

    document.getElementById('reportRevenueChart').innerHTML = days.map(function (d, idx) {
        var pct = (d.revenue / maxRev * 100);
        var dayName = d.date.toLocaleDateString('en', { weekday: 'short' });
        return '<div class="flex-1 flex flex-col items-center gap-1">' +
            '<div class="w-full rounded-t chart-bar" style="height:' + Math.max(pct, 2) + '%;background:linear-gradient(to top,' + chartColors[idx] + ',' + chartColors[idx] + '80);"></div>' +
            '<span class="text-[9px] text-gray-600">' + dayName + '</span>' +
            '<span class="text-[9px] text-gray-500 font-semibold">' + d.revenue + '</span>' +
            '</div>';
    }).join('');
}

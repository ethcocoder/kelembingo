// ==================== DISPLAY UPDATES ====================
function updateAllDisplays() {
    if (!currentUser) return;
    var bal = currentUser.balance || 0;
    var pw = currentUser.play_wallet || 0;
    
    function setText(id, text) {
        var el = document.getElementById(id);
        if (el) el.textContent = text;
    }
    
    setText('home-balance', bal + ' ETB');
    setText('home-play-wallet', pw + ' ETB');
    setText('wallet-balance', bal + ' ETB');
    setText('wallet-play', pw + ' ETB');
    setText('user-greeting', 'Hello, ' + (currentUser.first_name || 'Player') + '!');
    setText('profile-name', currentUser.first_name || 'Player');
    setText('profile-id', '@' + (currentUser.username || 'player'));
    setText('profile-avatar', (currentUser.first_name || 'P')[0].toUpperCase());
    setText('profile-games', currentUser.total_games || 0);
    setText('profile-wins', currentUser.wins || 0);
    
    var tg2 = currentUser.total_games || 0;
    var w2 = currentUser.wins || 0;
    setText('profile-winrate', (tg2 > 0 ? Math.round((w2 / tg2) * 100) : 0) + '%');
    setText('profile-earnings', ((currentUser.wins || 0) * STAKE * 0.75) + ' ETB');
}

// ==================== NAVIGATION ====================
async function navigateTo(screen) {
    if (currentScreen === 'game' && screen !== 'game') {
        try { leaveGame(); } catch(e) { console.warn('leaveGame error:', e); }
    }
    
    if (window.PageLoader) {
        await PageLoader.loadOnDemand(screen);
    }
    
    document.querySelectorAll('.screen').forEach(function(s) { s.classList.remove('active'); });
    var target = document.getElementById('screen-' + screen);
    if (target) { 
        target.classList.remove('screen-transition');
        void target.offsetWidth;
        target.classList.add('active'); 
        target.classList.add('screen-transition'); 
    }
    document.querySelectorAll('.nav-item').forEach(function(n) { n.classList.remove('active'); });
    var navBtn = document.querySelector('.nav-item[data-screen="' + screen + '"]');
    if (navBtn) navBtn.classList.add('active');
    currentScreen = screen;
    var bottomNav = document.getElementById('bottom-nav');
    if (bottomNav) bottomNav.style.display = (screen === 'game') ? 'none' : '';
    if (screen === 'history' && currentUser) loadHistory();
    
    if (currentUser && typeof updateAllDisplays === 'function') {
        updateAllDisplays();
    }
}

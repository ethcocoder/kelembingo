// ==================== DISPLAY UPDATES ====================
function updateAllDisplays() {
    if (!currentUser) return;
    const bal = currentUser.balance || 0;
    const pw = currentUser.play_wallet || 0;
    
    // Helper to safely update element text
    function setText(id, text) {
        const el = document.getElementById(id);
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
    
    const tg2 = currentUser.total_games || 0;
    const w2 = currentUser.wins || 0;
    setText('profile-winrate', (tg2 > 0 ? Math.round((w2 / tg2) * 100) : 0) + '%');
    setText('profile-earnings', ((currentUser.wins || 0) * STAKE * PRIZE_MULTIPLIER) + ' ETB');
}

// ==================== NAVIGATION ====================
async function navigateTo(screen) {
    if (currentScreen === 'game' && screen !== 'game') leaveGame();
    
    // Load the page on demand if PageLoader is available
    if (window.PageLoader) {
        await PageLoader.loadOnDemand(screen);
    }
    
    document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
    const target = document.getElementById('screen-' + screen);
    if (target) { 
        target.classList.add('active'); 
        target.classList.add('screen-transition'); 
    }
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    const navBtn = document.querySelector('.nav-item[data-screen="' + screen + '"]');
    if (navBtn) navBtn.classList.add('active');
    currentScreen = screen;
    document.getElementById('bottom-nav').style.display = (screen === 'game') ? 'none' : '';
    if (screen === 'history') loadHistory();
    
    // Update displays after navigation
    if (currentUser && typeof updateAllDisplays === 'function') {
        updateAllDisplays();
    }
}

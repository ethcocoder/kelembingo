// ==================== DISPLAY UPDATES ====================
function updateAllDisplays() {
    if (!currentUser) return;
    const bal = currentUser.balance || 0;
    const pw = currentUser.play_wallet || 0;
    document.getElementById('home-balance').textContent = bal + ' ETB';
    document.getElementById('home-play-wallet').textContent = pw + ' ETB';
    document.getElementById('wallet-balance').textContent = bal + ' ETB';
    document.getElementById('wallet-play').textContent = pw + ' ETB';
    document.getElementById('user-greeting').textContent = 'Hello, ' + (currentUser.first_name || 'Player') + '!';
    document.getElementById('profile-name').textContent = currentUser.first_name || 'Player';
    document.getElementById('profile-id').textContent = '@' + (currentUser.username || 'player');
    document.getElementById('profile-avatar').textContent = (currentUser.first_name || 'P')[0].toUpperCase();
    document.getElementById('profile-games').textContent = currentUser.total_games || 0;
    document.getElementById('profile-wins').textContent = currentUser.wins || 0;
    const tg2 = currentUser.total_games || 0;
    const w2 = currentUser.wins || 0;
    document.getElementById('profile-winrate').textContent = (tg2 > 0 ? Math.round((w2 / tg2) * 100) : 0) + '%';
    document.getElementById('profile-earnings').textContent = ((currentUser.wins || 0) * STAKE * PRIZE_MULTIPLIER) + ' ETB';
}

// ==================== NAVIGATION ====================
function navigateTo(screen) {
    if (currentScreen === 'game' && screen !== 'game') leaveGame();
    document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
    const target = document.getElementById('screen-' + screen);
    if (target) { target.classList.add('active'); target.classList.add('screen-transition'); }
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    const navBtn = document.querySelector('.nav-item[data-screen="' + screen + '"]');
    if (navBtn) navBtn.classList.add('active');
    currentScreen = screen;
    document.getElementById('bottom-nav').style.display = (screen === 'game') ? 'none' : '';
    if (screen === 'history') loadHistory();
}

// ==================== INIT ====================
document.addEventListener('DOMContentLoaded', async function() {
    restoreAudioSettings();
    
    if (window.PageLoader) {
        await PageLoader.initComponents();
    }
    
    if (window.PageLoader) {
        await PageLoader.loadPage('home');
    }
    
    await initUser();
});

document.addEventListener('pageLoaded', function(e) {
    var screen = e.detail.screen;
    
    if (screen === 'home') {
        if (currentUser && typeof updateAllDisplays === 'function') {
            updateAllDisplays();
        }
    } else if (screen === 'wallet') {
        if (currentUser && typeof updateAllDisplays === 'function') {
            updateAllDisplays();
        }
    } else if (screen === 'profile') {
        if (currentUser && typeof updateAllDisplays === 'function') {
            updateAllDisplays();
        }
    }
});

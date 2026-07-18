// ==================== INIT ====================
document.addEventListener('DOMContentLoaded', async function() {
    // Restore audio settings first
    restoreAudioSettings();
    
    // Load all components (header, nav, modals, overlays)
    if (window.PageLoader) {
        await PageLoader.initComponents();
    }
    
    // Load the default home page
    if (window.PageLoader) {
        await PageLoader.loadPage('home');
    }
    
    // Initialize user (this will trigger auth, load data, etc.)
    initUser();
});

// Listen for page load events to re-initialize page-specific JS
document.addEventListener('pageLoaded', function(e) {
    const screen = e.detail.screen;
    
    // Re-attach event listeners or re-initialize as needed
    if (screen === 'home') {
        // Home page loaded - ensure displays are updated
        if (currentUser && typeof updateAllDisplays === 'function') {
            updateAllDisplays();
        }
    } else if (screen === 'game') {
        // Game board loaded - no special init needed here
        // Game board setup happens via setupGameBoard() called from card-select.js
    } else if (screen === 'history') {
        // History page loaded - load history data
        if (typeof loadHistory === 'function') {
            loadHistory();
        }
    } else if (screen === 'wallet') {
        // Wallet page loaded - update displays
        if (currentUser && typeof updateAllDisplays === 'function') {
            updateAllDisplays();
        }
    } else if (screen === 'profile') {
        // Profile page loaded - update displays
        if (currentUser && typeof updateAllDisplays === 'function') {
            updateAllDisplays();
        }
    }
});

// ==================== HELPERS ====================
function getNumberLetter(num) {
    for (var i = 0; i < BINGO_RANGES.length; i++) {
        var r = BINGO_RANGES[i];
        if (num >= r.min && num <= r.max) return r.letter;
    }
    return '?';
}

function getLetterColor(letter) {
    for (var i = 0; i < BINGO_RANGES.length; i++) {
        if (BINGO_RANGES[i].letter === letter) return BINGO_RANGES[i].color;
    }
    return '#FF8C00';
}

function showToast(msg) {
    var el = document.getElementById('toast');
    var textEl = document.getElementById('toast-text');
    if (el && textEl) {
        textEl.textContent = msg;
        el.classList.remove('hidden');
        setTimeout(function() { el.classList.add('hidden'); }, 3000);
    }
}

function showLoading(msg) {
    var overlay = document.getElementById('loading-overlay');
    var textEl = document.getElementById('loading-text');
    if (overlay && textEl) {
        textEl.textContent = msg || 'Loading...';
        overlay.classList.remove('hidden');
    }
}

function hideLoading() {
    var overlay = document.getElementById('loading-overlay');
    if (overlay) overlay.classList.add('hidden');
}

function hideScreen(id) {
    var el = document.getElementById(id);
    if (el) el.classList.add('hidden');
}

// ==================== HELPERS ====================
function getNumberLetter(num) {
    for (const r of BINGO_RANGES) { if (num >= r.min && num <= r.max) return r.letter; }
    return '?';
}

function getLetterColor(letter) {
    for (const r of BINGO_RANGES) { if (r.letter === letter) return r.color; }
    return '#FF8C00';
}

function showToast(msg) {
    const el = document.getElementById('toast');
    document.getElementById('toast-text').textContent = msg;
    el.classList.remove('hidden');
    setTimeout(() => el.classList.add('hidden'), 3000);
}

function showLoading(msg) {
    document.getElementById('loading-text').textContent = msg || 'Loading...';
    document.getElementById('loading-overlay').classList.remove('hidden');
}

function hideLoading() {
    document.getElementById('loading-overlay').classList.add('hidden');
}

function hideScreen(id) {
    document.getElementById(id).classList.add('hidden');
}

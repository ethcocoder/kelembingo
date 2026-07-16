// ==================== RULES ====================
function showRules() { document.getElementById('rules-modal').classList.remove('hidden'); }
function hideRules() { document.getElementById('rules-modal').classList.add('hidden'); }

function logout() {
    if (tg) tg.close();
    else window.location.reload();
}

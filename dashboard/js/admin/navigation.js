// ==================== SECTION SWITCHING ====================
var sectionTitles = {
    dashboard: 'Dashboard',
    users: 'User Management',
    games: 'Games',
    cartelas: 'Cartela Pool',
    reports: 'Reports',
    payments: 'Payments',
    settings: 'Settings'
};

function switchSection(name) {
    currentSection = name;
    window.location.hash = name;
    document.querySelectorAll('.section').forEach(function (s) { s.classList.remove('active'); });
    var sec = document.getElementById('section-' + name);
    if (sec) sec.classList.add('active');
    document.getElementById('pageTitle').textContent = sectionTitles[name] || name;
    document.querySelectorAll('.nav-item').forEach(function (n) {
        n.classList.remove('active');
        n.classList.add('text-gray-400');
    });
    var activeNav = document.querySelector('.nav-item[data-section="' + name + '"]');
    if (activeNav) {
        activeNav.classList.add('active');
        activeNav.classList.remove('text-gray-400');
    }
    document.getElementById('sidebar').classList.remove('open');
    document.getElementById('sidebarOverlay').classList.remove('open');
    document.getElementById('userDropdown').classList.add('hidden');
    if (name === 'cartelas') loadCartelaPool();
    if (name === 'payments') loadPayments();
}

// Restore section from URL hash on page load
(function() {
    var hash = window.location.hash.replace('#', '');
    if (hash && sectionTitles[hash]) {
        switchSection(hash);
    }
})();

window.addEventListener('hashchange', function() {
    var hash = window.location.hash.replace('#', '');
    if (hash && sectionTitles[hash] && hash !== currentSection) {
        switchSection(hash);
    }
});

// ==================== MODALS ====================
function openModal(id) {
    var m = document.getElementById(id);
    if (m) { m.classList.remove('hidden'); m.classList.add('flex'); document.body.style.overflow = 'hidden'; }
}
function closeModal(id) {
    var m = document.getElementById(id);
    if (m) { m.classList.add('hidden'); m.classList.remove('flex'); document.body.style.overflow = ''; }
}
document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
        document.querySelectorAll('[id$="Modal"]').forEach(function (m) {
            if (!m.classList.contains('hidden')) { m.classList.add('hidden'); m.classList.remove('flex'); }
        });
        document.body.style.overflow = '';
    }
});

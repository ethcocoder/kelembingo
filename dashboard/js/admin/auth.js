// ==================== AUTH CHECK ====================
(function () {
    if (localStorage.getItem('loggedIn') !== 'true') {
        window.location.href = '/login';
        return;
    }
    var u = localStorage.getItem('username') || 'Admin';
    var r = localStorage.getItem('role') || 'admin';
    var initial = u.charAt(0).toUpperCase();
    var roleLabel = r === 'super_admin' ? 'Super Admin' : 'Admin';
    document.getElementById('sidebarUsername').textContent = u;
    document.getElementById('sidebarRole').textContent = roleLabel;
    document.getElementById('sidebarAvatar').textContent = initial;
    document.getElementById('headerUsername').textContent = u;
    document.getElementById('headerRole').textContent = roleLabel;
    document.getElementById('headerAvatar').textContent = initial;
})();

function logout() {
    localStorage.removeItem('loggedIn');
    localStorage.removeItem('username');
    localStorage.removeItem('role');
    window.location.href = '/login';
}

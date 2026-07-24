var _wiping = false;

document.addEventListener('DOMContentLoaded', function () {
    var cb = document.getElementById('wipeConfirm');
    var btn = document.getElementById('wipeAllBtn');
    if (cb && btn) {
        cb.addEventListener('change', function () {
            var checked = cb.checked;
            btn.disabled = !checked;
            btn.className = checked
                ? 'w-full py-3 rounded-xl text-sm font-semibold bg-red-600 hover:bg-red-700 text-white cursor-pointer border-0'
                : 'w-full py-3 rounded-xl text-sm font-semibold bg-red-600/30 text-red-400 cursor-not-allowed border border-red-500/30';
        });
    }
});

function runWipeAll() {
    if (_wiping) return;
    if (!document.getElementById('wipeConfirm').checked) return;
    if (!confirm('Are you SURE? This will delete ALL data permanently.')) return;
    if (!confirm('Last chance — there is NO undo. Proceed?')) return;

    _wiping = true;
    var btn = document.getElementById('wipeAllBtn');
    btn.disabled = true;
    btn.textContent = 'Wiping...';

    fetch(API_BASE + '/api/admin/wipe-all', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({confirm: true}),
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
        if (data.ok) {
            var msg = 'Wipe complete! Deleted: ' + data.deleted.documents + ' documents';
            if (data.deleted.events) msg += ', ' + data.deleted.events + ' events';
            if (data.backup_unpinned) msg += '. Backup unpinned.';
            if (data.backup_error) msg += ' (backup error: ' + data.backup_error + ')';
            alert(msg);
            if (typeof loadBackupStatus === 'function') loadBackupStatus();
        } else {
            alert('Wipe failed: ' + (data.detail || 'unknown error'));
        }
    })
    .catch(function (err) {
        alert('Wipe error: ' + err.message);
    })
    .finally(function () {
        _wiping = false;
        btn.disabled = false;
        btn.textContent = 'Wipe All Data';
        document.getElementById('wipeConfirm').checked = false;
        document.getElementById('wipeConfirm').dispatchEvent(new Event('change'));
    });
}

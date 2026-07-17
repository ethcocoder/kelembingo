// ==================== ADMIN UTILITIES ====================
function animateNum(el, target, dur) {
    if (!el) return;
    var start = 0;
    var startTime = null;
    function step(ts) {
        if (!startTime) startTime = ts;
        var p = Math.min((ts - startTime) / dur, 1);
        var val = Math.round(p * target);
        el.textContent = val.toLocaleString();
        if (p < 1) requestAnimationFrame(step);
    }
    if (target > 0) requestAnimationFrame(step);
    else el.textContent = '0';
}

function fmtTime(ts) {
    if (!ts) return '-';
    try {
        var d = ts.toDate ? ts.toDate() : new Date(ts);
        return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch (e) { return '-'; }
}

function fmtTimeShort(ts) {
    if (!ts) return '-';
    try {
        var d = ts.toDate ? ts.toDate() : new Date(ts);
        var now = new Date();
        var diff = Math.floor((now - d) / 1000);
        if (diff < 60) return diff + 's ago';
        if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
        if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
        return Math.floor(diff / 86400) + 'd ago';
    } catch (e) { return '-'; }
}

function hashStr(s) {
    var h = 0;
    for (var i = 0; i < s.length; i++) { h = ((h << 5) - h) + s.charCodeAt(i); h |= 0; }
    return h;
}

function escHtml(s) {
    if (!s) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function api(method, path, body) {
    var opts = {
        method: method,
        headers: { 'Content-Type': 'application/json' }
    };
    if (body !== undefined) opts.body = JSON.stringify(body);
    return fetch(API_BASE + path, opts).then(function (res) {
        if (!res.ok) {
            return res.text().then(function (txt) {
                throw new Error(txt || 'API Error');
            });
        }
        return res.json();
    });
}


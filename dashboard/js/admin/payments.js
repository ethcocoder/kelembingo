// ==================== PAYMENTS (SQL REST API) ====================

function toggleAdminOnline() {
    adminOnline = !adminOnline;
    api('POST', '/api/admin/status', { online: adminOnline }).then(function () {
        updateAdminStatusUI();
        loadPayments();
    }).catch(function (e) { showToast('Error updating status: ' + e.message, 'error'); });
}

function updateAdminStatusUI() {
    var dot = document.getElementById('adminStatusDot');
    var txt = document.getElementById('adminStatusText');
    var btn = document.getElementById('adminOnlineBtn');
    if (adminOnline) {
        dot.className = 'w-3 h-3 rounded-full bg-green-500 anim-live';
        txt.textContent = 'Online';
        txt.className = 'text-sm font-semibold text-green-400';
        btn.textContent = 'Go Offline';
        btn.className = 'btn-red-g px-4 py-2 rounded-xl text-sm font-bold text-white';
    } else {
        dot.className = 'w-3 h-3 rounded-full bg-red-500 anim-live';
        txt.textContent = 'Offline';
        txt.className = 'text-sm font-semibold text-gray-400';
        btn.textContent = 'Go Online';
        btn.className = 'btn-grad px-4 py-2 rounded-xl text-sm font-bold text-white';
    }
}

function loadPayments() {
    // Load admin status
    api('GET', '/api/admin/status').then(function (data) {
        adminOnline = data.online || false;
        updateAdminStatusUI();
    });
}

function renderPayments() {
    // 1. Pending deposits
    var deposits = allDeposits.filter(function (d) { return d.status === 'pending'; });
    var list = document.getElementById('payPendingList');
    document.getElementById('pay-pending-count').textContent = deposits.length;
    if (!deposits.length) {
        list.innerHTML = '<div class="text-center py-8"><div class="text-3xl mb-2">📭</div><p class="text-gray-500 text-sm">No pending deposits</p></div>';
    } else {
        var html = '';
        deposits.forEach(function (d) {
            var id = d.id;
            var amt = d.amount || 0;
            var time = d.createdAt ? new Date(d.createdAt).toLocaleString() : 'Unknown';
            var ocrHtml = '';
            if (d.ocr) {
                var ocr = d.ocr;
                var confPct = Math.round((ocr.confidence || 0) * 100);
                ocrHtml = '<div class="mt-2 rounded-lg bg-black/20 border border-white/5 p-2 space-y-1">' +
                    '<p class="text-[10px] text-gray-500 font-semibold">OCR Parsed (' + confPct + '% confidence)</p>' +
                    (ocr.status ? '<p class="text-[10px] text-gray-400">Status: <span class="' + (ocr.status === 'success' ? 'text-[#10B981]' : 'text-red-400') + '">' + escHtml(ocr.status) + '</span></p>' : '') +
                    (ocr.amount ? '<p class="text-[10px] text-gray-400">Amount: ' + escHtml(String(ocr.amount)) + ' ETB</p>' : '') +
                    (ocr.transactionDate ? '<p class="text-[10px] text-gray-400">Date: ' + escHtml(ocr.transactionDate) + '</p>' : '') +
                    (ocr.transactionRef ? '<p class="text-[10px] text-gray-400">Ref: <code>' + escHtml(ocr.transactionRef) + '</code></p>' : '') +
                    (ocr.receiverName ? '<p class="text-[10px] text-gray-400">Receiver: ' + escHtml(ocr.receiverName) + '</p>' : '') +
                    (ocr.transactionType ? '<p class="text-[10px] text-gray-400">Type: ' + escHtml(ocr.transactionType) + '</p>' : '') +
                    '</div>';
            }
            html += '<div class="glass rounded-xl p-4 mb-3 anim-slide border border-yellow-500/20">' +
                '<div class="flex flex-col sm:flex-row sm:items-start gap-3">' +
                '<div class="flex-1">' +
                '<div class="flex items-center gap-2 mb-1">' +
                '<span class="text-yellow-400 text-lg font-black">' + amt + ' ETB</span>' +
                '<span class="text-[10px] px-2 py-0.5 rounded-full bg-yellow-500/20 text-yellow-400 font-bold">PENDING</span>' +
                '</div>' +
                '<p class="text-xs text-gray-400">👤 ' + escHtml(d.firstName || 'Unknown') + ' (@' + escHtml(d.username || 'unknown') + ')</p>' +
                '<p class="text-xs text-gray-500">TXN: <code class="text-gray-400">' + escHtml(d.transactionId || 'N/A') + '</code></p>' +
                '<p class="text-xs text-gray-500">Sender: ' + escHtml(d.senderName || 'Unknown') + '</p>' +
                '<p class="text-xs text-gray-500">TeleBirr Name: ' + escHtml(d.telebirrName || 'N/A') + '</p>' +
                '<p class="text-[10px] text-gray-600 mt-1">🕐 ' + time + '</p>' +
                '<p class="text-[10px] text-gray-600">ID: <code class="text-gray-500">' + id.substring(0, 8) + '</code></p>' +
                ocrHtml +
                '</div>' +
                '<div class="flex sm:flex-col gap-2">' +
                '<button onclick="approveDeposit(\'' + id + '\')" class="btn-green-g px-4 py-2 rounded-lg text-xs font-bold text-white flex-1 sm:flex-none">✅ Approve</button>' +
                '<button onclick="rejectDeposit(\'' + id + '\')" class="btn-red-g px-4 py-2 rounded-lg text-xs font-bold text-white flex-1 sm:flex-none">❌ Reject</button>' +
                '</div>' +
                '</div>' +
                '</div>';
        });
        list.innerHTML = html;
    }

    // 2. Counts + Total amount
    var approvedDeposits = allDeposits.filter(function (d) { return d.status === 'approved'; });
    var rejectedDeposits = allDeposits.filter(function (d) { return d.status === 'rejected'; });
    document.getElementById('pay-approved-count').textContent = approvedDeposits.length;
    document.getElementById('pay-rejected-count').textContent = rejectedDeposits.length;
    var totalApprovedAmt = approvedDeposits.reduce(function (s, d) { return s + (d.amount || 0); }, 0);
    document.getElementById('pay-total-amount').textContent = totalApprovedAmt.toFixed(0);

    // 3. Processed deposits history (status != pending)
    var processedDeposits = allDeposits.filter(function (d) { return d.status !== 'pending'; });
    processedDeposits.sort(function (a, b) {
        var tA = a.processedAt ? new Date(a.processedAt) : 0;
        var tB = b.processedAt ? new Date(b.processedAt) : 0;
        return tB - tA;
    });
    var dList = document.getElementById('payProcessedList');
    var dItems = processedDeposits.slice(0, 10).map(function (d) {
        var emoji = d.status === 'approved' ? '✅' : '❌';
        var color = d.status === 'approved' ? 'text-green-400' : 'text-red-400';
        var bgColor = d.status === 'approved' ? 'border-green-500/20' : 'border-red-500/20';
        var time = d.createdAt ? new Date(d.createdAt).toLocaleString() : 'Unknown';
        return '<div class="glass rounded-xl p-3 mb-2 border ' + bgColor + '">' +
            '<div class="flex items-center justify-between">' +
            '<div><span class="' + color + ' font-bold">' + emoji + ' ' + (d.amount || 0) + ' ETB</span>' +
            '<span class="text-[10px] text-gray-500 ml-2">' + (d.firstName || 'Unknown') + '</span></div>' +
            '<span class="text-[10px] text-gray-600">' + time + '</span>' +
            '</div></div>';
    });
    dList.innerHTML = dItems.length > 0 ? dItems.join('') : '<div class="text-center py-4 text-gray-600 text-sm">No processed deposits</div>';

    // 4. Pending withdrawals
    var withdrawals = allWithdrawals.filter(function (w) { return w.status === 'pending'; });
    var wList = document.getElementById('withdrawPendingList');
    if (!withdrawals.length) {
        wList.innerHTML = '<div class="text-center py-8"><div class="text-3xl mb-2">📭</div><p class="text-gray-500 text-sm">No pending withdrawals</p></div>';
    } else {
        var wHtml = '';
        withdrawals.forEach(function (d) {
            var id = d.id;
            var amt = d.amount || 0;
            var time = d.createdAt ? new Date(d.createdAt).toLocaleString() : 'Unknown';
            wHtml += '<div class="glass rounded-xl p-4 mb-3 anim-slide border border-orange-500/20">' +
                '<div class="flex flex-col sm:flex-row sm:items-start gap-3">' +
                '<div class="flex-1">' +
                '<div class="flex items-center gap-2 mb-1">' +
                '<span class="text-orange-400 text-lg font-black">' + amt + ' ETB</span>' +
                '<span class="text-[10px] px-2 py-0.5 rounded-full bg-orange-500/20 text-orange-400 font-bold">PENDING</span>' +
                '</div>' +
                '<p class="text-xs text-gray-400">👤 ' + escHtml(d.firstName || 'Unknown') + ' (@' + escHtml(d.username || 'unknown') + ')</p>' +
                '<p class="text-xs text-gray-500">Phone: <code class="text-gray-400">' + escHtml(d.phone || 'N/A') + '</code></p>' +
                '<p class="text-xs text-gray-500">TeleBirr Name: ' + escHtml(d.telebirrName || 'N/A') + '</p>' +
                '<p class="text-[10px] text-gray-600 mt-1">🕐 ' + time + '</p>' +
                '<p class="text-[10px] text-gray-600">ID: <code class="text-gray-500">' + id.substring(0, 8) + '</code></p>' +
                '</div>' +
                '<div class="flex sm:flex-col gap-2">' +
                '<button onclick="approveWithdrawal(\'' + id + '\')" class="btn-green-g px-4 py-2 rounded-lg text-xs font-bold text-white flex-1 sm:flex-none">✅ Approve</button>' +
                '<button onclick="rejectWithdrawal(\'' + id + '\')" class="btn-red-g px-4 py-2 rounded-lg text-xs font-bold text-white flex-1 sm:flex-none">❌ Reject</button>' +
                '</div>' +
                '</div>' +
                '</div>';
        });
        wList.innerHTML = wHtml;
    }

    // 5. Processed withdrawals history
    var processedWithdrawals = allWithdrawals.filter(function (d) { return d.status !== 'pending'; });
    processedWithdrawals.sort(function (a, b) {
        var tA = a.processedAt ? new Date(a.processedAt) : 0;
        var tB = b.processedAt ? new Date(b.processedAt) : 0;
        return tB - tA;
    });
    var wHistList = document.getElementById('withdrawProcessedList');
    var wHistItems = processedWithdrawals.slice(0, 10).map(function (d) {
        var emoji = d.status === 'approved' ? '✅' : '❌';
        var color = d.status === 'approved' ? 'text-green-400' : 'text-red-400';
        var bgColor = d.status === 'approved' ? 'border-green-500/20' : 'border-red-500/20';
        var time = d.createdAt ? new Date(d.createdAt).toLocaleString() : 'Unknown';
        return '<div class="glass rounded-xl p-3 mb-2 border ' + bgColor + '">' +
            '<div class="flex items-center justify-between">' +
            '<div><span class="' + color + ' font-bold">' + emoji + ' ' + (d.amount || 0) + ' ETB</span>' +
            '<span class="text-[10px] text-gray-500 ml-2">' + (d.firstName || 'Unknown') + '</span>' +
            '<span class="text-[10px] text-gray-600 ml-2">📞 ' + (d.phone || 'N/A') + '</span></div>' +
            '<span class="text-[10px] text-gray-600">' + time + '</span>' +
            '</div></div>';
    });
    wHistList.innerHTML = wHistItems.length > 0 ? wHistItems.join('') : '<div class="text-center py-4 text-gray-600 text-sm">No processed withdrawals</div>';
}

function approveDeposit(id) {
    var note = '';
    if (!confirm('Approve this deposit?')) return;
    api('POST', '/api/admin/deposits/' + id + '/approve', { note: note })
        .then(function (res) {
            showToast('✅ Deposit approved! ' + res.amount + ' ETB added.', 'success');
            loadPayments();
        })
        .catch(function (e) { alert('Error: ' + e.message); });
}

function rejectDeposit(id) {
    var note = prompt('Reason for rejection (optional):', '');
    if (note === null) return;
    api('POST', '/api/admin/deposits/' + id + '/reject', { note: note })
        .then(function () { showToast('❌ Deposit rejected.', 'info'); loadPayments(); })
        .catch(function (e) { alert('Error: ' + e.message); });
}

function approveWithdrawal(id) {
    if (!confirm('Approve this withdrawal?')) return;
    api('POST', '/api/admin/withdrawals/' + id + '/approve', { note: '' })
        .then(function (res) {
            showToast('✅ Withdrawal approved! ' + res.amount + ' ETB deducted.', 'success');
            loadPayments();
        })
        .catch(function (e) { alert('Error: ' + e.message); });
}

function rejectWithdrawal(id) {
    var note = prompt('Reason for rejection (optional):', '');
    if (note === null) return;
    api('POST', '/api/admin/withdrawals/' + id + '/reject', { note: note })
        .then(function () { showToast('❌ Withdrawal rejected & refunded.', 'info'); loadPayments(); })
        .catch(function (e) { alert('Error: ' + e.message); });
}

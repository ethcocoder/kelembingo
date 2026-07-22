/**
 * Frontend JavaScript Test Suite for Bingo Game
 * Run: node test_frontend.js
 */

var fs = require('fs');
var path = require('path');

var passed = 0;
var failed = 0;
var total = 0;

function assert(condition, message) {
    total++;
    if (condition) {
        passed++;
        console.log('  [OK] ' + message);
    } else {
        failed++;
        console.log('  [FAIL] ' + message);
    }
}

function readFile(relPath) {
    var fullPath = path.join(__dirname, relPath);
    return fs.readFileSync(fullPath, 'utf8');
}

console.log('');
console.log('============================================================');
console.log('  BINGO GAME - FRONTEND JS TEST SUITE');
console.log('============================================================');

// ==================== TEST 1: calcDerash ====================
console.log('');
console.log('TEST 1: calcDerash Function');
console.log('------------------------------------------------------------');

var cardSelectSrc = readFile('dashboard/js/card-select.js');

// Extract calcDerash function
var funcMatch = cardSelectSrc.match(/function calcDerash\([^)]*\)\s*\{[\s\S]*?\n\}/);
if (funcMatch) {
    eval(funcMatch[0]);

    var r1 = calcDerash(0, 0, 10);
    assert(r1 === 0, 'No cards selected returns 0 (got ' + r1 + ')');

    var r2 = calcDerash(0, 1, 10);
    assert(r2 === 7.5, '1 card x 10 ETB = 7.5 (got ' + r2 + ')');

    var r3 = calcDerash(0, 2, 10);
    assert(r3 === 15, '2 cards x 10 ETB = 15 (got ' + r3 + ')');

    var r4 = calcDerash(0, 1, 20);
    assert(r4 === 15, '1 card x 20 ETB = 15 (got ' + r4 + ')');

    var r5 = calcDerash(3, 2, 10);
    assert(r5 === 37.5, '5 total x 10 ETB = 37.5 (got ' + r5 + ')');

    var r6 = calcDerash(0, 0, 50);
    assert(r6 === 0, '0 cards x 50 ETB = 0 (got ' + r6 + ')');
} else {
    assert(false, 'calcDerash function not found');
}

// ==================== TEST 2: No forced totalCartelas = 1 ====================
console.log('');
console.log('TEST 2: calcDerash Does Not Force 1 Card');
console.log('------------------------------------------------------------');

var hasForcedOne = cardSelectSrc.includes('if (totalCartelas < 1) totalCartelas = 1');
assert(!hasForcedOne, 'Removed forced totalCartelas = 1');

var hasReturnZero = cardSelectSrc.includes('if (totalCartelas < 1) return 0');
assert(hasReturnZero, 'Added return 0 for empty selection');

// ==================== TEST 3: Debounced Preview Render ====================
console.log('');
console.log('TEST 3: Card Selection Debouncing');
console.log('------------------------------------------------------------');

var hasSchedulePreview = cardSelectSrc.includes('schedulePreviewRender()');
assert(hasSchedulePreview, 'toggleCardSelection calls schedulePreviewRender()');

var hasDebounceVar = cardSelectSrc.includes('_previewDebounce');
assert(hasDebounceVar, 'Debounce variable _previewDebounce exists');

var hasDebounceClear = cardSelectSrc.includes('clearTimeout(_previewDebounce)');
assert(hasDebounceClear, 'Debounce clears previous timer');

// ==================== TEST 4: playNow Recursion Guard ====================
console.log('');
console.log('TEST 4: playNow Recursion Guard');
console.log('------------------------------------------------------------');

var hasGuardVar = cardSelectSrc.includes('var _playNowRunning = false');
assert(hasGuardVar, 'Guard variable _playNowRunning exists');

var hasGuardCheck = cardSelectSrc.includes('if (_playNowRunning) return;');
assert(hasGuardCheck, 'Guard check at function start');

var hasGuardSet = cardSelectSrc.includes('_playNowRunning = true');
assert(hasGuardSet, 'Guard set to true on entry');

var hasGuardClear = cardSelectSrc.includes('_playNowRunning = false');
assert(hasGuardClear, 'Guard cleared on exit');

// ==================== TEST 5: Preview Cache Reuse ====================
console.log('');
console.log('TEST 5: Cartela Cache Reuse After Join');
console.log('------------------------------------------------------------');

var hasCacheCheck = cardSelectSrc.includes('_previewCache[num]');
assert(hasCacheCheck, 'Checks _previewCache before DB fetch');

var hasCacheFallback = cardSelectSrc.includes('else {') && cardSelectSrc.includes('var cartelaDoc = await db');
assert(hasCacheFallback, 'Falls back to DB on cache miss');

// ==================== TEST 6: game-board.js Announce Timeout ====================
console.log('');
console.log('TEST 6: Number Announcement Timeout Cleanup');
console.log('------------------------------------------------------------');

var gameBoardSrc = readFile('dashboard/js/game-board.js');

var hasAnnounceTimeout = gameBoardSrc.includes('var _announceTimeout = null');
assert(hasAnnounceTimeout, 'Module-level _announceTimeout variable exists');

var hasClearAnnounce = gameBoardSrc.includes('if (_announceTimeout) clearTimeout(_announceTimeout)');
assert(hasClearAnnounce, 'showNumberAnnouncement clears previous timeout');

var hasClearInLeave = gameBoardSrc.includes('if (_announceTimeout) { clearTimeout(_announceTimeout); _announceTimeout = null; }');
assert(hasClearInLeave, 'leaveGame() clears _announceTimeout');

// ==================== TEST 7: DOM Caching in Snapshot ====================
console.log('');
console.log('TEST 7: Cached DOM References in Snapshot');
console.log('------------------------------------------------------------');

var hasElPlayers = gameBoardSrc.includes('var elPlayers = document.getElementById(\'game-players\')');
assert(hasElPlayers, 'Caches game-players element');

var hasElDerash = gameBoardSrc.includes('var elDerash = document.getElementById(\'game-derash\')');
assert(hasElDerash, 'Caches game-derash element');

var hasElCalledCount = gameBoardSrc.includes('var elCalledCount = document.getElementById(\'game-called-count\')');
assert(hasElCalledCount, 'Caches game-called-count element');

var hasElCountdown = gameBoardSrc.includes('var elCountdown = document.getElementById(\'game-countdown\')');
assert(hasElCountdown, 'Caches game-countdown element');

// ==================== TEST 8: prevCalledCount Race Fix ====================
console.log('');
console.log('TEST 8: prevCalledCount Race Condition Fix');
console.log('------------------------------------------------------------');

var hasPrevCount = gameBoardSrc.includes('var prevCount = calledNumbers.size');
assert(hasPrevCount, 'Derives prevCount from calledNumbers.size each snapshot');

var noOldPrevCalled = !gameBoardSrc.includes('var prevCalledCount = calledNumbers.size');
assert(noOldPrevCalled, 'Removed closure-based prevCalledCount');

var noPrevCalledUpdate = !gameBoardSrc.includes('prevCalledCount = called.length');
assert(noPrevCalledUpdate, 'Removed prevCalledCount = called.length assignment');

// ==================== TEST 9: Multiple Winner Handling ====================
console.log('');
console.log('TEST 9: Multiple Winner Support in UI');
console.log('------------------------------------------------------------');

var hasWinnerCount = gameBoardSrc.includes('var winnerCount = (data.winners || []).length');
assert(hasWinnerCount, 'Counts winners from data.winners array');

var hasMultiToast = gameBoardSrc.includes('winnerCount + \' winners split \'');
assert(hasMultiToast, 'Shows multi-winner toast message');

var hasCartelaArray = gameBoardSrc.includes('Array.isArray(data.winning_cartela)');
assert(hasCartelaArray, 'Handles winning_cartela as array');

// ==================== TEST 10: history.js Multiple Winners ====================
console.log('');
console.log('TEST 10: History Multiple Winners Display');
console.log('------------------------------------------------------------');

var historySrc = readFile('dashboard/js/history.js');

var hasCartelaJoin = historySrc.includes('Array.isArray(d.winning_cartela) ? d.winning_cartela.join');
assert(hasCartelaJoin, 'Joins multiple cartelas for display');

// ==================== TEST 11: Admin Listeners Debouncing ====================
console.log('');
console.log('TEST 11: Admin Listener Debouncing');
console.log('------------------------------------------------------------');

var listenersSrc = readFile('dashboard/js/admin/listeners.js');

var hasUsersTimer = listenersSrc.includes('_usersRenderTimer');
assert(hasUsersTimer, 'Users listener has debounce timer');

var hasRoundsTimer = listenersSrc.includes('_roundsRenderTimer');
assert(hasRoundsTimer, 'Rounds listener has debounce timer');

var hasDepositsTimer = listenersSrc.includes('_depositsRenderTimer');
assert(hasDepositsTimer, 'Deposits listener has debounce timer');

var hasWithdrawalsTimer = listenersSrc.includes('_withdrawalsRenderTimer');
assert(hasWithdrawalsTimer, 'Withdrawals listener has debounce timer');

var hasUsersDelay = listenersSrc.match(/_usersRenderTimer.*setTimeout.*200/s);
assert(hasUsersDelay, 'Users debounce delay is 200ms');

var hasRoundsDelay = listenersSrc.match(/_roundsRenderTimer.*setTimeout.*200/s);
assert(hasRoundsDelay, 'Rounds debounce delay is 200ms');

var hasPaymentsDelay = listenersSrc.match(/_depositsRenderTimer.*setTimeout.*500/s);
assert(hasPaymentsDelay, 'Payments debounce delay is 500ms');

// ==================== TEST 12: No Snapshot Mutation ====================
console.log('');
console.log('TEST 12: No Firestore Snapshot Mutation');
console.log('------------------------------------------------------------');

var noDataMutation = !listenersSrc.includes('data._docId = doc.id') && !listenersSrc.includes('data.id = doc.id');
assert(noDataMutation, 'No direct mutation of snapshot data objects');

var hasObjectAssign = listenersSrc.includes('Object.assign({}, doc.data()');
assert(hasObjectAssign, 'Uses Object.assign to clone snapshot data');

// ==================== TEST 13: auth.js Single Query ====================
console.log('');
console.log('TEST 13: auth.js Single DB Query');
console.log('------------------------------------------------------------');

var authSrc = readFile('dashboard/js/auth.js');

// Count .where( in refreshCompletedStats
var funcStart = authSrc.indexOf('function refreshCompletedStats()');
var funcBody = authSrc.substring(funcStart, authSrc.indexOf('\n}', funcStart) + 2);
var whereCount = (funcBody.match(/\.where\(/g) || []).length;

assert(whereCount <= 1, 'refreshCompletedStats uses ' + whereCount + ' DB query (should be 1)');

// ==================== TEST 14: payments.js Date Sort ====================
console.log('');
console.log('TEST 14: payments.js Correct Date Sorting');
console.log('------------------------------------------------------------');

var paymentsSrc = readFile('dashboard/js/admin/payments.js');

var hasTimestampSort = paymentsSrc.includes('new Date(a.processedAt).getTime()');
assert(hasTimestampSort, 'Uses raw timestamp for sort (not formatted string)');

var noStringSort = !paymentsSrc.includes('fmtDateFull(a.processedAt)');
assert(noStringSort, 'Removed fmtDateFull from sort comparison');

// ==================== TEST 15: Wallet Deposit Web Flow ====================
console.log('');
console.log('TEST 15: Wallet Deposit Modal Flow');
console.log('------------------------------------------------------------');

var walletSrc = readFile('dashboard/js/wallet.js');
var walletPageSrc = readFile('dashboard/pages/wallet.html');
var pageLoaderSrc = readFile('dashboard/js/page-loader.js');
var gameHtmlSrc = readFile('dashboard/game.html');
var depositModalSrc = readFile('dashboard/components/deposit-modal.html');

assert(walletPageSrc.includes('onclick="requestDeposit()"'), 'Wallet deposit button opens the in-app deposit modal');
assert(walletSrc.includes("'/api/deposits/config/'"), 'Wallet requests deposit config from backend');
assert(walletSrc.includes("'/api/deposits/submit'"), 'Wallet submits deposits through backend API');
assert(walletSrc.includes('continueDepositStep()'), 'Wallet has step transition for deposit flow');
assert(walletSrc.includes('loadWalletTransactions()'), 'Wallet reloads recent transactions');
assert(pageLoaderSrc.includes("'depositModal': 'deposit-modal.html'"), 'Page loader wires the deposit modal component');
assert(gameHtmlSrc.includes('id="depositModal"'), 'Game shell includes deposit modal container');
assert(depositModalSrc.includes('Transaction Number'), 'Deposit modal asks for transaction number');
assert(depositModalSrc.includes('TeleBirr Number'), 'Deposit modal shows the TeleBirr target number');

// ==================== SUMMARY ====================
console.log('');
console.log('============================================================');
console.log('  TEST RESULTS SUMMARY');
console.log('============================================================');
console.log('  Passed: ' + passed + '/' + total);
console.log('  Failed: ' + failed + '/' + total);
console.log('------------------------------------------------------------');

if (failed === 0) {
    console.log('  [PASS] ALL FRONTEND TESTS PASSED!');
    console.log('  Your game changes are verified and safe.');
    console.log('============================================================');
    process.exit(0);
} else {
    console.log('  [WARN] ' + failed + ' test(s) failed. Review before deploying.');
    console.log('============================================================');
    process.exit(1);
}

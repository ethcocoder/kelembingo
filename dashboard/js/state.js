// ==================== STATE ====================
let currentUser = null;
let currentScreen = 'home';
let currentRoundId = null;
let roundUnsubscribe = null;
let userUnsubscribe = null;
let statsUnsubscribe = null;
let selectedCartelas = [];
let myCartelas = {};
let autoMarkEnabled = false;
let calledNumbers = new Set();
let gameCountdownInterval = null;
let winCountdownInterval = null;
let listenerReady = false;
let isSpectator = false;
let serverTimeOffset = 0; // ms offset: serverTime - clientTime

// Returns the current time in ms, corrected to server clock
function serverNow() {
    return Date.now() + serverTimeOffset;
}

// Call once at startup to calibrate the offset
async function syncServerTime() {
    try {
        const before = Date.now();
        const res = await fetch((window.API_BASE || window.location.origin) + '/api/time');
        const after = Date.now();
        const data = await res.json();
        const serverMs = new Date(data.iso).getTime();
        // Account for network latency: assume server responded at midpoint
        const rtt = after - before;
        const clientMid = before + Math.floor(rtt / 2);
        serverTimeOffset = serverMs - clientMid;
        console.log('[TimeSync] offset=' + serverTimeOffset + 'ms, rtt=' + rtt + 'ms');
    } catch (e) {
        console.warn('[TimeSync] Failed, using local clock:', e);
        serverTimeOffset = 0;
    }
}

// Audio state
let musicEnabled = false;
let voiceEnabled = true;
let masterVolume = 0.8;
let bgMusicAudio = null;
let audioCtx = null;

// Telegram WebApp
const tg = window.Telegram?.WebApp;
if (tg) {
    tg.ready();
    tg.expand();
    tg.setHeaderColor('#0D1117');
    tg.setBackgroundColor('#0D1117');
}

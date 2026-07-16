// ==================== STATE ====================
let currentUser = null;
let currentScreen = 'home';
let currentRoundId = null;
let roundUnsubscribe = null;
let userUnsubscribe = null;
let statsUnsubscribe = null;
let selectionTimer = null;
let selectionDeadline = 0;
let selectedCartelas = [];
let myCartelas = {};
let autoMarkEnabled = false;
let calledNumbers = new Set();
let numberCallInterval = null;
let gameCountdownInterval = null;
let winCountdownInterval = null;
let selectionHandled = false;
let listenerReady = false;
let isSpectator = false;

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

// ==================== AUDIO ====================
var _lastNumberAudio = null;
function getAudioCtx() {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    return audioCtx;
}

function playNumberSound(num) {
    if (!voiceEnabled) return;
    if (!num || num < 1 || num > 75) return;
    try {
        var letter = getNumberLetter(num);
        if (!letter) return;
        if (_lastNumberAudio) { try { _lastNumberAudio.pause(); _lastNumberAudio.src = ''; } catch(e) {} }
        var src = 'public/audio/' + letter + num + '.mp3';
        var audio = new Audio(src);
        _lastNumberAudio = audio;
        audio.volume = masterVolume;
        audio.play().catch(function() {});
    } catch(e) {}
}

function playMarkSound() {
    try {
        const ctx = getAudioCtx();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain); gain.connect(ctx.destination);
        osc.type = 'sine';
        osc.frequency.setValueAtTime(1000, ctx.currentTime);
        gain.gain.setValueAtTime(0.15, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.15);
        osc.start(ctx.currentTime); osc.stop(ctx.currentTime + 0.15);
    } catch(e) {}
}

function playWinSound() {
    if (!voiceEnabled) return;
    try {
        const ctx = getAudioCtx();
        [523.25, 659.25, 783.99, 1046.50].forEach(function(freq, i) {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain); gain.connect(ctx.destination);
            osc.type = 'sine';
            osc.frequency.setValueAtTime(freq, ctx.currentTime + i * 0.15);
            gain.gain.setValueAtTime(masterVolume * 0.3, ctx.currentTime + i * 0.15);
            gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + i * 0.15 + 0.3);
            osc.start(ctx.currentTime + i * 0.15);
            osc.stop(ctx.currentTime + i * 0.15 + 0.3);
        });
    } catch(e) {}
}

function playBingoAnnouncement(cartelaNum) {
    if (!voiceEnabled) return;
    try {
        var num = parseInt(cartelaNum);
        if (num >= 1 && num <= 500) {
            var audio = new Audio('public/audio/cartela_bingo/cartela_' + num + '.mp3');
            audio.volume = masterVolume;
            audio.play().catch(function() {
                playBingoAnnouncementFallback(cartelaNum);
            });
        } else {
            playBingoAnnouncementFallback(cartelaNum);
        }
    } catch(e) {
        playBingoAnnouncementFallback(cartelaNum);
    }
}

function playBingoAnnouncementFallback(cartelaNum) {
    if (!voiceEnabled) return;
    try {
        if ('speechSynthesis' in window) {
            window.speechSynthesis.cancel();
            var msg = new SpeechSynthesisUtterance('Cartela ' + cartelaNum + ' Bingo!');
            msg.rate = 1.0;
            msg.pitch = 1.1;
            msg.volume = masterVolume;
            msg.lang = 'am-ET';
            var voices = window.speechSynthesis.getVoices();
            var amVoice = voices.find(function(v) { return v.lang.startsWith('am'); });
            if (!amVoice) amVoice = voices.find(function(v) { return v.lang.startsWith('en'); });
            if (amVoice) msg.voice = amVoice;
            window.speechSynthesis.speak(msg);
        }
    } catch(e) {}
}

function toggleMusic() {
    musicEnabled = !musicEnabled;
    var el = document.getElementById('music-icon');
    if (el) el.textContent = musicEnabled ? '\u{1F3B5}' : '\u{1F507}';
    if (musicEnabled) startBgMusic(); else stopBgMusic();
    localStorage.setItem('yegara_music', musicEnabled ? '1' : '0');
}

function toggleVoice() {
    voiceEnabled = !voiceEnabled;
    var el = document.getElementById('voice-icon');
    if (el) {
        if (voiceEnabled) {
            el.classList.remove('muted');
        } else {
            el.classList.add('muted');
        }
    }
    localStorage.setItem('yegara_voice', voiceEnabled ? '1' : '0');
}

function setVolume(val) {
    masterVolume = val / 100;
    var slider = document.getElementById('volume-slider');
    if (slider) slider.style.setProperty('--vol-pct', val + '%');
    localStorage.setItem('yegara_volume', val);
    if (bgMusicAudio) bgMusicAudio.volume = masterVolume * 0.3;
}

function startBgMusic() {
    if (bgMusicAudio) return;
    try {
        bgMusicAudio = new Audio('public/audio/bg_music.wav');
        bgMusicAudio.loop = true;
        bgMusicAudio.volume = masterVolume * 0.3;
        bgMusicAudio.play().catch(function() { bgMusicAudio = null; musicEnabled = false; });
    } catch(e) { bgMusicAudio = null; }
}

function stopBgMusic() {
    if (bgMusicAudio) { bgMusicAudio.pause(); bgMusicAudio.currentTime = 0; bgMusicAudio = null; }
}

function restoreAudioSettings() {
    if (localStorage.getItem('yegara_music') === '1') { musicEnabled = true; var m = document.getElementById('music-icon'); if (m) m.textContent = '\u{1F3B5}'; }
    if (localStorage.getItem('yegara_voice') === '0') {
        voiceEnabled = false;
        var v = document.getElementById('voice-icon');
        if (v) v.classList.add('muted');
    }
    var vol = localStorage.getItem('yegara_volume');
    if (vol) { masterVolume = parseInt(vol) / 100; var s = document.getElementById('volume-slider'); if (s) { s.value = vol; s.style.setProperty('--vol-pct', vol + '%'); } }
}

// ==================== AUDIO ====================
function getAudioCtx() {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    return audioCtx;
}

function playNumberSound() {
    if (!voiceEnabled) return;
    try {
        const ctx = getAudioCtx();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain); gain.connect(ctx.destination);
        osc.type = 'sine';
        osc.frequency.setValueAtTime(800, ctx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(1200, ctx.currentTime + 0.1);
        osc.frequency.exponentialRampToValueAtTime(600, ctx.currentTime + 0.2);
        gain.gain.setValueAtTime(0.3, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.4);
        osc.start(ctx.currentTime); osc.stop(ctx.currentTime + 0.4);
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

function toggleMusic() {
    musicEnabled = !musicEnabled;
    var el = document.getElementById('music-icon');
    if (el) el.textContent = musicEnabled ? '🎵' : '🔇';
    if (musicEnabled) startBgMusic(); else stopBgMusic();
    localStorage.setItem('yegara_music', musicEnabled ? '1' : '0');
}

function toggleVoice() {
    voiceEnabled = !voiceEnabled;
    var el = document.getElementById('voice-icon');
    if (el) el.textContent = voiceEnabled ? '🔊' : '🔇';
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
    if (localStorage.getItem('yegara_music') === '1') { musicEnabled = true; var m = document.getElementById('music-icon'); if (m) m.textContent = '🎵'; }
    if (localStorage.getItem('yegara_voice') === '0') { voiceEnabled = false; var v = document.getElementById('voice-icon'); if (v) v.textContent = '🔇'; }
    var vol = localStorage.getItem('yegara_volume');
    if (vol) { masterVolume = parseInt(vol) / 100; var s = document.getElementById('volume-slider'); if (s) { s.value = vol; s.style.setProperty('--vol-pct', vol + '%'); } }
}

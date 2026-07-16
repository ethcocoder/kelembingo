// ==================== FIREBASE INIT ====================
const firebaseConfig = {
    apiKey: "AIzaSyBzemnXChPIBwCSCBIT2TgfMVhYiHc_JrY",
    authDomain: "bingo-bot-5c708.firebaseapp.com",
    projectId: "bingo-bot-5c708",
    storageBucket: "bingo-bot-5c708.firebasestorage.app",
    messagingSenderId: "988357359269",
    appId: "1:988357359269:web:eb8ce31819d6853c717f4c",
    measurementId: "G-2P5YYZWKF1"
};
firebase.initializeApp(firebaseConfig);
const db = firebase.firestore();
const auth = firebase.auth();

auth.onAuthStateChanged(function(user) {
    if (!user) {
        auth.signInAnonymously().catch(function(e) {
            console.warn('Anonymous auth failed:', e);
        });
    }
});

// ============================================================
// Yegara Bingo – Client-Side Firestore Emulator
// Replaces the Google Firebase SDK with REST + WebSocket calls
// to our FastAPI backend (firestore_db / admin_api.py).
// All existing firebase.js consumers remain unchanged.
// ============================================================

(function () {
    // ── Detect API base URL ──────────────────────────────────
    const API_BASE = (function () {
        if (window.API_BASE) return window.API_BASE;
        const scripts = document.querySelectorAll('script');
        for (const s of scripts) {
            const m = (s.textContent || '').match(/API_BASE\s*=\s*['"]([^'"]+)['"]/);
            if (m) return m[1];
        }
        return window.location.origin;
    })();

    const WS_BASE = API_BASE.replace(/^http/, 'ws');

    // ── Helpers ──────────────────────────────────────────────
    function apiFetch(method, path, body) {
        const opts = {
            method,
            headers: { 'Content-Type': 'application/json' },
        };
        if (body !== undefined) opts.body = JSON.stringify(body);
        return fetch(API_BASE + path, opts).then(async r => {
            if (!r.ok) {
                const txt = await r.text();
                throw new Error(`API ${method} ${path} → ${r.status}: ${txt}`);
            }
            return r.json();
        });
    }

    // ── MockTimestamp ─────────────────────────────────────────
    class MockTimestamp {
        constructor(isoString) { this._iso = isoString; }
        toDate() { return new Date(this._iso); }
        static now() { return new MockTimestamp(new Date().toISOString()); }
        static fromDate(d) { return new MockTimestamp(d instanceof Date ? d.toISOString() : d); }
        get serverTimestamp() { return MockTimestamp.now(); }
    }

    // ── MockDocumentSnapshot ─────────────────────────────────
    class MockDocumentSnapshot {
        constructor(id, data, exists) {
            this.id = id;
            this._data = data || {};
            this.exists = exists !== false;
        }
        data() { return this._data; }
        get(field) { return this._data ? this._data[field] : undefined; }
    }

    // ── MockQuerySnapshot ────────────────────────────────────
    class MockQuerySnapshot {
        constructor(docs) {
            this.docs = docs; // array of MockDocumentSnapshot
            this.size = docs.length;
            this.empty = docs.length === 0;
        }
        forEach(fn) { this.docs.forEach(fn); }
    }

    // ── MockDocumentReference ────────────────────────────────
    class MockDocumentReference {
        constructor(collection, id) {
            this.id = id;
            this._collection = collection;
            this._path = `/api/db/${collection}/${id}`;
        }

        get() {
            return apiFetch('GET', this._path)
                .then(r => new MockDocumentSnapshot(r.id, r.data, true))
                .catch(e => {
                    if (e.message.includes('404')) return new MockDocumentSnapshot(this.id, {}, false);
                    throw e;
                });
        }

        set(data, opts) {
            const merge = !!(opts && opts.merge);
            return apiFetch('POST', this._path, { data, merge });
        }

        update(data) {
            return apiFetch('PATCH', this._path, { data });
        }

        delete() {
            return apiFetch('DELETE', this._path);
        }

        onSnapshot(onNext, onError) {
            let ws;
            const connect = () => {
                ws = new WebSocket(`${WS_BASE}/api/ws`);
                ws.onopen = () => {
                    ws.send(JSON.stringify({ collection: this._collection, doc_id: this.id }));
                };
                ws.onmessage = (ev) => {
                    const msg = JSON.parse(ev.data);
                    if (msg.type === 'snapshot') {
                        const snap = new MockDocumentSnapshot(msg.id, msg.data, msg.exists);
                        onNext(snap);
                    }
                };
                ws.onerror = e => onError && onError(e);
                ws.onclose = () => setTimeout(connect, 2000);
            };
            connect();
            // Also load immediately
            this.get().then(onNext).catch(e => onError && onError(e));
            return () => ws && ws.close();   // unsubscribe function
        }

        collection(sub) {
            return new MockCollectionReference(`${this._collection}/${this.id}/${sub}`);
        }
    }

    // ── MockQuery ────────────────────────────────────────────
    class MockQuery {
        constructor(collection, filters, orderField, orderDir, limitN) {
            this._collection = collection;
            this._filters = filters || [];
            this._orderField = orderField || null;
            this._orderDir = orderDir || 'ASCENDING';
            this._limitN = limitN || null;
        }

        _buildPath() {
            const params = new URLSearchParams();
            if (this._filters.length) params.set('filters', JSON.stringify(this._filters));
            if (this._orderField) { params.set('order_by', this._orderField); params.set('order_dir', this._orderDir); }
            if (this._limitN !== null) params.set('limit_n', this._limitN);
            const qs = params.toString();
            return `/api/db/${this._collection}${qs ? '?' + qs : ''}`;
        }

        get() {
            return apiFetch('GET', this._buildPath()).then(arr =>
                new MockQuerySnapshot(arr.map(r => new MockDocumentSnapshot(r.id, r.data, true)))
            );
        }

        where(field, op, value) {
            const newFilters = [...this._filters, [field, op, value]];
            return new MockQuery(this._collection, newFilters, this._orderField, this._orderDir, this._limitN);
        }

        orderBy(field, dir) {
            const d = (dir === 'desc' || dir === firebase.firestore.Query.DESCENDING) ? 'DESCENDING' : 'ASCENDING';
            return new MockQuery(this._collection, this._filters, field, d, this._limitN);
        }

        limit(n) {
            return new MockQuery(this._collection, this._filters, this._orderField, this._orderDir, n);
        }

        onSnapshot(onNext, onError) {
            let ws;
            const connect = () => {
                ws = new WebSocket(`${WS_BASE}/api/ws`);
                ws.onopen = () => {
                    ws.send(JSON.stringify({ collection: this._collection }));
                };
                ws.onmessage = (ev) => {
                    const msg = JSON.parse(ev.data);
                    if (msg.type === 'query_snapshot') {
                        const snap = new MockQuerySnapshot(
                            msg.docs.map(d => new MockDocumentSnapshot(d.id, d.data, true))
                        );
                        onNext(snap);
                    }
                };
                ws.onerror = e => onError && onError(e);
                ws.onclose = () => setTimeout(connect, 2000);
            };
            connect();
            // Initial load
            this.get().then(onNext).catch(e => onError && onError(e));
            return () => ws && ws.close();
        }
    }

    // ── MockCollectionReference ──────────────────────────────
    class MockCollectionReference extends MockQuery {
        constructor(name) {
            super(name, [], null, 'ASCENDING', null);
        }

        doc(id) {
            return new MockDocumentReference(this._collection, String(id));
        }

        add(data) {
            return apiFetch('POST', `/api/db/${this._collection}`, { data }).then(r =>
                new MockDocumentReference(this._collection, r.id)
            );
        }
    }

    // ── MockFirestore ────────────────────────────────────────
    class MockFirestore {
        collection(name) { return new MockCollectionReference(name); }
        document(path) {
            const [col, ...rest] = path.split('/');
            return new MockDocumentReference(col, rest.join('/'));
        }
        batch() {
            return {
                _ops: [],
                set(ref, data, opts) { this._ops.push(() => ref.set(data, opts)); return this; },
                update(ref, data) { this._ops.push(() => ref.update(data)); return this; },
                delete(ref) { this._ops.push(() => ref.delete()); return this; },
                commit() { return Promise.all(this._ops.map(op => op())); }
            };
        }
    }

    // ── MockAuth ─────────────────────────────────────────────
    class MockAuth {
        constructor() {
            this._listeners = [];
            this.currentUser = null;
            this._init();
        }
        _init() {
            let uid = localStorage.getItem('_bingo_anon_uid');
            if (!uid) { uid = 'anon_' + Math.random().toString(36).slice(2); localStorage.setItem('_bingo_anon_uid', uid); }
            this.currentUser = { uid, isAnonymous: true };
            setTimeout(() => this._listeners.forEach(fn => fn(this.currentUser)), 0);
        }
        onAuthStateChanged(fn) { this._listeners.push(fn); if (this.currentUser) setTimeout(() => fn(this.currentUser), 0); }
        signInAnonymously() { return Promise.resolve({ user: this.currentUser }); }
        signOut() { return Promise.resolve(); }
    }

    // ── firebase.firestore.FieldValue helpers ────────────────
    const FieldValue = {
        serverTimestamp: () => ({ __type: 'serverTimestamp', value: new Date().toISOString() }),
        increment: n => ({ __type: 'increment', value: n }),
        arrayUnion: (...items) => ({ __type: 'arrayUnion', values: items }),
        arrayRemove: (...items) => ({ __type: 'arrayRemove', values: items }),
        delete: () => ({ __type: 'delete' }),
    };

    // ── Expose global firebase object ────────────────────────
    const _firestore = new MockFirestore();
    const _auth = new MockAuth();

    window.firebase = {
        apps: [{}],
        initializeApp: () => {},
        firestore: () => _firestore,
        auth: () => _auth,
    };

    // Attach static helpers so existing code like
    //   firebase.firestore.FieldValue.serverTimestamp()
    // and firebase.firestore.Query.DESCENDING still work
    window.firebase.firestore.FieldValue = FieldValue;
    window.firebase.firestore.Timestamp = MockTimestamp;
    window.firebase.firestore.Query = { DESCENDING: 'DESCENDING', ASCENDING: 'ASCENDING' };

    // Also expose db + auth at top level (used by existing scripts)
    window.db = _firestore;
    window.auth = _auth;

    console.log('[Yegara Bingo] SQL emulator bridge loaded. API:', API_BASE);
})();

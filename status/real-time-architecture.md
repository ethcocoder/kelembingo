# REAL-TIME ARCHITECTURE

## Core Problem

When a player takes a cartela during the 35s selection window, **other players currently selecting should instantly see it as "TAKEN"**. This must work reliably on Render.

## Current Architecture

### Transport Layer: Socket.IO  [admin_api.py:32]

```python
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins=ALLOWED_ORIGINS)
```

- **Library**: python-socketio v5.11
- **Transports**: default `['polling', 'websocket']`
- **No adapter** (no Redis, no DB-backed room state)
- **Rooms are in-memory** only — tied to a single Python process

### Client Connection  [firebase.js:24]

```javascript
socket = io(API_BASE, {
    transports: ['polling'],       // ← polling only, no WebSocket
    reconnection: true,
    reconnectionDelay: 1000,
    reconnectionAttempts: Infinity,
});
```

Key: Client forces **polling** transport (long-polling HTTP). No WebSocket.

### Server-Side Broadcasting  [admin_api.py:1108]

```python
async def broadcast_event(collection, doc_id):
    snap = db.collection(collection).document(doc_id).get()
    # Emit to doc-level subscribers
    await sio.emit('snapshot', { 'id': snap.id, 'data': snap.to_dict(), 'exists': True },
                   room=f'{collection}:{doc_id}')
    # Emit to collection-level subscribers (ALL docs in collection!)
    all_docs = db.collection(collection).get()
    await sio.emit('query_snapshot', { 'docs': [...] },
                   room=collection)
```

Called from:
- `join_round` — after successful join  [admin_api.py:542]
- `_game_loop` — on status change, number call, bingo detection
- Various admin endpoints

### Client-Side onSnapshot  [firebase.js:186]

```javascript
MockDocumentReference.prototype.onSnapshot = function(callback) {
    var sub = { collection: this._collection, doc_id: this._docId };
    _activeSubscriptions.push(sub);
    socket.emit('subscribe', sub);
    socket.on('snapshot', function(msg) {
        if (msg.id === sub.doc_id) {
            callback(new MockDocumentSnapshot(msg.id, msg.data, msg.exists));
        }
    });
    return function unsubscribe() { /* remove from active subs, emit 'unsubscribe' */ };
};
```

## The Full Real-Time Path

```
Player B clicks "10 ETB", joins round
    │
    ├── POST /api/rounds/{id}/join
    │     └── engine.join_round() → DB write (taken_cartelas += ArrayUnion)
    │           └── system_events INSERT
    │
    └── broadcast_event('rounds', roundId)
          └── sio.emit('snapshot', { id, data, exists }, room='rounds:{roundId}')
                │
                ▼
          Server A's Socket.IO process emits to all clients in room 'rounds:{roundId}'
                │
                ├── Player A's browser (connected to Server A) ← RECEIVES
                │     └── onSnapshot callback fires
                │           └── taken_cartelas sync → UI updates
                │
                └── Player B's browser (same server) ← RECEIVES (but just joined)
```

## Why This Fails on Render

Render's Free plan **can spin up multiple replicas** (or rather, the user configured 2 services in `render.yaml`). Socket.IO rooms are **in-memory per process**.

### Scenario: Two Replicas

```
                         Internet
                            │
                    ┌───────┴───────┐
                    │               │
              Replica A          Replica B
            (Server A)          (Server B)
                    │               │
              ┌─────┴─────┐   ┌─────┴─────┐
              │           │   │           │
         Player A      Player B      Player C
         (selecting)   (joins)      (selecting)
```

1. Player B (on Replica A) joins → `join_round()` writes to the **shared database** → `broadcast_event()` emits via **Replica A's Socket.IO**
2. Player A (also on Replica A) receives the event → UI updates ✅
3. Player C (on Replica B) **does NOT receive the event** — it's in a different Socket.IO server with different in-memory rooms ❌

### Even with 1 Replica (Service)

The `render.yaml` defines **2 separate services** (`kelembingo` and `kelem-bingo-api`), both using the **same Dockerfile / same port**. This creates port conflicts and duplicate game loops regardless of replica count.

## Event Broadcasting Loop  [admin_api.py:369]

The server also runs a periodic broadcast loop that polls `system_events`:

```python
async def _event_broadcast_loop():
    while True:
        events = session.query(SystemEvent).filter(...).all()
        for event in events:
            await broadcast_event(event.collection, event.doc_id)
            # delete processed events
        await asyncio.sleep(0.5)
```

This runs **every 500ms** and re-broadcasts any recent events. This acts as a **partial polling fallback** within the same process, but does NOT solve the cross-replica problem because each replica has its own loop polling the same table.

## Cartela Pool Event  [admin_api.py:1153]

```python
async def broadcast_cartela_pool(round_id):
    snap = db.collection('rounds').document(round_id).get()
    data = snap.to_dict()
    await sio.emit('cartela_pool', {
        'taken_cartelas': data.get('taken_cartelas', []),
        'player_count': data.get('player_count', 0),
        'player_cartelas': data.get('players', {})
    }, room=f'rounds:{round_id}')
```

This is the **dedicated taken-cartela event**, emitted right after `join_round`. But it has the same cross-replica problem.

## Potential Fixes (Not Implemented)

| Approach | Pros | Cons | Status |
|----------|------|------|--------|
| **Socket.IO Redis adapter** | Proper cross-replica rooms | Requires Redis add-on ($) | Not tried |
| **REST polling** (was implemented, reverted) | Simple, works with any replicas | 1.5s delay, extra DB load | Reverted to a9201c5 |
| **Firestore onSnapshot** (if using real Firebase) | Real Firebase has cross-region sync | Real Firebase is not used | Would require architecture rewrite |
| **SSE with DB polling** | Lightweight, no extra deps | Still has polling delay | Not tried |
| **Remove multi-replica config** | Instant fix, zero code changes | Single point of failure | Possible, if Render Free allows |

## Socket.IO Events Summary

| Event | Direction | Payload | When |
|-------|-----------|---------|------|
| `connect` | Client→Server | — | On connect |
| `disconnect` | Client→Server | — | On disconnect |
| `subscribe` | Client→Server | `{ collection, doc_id? }` | On `onSnapshot` call |
| `unsubscribe` | Client→Server | `{ collection, doc_id? }` | On cleanup |
| `snapshot` | Server→Client | `{ id, data, exists }` | On document change (to doc room) |
| `query_snapshot` | Server→Client | `{ docs: [{ id, data }] }` | On collection change (to collection room) |
| `cartela_pool` | Server→Client | `{ taken_cartelas, player_count, player_cartelas }` | On player join (to round room) |

## Socket.IO Clients: Subscriptions  [firebase.js]

| Context | Subscription | Purpose |
|---------|-------------|---------|
| Card selection | `rounds:{roundId}` | Taken cartelas, player count, status transitions |
| Game board | `rounds:{roundId}` | Called numbers, game status, winners |
| Home page stats | `rounds` (collection) | Active round counts |
| User profile | `users:{userId}` | Balance/wallet updates |

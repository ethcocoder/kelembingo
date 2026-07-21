# KNOWN ISSUES & CONSTRAINTS

## Critical Issues

### 1. Taken Cartelas Not Visible Cross-Device ❌

**Current state**: `onSnapshot` → Socket.IO → in-memory rooms → **only works if all clients are on the same server process**.

If Render spins up a second instance, or if the user's two-service `render.yaml` splits traffic, Player A and Player B see different taken states.

**Root cause**: Socket.IO rooms are in-memory. No Redis adapter. Cross-replica broadcast is impossible.

### 2. Two Render Services = Conflicts ❌

`render.yaml` defines **two web services** (`kelembingo` + `kelem-bingo-api`) that both run the **same Dockerfile**. This causes:
- Telegram bot "409 Conflict" errors (two bot instances polling)
- Port 8000 conflicts on one of the services
- Duplicate game loops calling numbers twice
- Duplicate Socket.IO event broadcasting

**Fix**: Remove one service from `render.yaml`. Only one is needed — the API server serves both the backend and the dashboard static files.

### 3. Race Condition in join_round ❌

`round_engine.py:216-238` has a read-check-write pattern without atomic locking:
```
1. Read round doc (time T1)
2. Deduct wallet
3. Re-read round doc (time T2)
4. If cartelas taken → refund, error
5. Write cartelas (time T3)
```

If two concurrent requests both pass step 3 before either reaches step 5:
- Both get deducted
- Both write to `players` dict
- `ArrayUnion` prevents duplicate `taken_cartelas`, but the first user's picked cards might conflict with the second's

**Fix**: Use SQL-level locking (SELECT FOR UPDATE) or a database transaction that wraps the entire join operation.

## Moderate Issues

### 4. Socket.IO Has No Authentication ⚠️

Any client can connect, subscribe to any room, and receive all broadcasts. The API has no auth middleware.

### 5. Firebase Credentials in Git History ⚠️

The `.env` file with Firebase service account private key, API keys, and bot tokens was committed to git. Even if removed later, the secrets remain in the commit history.

**Fix**: Rotate all secrets. Use `git-filter-repo` to scrub history.

### 6. _event_broadcast_loop: Full Collection Broadcast ⚠️

`broadcast_event('rounds', roundId)` also broadcasts to the **collection-level room** sending ALL round documents (`db.collection('rounds').get()`) every time any round changes. With many rounds, this is a performance issue.

### 7. GAME_TIMER_SECONDS Mismatch ⚠️

Environment variable `GAME_TIMER_SECONDS=180` conflicts with code constant `SELECTION_DURATION=35`. The code constant wins for the selection phase, but the env var may affect other timer logic.

### 8. MAX_CARTELAS Constant ⚠️

`MAX_CARTELAS = 2` is defined in `constants.js` but also in `game/round_engine.py:28`. If one changes without the other, the client allows selecting more than the server accepts.

### 9. No Graceful Degradation on Socket.IO Disconnect ⚠️

If Socket.IO disconnects during the 35s selection window, the user sees no indication that real-time updates have stopped. Taken cartelas will not update, and the round status transition (selecting → playing) will not trigger navigation.

## Minor Issues

### 10. `serverNow()` Relies on `/api/time` Sync

The 35s timer uses `serverNow()` which is synced via `/api/time` on every page load and every 30s. If the sync fails, the timer drifts.

### 11. No Loading State for Grid

The cartela grid (500 tiles) loads all at once. For slow connections, there's a placeholder but no progressive loading.

### 12. Preview Cache Never Clears

`_previewCache` in `card-select.js` grows unbounded. Foreach page load, previously loaded cartela data stays in memory.

### 13. `confirmSelection()` Not Awaited

`playNow()` calls `showCardSelection(roundId, roundData)` without `await` at line 156 of `card-select.js`. This is intentional (non-blocking) but means `confirmSelection()` (called by the timer) may run before `showCardSelection` finishes setting up.

### 14. No WebSocket Transport on Client

The client forces `transports: ['polling']` (no WebSocket). This adds latency compared to WebSocket, which would be faster for the real-time taken-cartela sync.

### 15. Admin Dashboard Exposes All DB

The generic `GET /api/db/{collection}/{doc_id}` endpoint has no auth and exposes the entire database. Used for admin dashboard but accessible to anyone.

## Architectural Constraints

| Constraint | Impact |
|-----------|--------|
| No real Firebase | Must build all real-time infrastructure in-house |
| Socket.IO without adapter | Single-process only for real-time |
| Free Render plan | Sleep after 15 min idle, limited resources |
| SQLite (dev) | No concurrent write support (WAL mode helps but limited) |
| Two Telegram bots | Separate tokens required, both must be unique |
| No CI/CD pipeline | Manual deploy, no tests run on push |

# GIT HISTORY — EVOLUTION OF KEY FEATURES

## Real-Time Communication: 5 Generations

```
Gen 1: Raw WebSockets          (f1845e3)
  ↓
Gen 2: Socket.IO               (da02829)
  ↓
Gen 3: Firestore onSnapshot    (986409f)
  ↓
Gen 4: REST Polling            (2e015af..2139592)  ← REVERTED
  ↓
Gen 5: Back to onSnapshot      (a9201c5)           ← CURRENT HEAD
```

## Detailed Commit Timeline (Relevant to Taken Cartelas & Real-Time)

### Phase 1: Foundation (Months ago)
| Commit | Description |
|--------|-------------|
| `38d21ba` | "implement card selection logic for bingo rounds with real-time UI updates" — Initial card selection implementation |
| `860cdae` | "implement bingo game board UI, card selection logic, and real-time Firebase round synchronization" |
| `9ca3dcd` | "add client-side Firestore emulator to interface with backend via REST and WebSockets" — The `firebase.js` mock was born |
| `f1845e3` | "migrate admin dashboard to SQLAlchemy/REST, fix WebSocket query broadcasting" |

### Phase 2: WebSocket → Socket.IO
| Commit | Description |
|--------|-------------|
| `da02829` | **"replace WebSocket with Socket.IO"** — python-socketio server + Socket.IO CDN + cartela_pool event |
| `df9ab97` | CORS, script loading order, and WebSocket transport fixes |
| `ae8667e` | "add ASGI-level CORS middleware to fix Socket.IO and REST CORS failures" |
| `a10f488` | "permanent CORS fix — wrap entire ASGI app (including Socket.IO) with outer CORS middleware" |

### Phase 3: onSnapshot Real-Time (Recent commits)
| Commit | Description |
|--------|-------------|
| `ad2eff1` | **"emit broadcast_event from _game_loop so frontend gets real-time updates"** — Game loop now broadcasts to Socket.IO rooms |
| `986409f` | **"server-side bingo detection and real-time taken cards"** — Fixed broadcast_cartela_pool room name so taken cards turn orange in real-time |
| `c540641` | "kill card-select listener on confirm, guard stale onSnapshot callbacks" |
| `1d6e239` | "taken cartelas clickable with toast, Derash includes selections" |
| `4cb79c4` | "strengthen winner selection, real-time performance, and card selection UX: taken cards show orange with TAKEN label and pulse animation" |

### Phase 4: Timer & UX Evolution
| Commit | Description |
|--------|-------------|
| `0702388` | "real-time card selection timer synchronization" — serverNow() + 30s re-sync |
| `c047961` | "seamless card selection flow and dual-card preview" |
| `43238c2` | "remove 'Game starting soon', stay on card-select until round is playing, proper spectator flow" |
| `1eff553` | "navigate to game after confirm, fix derash to 7.5, fix real-time rejoin with fresh data" |
| `06ad4f3` | "auto-confirm 400ms after cartela selection (no waiting for 35s timer)" — **Note: this was later reverted in a6c854c** |
| `a6c854c` | "revert auto-confirm, keep 35s timer, add timer status to debug bar" |

### Phase 5: Polling Attempt (REVERTED, commits between a9201c5 and 2139592)
| Commit | Description |
|--------|-------------|
| `2e015af` | "add polling fallback for taken cartelas + remove orange from taken cards" — First polling implementation |
| `3f081a0` | "robust polling with logging, CSS fix" |
| `ab490b2` | "add debug bar + test script" |
| `06ad4f3` | "auto-confirm 400ms after selection" |
| `a6c854c` | "revert auto-confirm, keep 35s timer" |
| `1a006d8` | **"unified round polling (replaces socket.io + debug)"** — _startRoundPolling replaces onSnapshot entirely |
| `80c176c` | "fire first poll immediately" |
| `2139592` | "remove orphaned old inline code" — Bug fix, but too late |
| **`a9201c5`** | **← CURRENT HEAD** (after reset) |

## The Polling Implementation (What Was Reverted)

The reverted code added to `card-select.js`:

1. **`_startTakenPolling(roundId, grid)`** — `setInterval(async function() { ... }, 1500)` that:
   - Called `db.collection('rounds').doc(roundId).get()` every 1.5s
   - Checked `taken_cartelas` array → updated grid cell CSS
   - Auto-deselected if user had chosen a now-taken card
   - Called `updateSelectedInfo()` + `renderAllPreviews()` on change
   - Also updated player count / derash
   - Detected status transitions (completed → restart, playing → navigate)

2. **`_stopTakenPolling()`** — `clearInterval` wrapper

3. **Unified version** (`1a006d8`): Named `_startRoundPolling`, replaced `onSnapshot` entirely, also handled:
   - 0-player auto-cancellation
   - Spectator entry on playing transition
   - Rejoin detection

4. **Auto-confirm** (`06ad4f3`): `_confirmDebounce = setTimeout(() => confirmSelection(), 400)` after each toggle

5. **CSS**: Taken cards changed from orange (eye-catching) to dark/subtle (grayed out with "TAKEN" badge)

6. **Debug bar**: `_showDebugStatus()` with polling status, taken count, timestamp

7. **Server-side**: `POST /api/rounds/{round_id}/sync-marks` + `POST .../check-bingo/{user_id}` endpoints + `round_engine.py` methods

**Why it was reverted**: The orphaned inline async code in `_startRoundPolling` (commit `2139592` was supposed to fix it but it was too late — the user lost confidence and asked to revert to `a9201c5`).

## What's at a9201c5 (Current HEAD)

- **Pure Socket.IO + onSnapshot** for real-time (no polling)
- `onSnapshot` in `showCardSelection` is the sole mechanism for taken-cartela updates
- Taken cards use **orange styling** (`background: linear-gradient(135deg, #FF8C00, #FF6B00)`)
- No auto-confirm (35s timer only)
- No server-side mark tracking
- No debug bar

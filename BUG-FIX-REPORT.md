# Bug Fix Report — Kelem Bingo

## Date: 2026-07-18
## Scope: Page loading failures, game entry errors, timer logic, history page, admin delete

---

## BLOCKER Bugs

### B1: `startGameCountdown` / `stopGameCountdown` never defined
- **Files:** `game-board.js` (lines 5, 202, 304, 410), `state.js` (line 12)
- **Impact:** Every call throws `ReferenceError`. `setupGameBoard()` crashes immediately → game board never renders. `leaveGame()` crashes → player stuck. `handleRoundCompleted()` crashes → no redirect.
- **Fix:** Implement both functions in `game-board.js`. `startGameCountdown(nextMs)` counts down using `serverNow()` and updates `#game-timer`. `stopGameCountdown()` clears the interval.

### B2: `await` inside non-async `onSnapshot` callback
- **Files:** `card-select.js` (lines 133, 163, 168)
- **Impact:** Parse error (entire file fails to load) OR silent failure (await ignored, DOM ops race page load). Either way, the card-select-to-game transition is broken.
- **Fix:** Make the `onSnapshot` callback `async`, or restructure to avoid `await` inside the callback (use `.then()` chains instead).

### B3: Player can never leave the game
- **Files:** `game-board.html` (lines 3, 134), `game-board.js` (line 410), `ui.js` (line 32)
- **Impact:** `leaveGame()` calls `stopGameCountdown()` which throws (B1). The `navigateTo('home')` after it never executes.
- **Fix:** Implementing B1 fixes this. Also add try/catch around `leaveGame()`.

---

## CRITICAL Bugs

### B4: `loadHistory()` crashes on null `currentUser`
- **Files:** `history.js` (line 19), `main.js` (line 17)
- **Impact:** `initUser()` is not awaited → `currentUser` is null when history loads → TypeError → blank page.
- **Fix:** Add null guard: `if (!currentUser) return;` at start of `loadHistory()`.

### B5: Double `loadHistory()` call
- **Files:** `main.js` (lines 33-37), `ui.js` (line 50)
- **Impact:** Both `pageLoaded` event and `navigateTo` call `loadHistory()` → race condition → crash on second call when DOM elements already removed.
- **Fix:** Remove `loadHistory()` from `pageLoaded` handler. Only call from `navigateTo()`.

### B6: `navigateTo('game')` not awaited in `enterSpectatorMode`
- **Files:** `card-select.js` (lines 272-274)
- **Impact:** `setupGameBoard()` and `listenToRound()` run before game page HTML is loaded → null DOM refs.
- **Fix:** Make `enterSpectatorMode` async and await `navigateTo('game')`.

### B7: WebSocket reconnection leak
- **Files:** `firebase.js` (lines 100-121, 167-190)
- **Impact:** `unsubscribe()` closes WebSocket → triggers `onclose` → reconnects after 2s → leaked connection.
- **Fix:** Add a `stopped` flag; check it in `onclose` handler before reconnecting.

---

## HIGH Bugs

### B8: `navigateTo('home')` not awaited in setTimeout callbacks
- **Files:** `game-board.js` (lines 317, 322, 325, 371)
- **Fix:** Use async IIFE in setTimeout: `setTimeout(async () => { await navigateTo('home'); }, ms)`

### B9: No timer display on card-select screen
- **Files:** `card-select.html`, `card-select.js`
- **Fix:** Add timer element to card-select.html. Show countdown based on `round.created_at` + SELECTION_DURATION.

### B10: History shows individual results, not 3 recent winners
- **Files:** `history.html`, `history.js`
- **Fix:** Rewrite to query completed rounds with winners, show 3 most recent winner names + prizes as motivational display.

### B11: Server has no `selection_deadline` field
- **Files:** `round_engine.py`, `admin_api.py`
- **Fix:** Add `SELECTION_DURATION = 60` constant. Store `selection_deadline` in round document. Game loop waits for deadline OR first card selection.

### B12: `screen-transition` class never removed
- **Files:** `ui.js` (line 43)
- **Fix:** Remove class before re-adding: `target.classList.remove('screen-transition'); void target.offsetWidth; target.classList.add('screen-transition');`

---

## MEDIUM Bugs

### B13-B16: Missing null-checks in helpers/auth/game-board
- `showToast()`, `showLoading()`, `hideScreen()` — add null guards
- `auth.js` — null-check `user-greeting`, `regName`, `regPhone`
- `game-board.js` — null-check DOM elements in `setupGameBoard()`, `showWinModal()`

### B17: No debounce on `loadHistory()`
- **Fix:** Add a loading flag guard.

### B18: `loadMyCartelas` error swallowed
- **Files:** `game-board.js` (line 400)
- **Fix:** Re-throw in catch block so caller knows it failed.

---

## Admin Delete Users
- **Status:** ALREADY FULLY IMPLEMENTED
- Delete button, confirmation modal, `requestDeleteUser()`, `confirmDeleteUser()`, backend DELETE endpoint all exist.
- No changes needed.

---

## Implementation Order
1. B1 (stopGameCountdown/startGameCountdown) → fixes B3
2. B2 (async onSnapshot) → fixes card-select-to-game flow
3. B4 + B5 (history null guard + remove double call)
4. B7 (WebSocket leak)
5. B9 + B10 + B11 (timer + history rewrite + server deadline)
6. B6 + B8 (await navigateTo issues)
7. B12 (screen-transition)
8. B13-B18 (null-safety, debounce, error handling)

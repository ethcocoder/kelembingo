# CARD SELECTION FLOW — COMPLETE ANALYSIS

## End-to-End Flow: Stake Click → Round Join

```
User clicks "10 ETB" on home page
    │
    ▼
playNow(10)                              [card-select.js:12]
    │
    ├── Set loading overlay "Finding game..."
    ├── Query `rounds` for active round:
    │     .where('status','in',['selecting','playing'])
    │     .where('stake','==',stake)
    │     .orderBy('created_at','desc')
    │     .limit(1)
    │
    ├── [No round] ──► CREATE with status='selecting', deadline=now+35s
    │                     └── showCardSelection(id, data)
    │
    └── [Found round] ──► Check status:
          ├── 'playing' + 0 players ──► mark completed, restart
          ├── 'playing' + is player  ──► rejoin game
          ├── 'playing' + not player ──► spectator mode
          ├── 'selecting' + already joined ──► rejoin
          ├── 'selecting' + expired deadline ──► spectate or restart
          └── 'selecting' + fresh ──► showCardSelection(id, data)
```

## showCardSelection(roundId, roundData)  [card-select.js:168]

### Phase 1 — Setup
- `selectedCartelas = []`, `_originalPlayWallet = currentUser.play_wallet`
- Update DOM: stake, wallets, derash estimate
- **Start 35s timer**: `startSelectionCountdown(deadlineMs)` — fires every 200ms

### Phase 2 — Load Cartela Grid
- Query `cartelas_master` collection (orderBy `number`)
- For each of 500 cartelas, create a `div.card-tile`:
  - **Available**: onclick → `toggleCardSelection(num, cell)`
  - **Taken** (in `roundData.taken_cartelas`): class `taken taken-flash`, toast-only onclick

### Phase 3 — Real-Time Listener
- `roundUnsubscribe = db.collection('rounds').doc(roundId).onSnapshot(callback)`
- Callback handles:
  1. **Taken cartelas sync**: marks newly-taken tiles, auto-deselects if user had chosen them
  2. **Player count / derash update**
  3. **Round completed/cancelled** → restart `playNow()`
  4. **Round playing** → navigate to game board (or spectator)

## toggleCardSelection(num, cell)  [card-select.js:360]

```
User taps a cartela tile
    │
    ├── [Already selected] ──► DESELECT: remove from array, revert CSS
    │
    └── [Not selected] ──► SELECT:
          ├── CHECK: selectedCartelas.length >= MAX_CARTELAS (2)?
          ├── CHECK: budget (play_wallet / stake)?
          ├── ADD to selectedCartelas[]
          ├── CSS: 'card-tile selected'
          │
          └── updateSelectedInfo() + schedulePreviewRender()
```

## confirmSelection()  [card-select.js:532]

Called by:
- **35s timer expiry** (auto-confirm, if selections exist)
- (No manual confirm button — purely timer-based)

Steps:
1. **Re-fetch round** to get latest `taken_cartelas`
2. **Remove any cards taken** by others since selection
3. **Check duplicates**
4. **POST /api/rounds/{roundId}/join** with `{ user_id, cartela_numbers, user_name }`
5. **On success**: load cartela data, navigate to game board
6. **On error**: if "Spectating/already started/finished" → re-queue with `playNow()`

## The 35s Timer  [game-board.js:95]

```
startSelectionCountdown(deadlineMs)
    │
    └── setInterval(every 200ms):
          ├── remaining = max(0, ceil((deadlineMs - serverNow()) / 1000))
          ├── Update DOM: #cs-timer, #cs-timer-bar
          ├── If remaining <= 10s: bar turns red
          │
          └── If remaining <= 0:
                ├── selections exist → confirmSelection()
                └── no selections → re-queue playNow()
```

Key: `serverNow()` = `Date.now() + serverTimeOffset` (synced via `/api/time` every 30s)

## Key State Variables  [state.js]

| Variable | Value | Purpose |
|----------|-------|---------|
| `SELECTION_DURATION` | 35 | Seconds for selection phase |
| `MAX_CARTELAS` | 2 | Max cards per player |
| `VALID_STAKES` | [10, 20] | Allowed bet amounts |
| `currentRoundId` | String | Active round doc ID |
| `selectedCartelas` | Array | User's current picks (max 2) |
| `_originalPlayWallet` | Number | Wallet snapshot at selection start |
| `listenerReady` | Boolean | Guard for rejoin flow |

## UI Elements

| Element ID | Purpose |
|-----------|---------|
| `cs-timer` | Countdown display (e.g. "23s") |
| `cs-timer-bar` | Progress bar (green → red at 10s) |
| `cs-stake` | Current stake amount |
| `cs-derash` | Estimated pool payout |
| `cs-main-wallet` | Main balance |
| `cs-play-wallet` | Play wallet (shows pending deduction) |
| `cs-selected-count` | "1/2" display |
| `cs-selected-total` | Cost of selected cards |
| `cs-preview-container` | 5x5 preview of selected cards |
| `cs-loading` | Loading overlay |
| `card-select-screen` | The entire card selection modal |

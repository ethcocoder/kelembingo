# DATABASE ARCHITECTURE

## Overview

The app uses a **custom SQL-backed Firestore emulator** (`firestore_db.py`) instead of real Firebase/Firestore. All data lives in SQLite (dev) or PostgreSQL (production) in a single `firestore_documents` table.

## The MockFirestoreClient  [firestore_db.py:91]

A `MockFirestoreClient` object is created as a global `db` in `config.py:44` and shared across:
- `api/admin_api.py` — REST endpoints + game loop
- `game/round_engine.py` — round management
- `handlers/user_manager.py` — user CRUD
- `bot.py` — Telegram bot user operations
- `admin_bot.py` — admin operations

## SQL Tables  [firestore_db.py:34]

### `firestore_documents`
| Column | Type | Description |
|--------|------|-------------|
| `collection` | VARCHAR(255), PK | Collection name (e.g., 'rounds', 'users') |
| `doc_id` | VARCHAR(255), PK | Document ID (UUID, user ID, or sequential ID) |
| `data` | TEXT | JSON-serialized document fields |
| `created_at` | TIMESTAMP | Auto-set on creation |
| `updated_at` | TIMESTAMP | Auto-updated on every change |

### `system_events`
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER, PK, AUTO | Sequential event ID |
| `collection` | VARCHAR(255) | Collection that changed |
| `doc_id` | VARCHAR(255) | Document that changed |
| `event_type` | VARCHAR(50) | 'created', 'updated', 'deleted' |
| `created_at` | TIMESTAMP | When the event occurred |

## Collections (Logical)

| Collection | Purpose | Key Fields |
|-----------|---------|------------|
| `rounds` | Game rounds | status, stake, players{}, taken_cartelas[], called_numbers[], player_count, winners[], prize_per_winner, selection_deadline, created_at |
| `users` | User accounts | balance, play_wallet, wins, losses, is_playing, phone, telebirr_name, deposits[], created_at |
| `cartelas_master` | 500 bingo cards | number (1-500), cartela[] (25-element flat array, 0=free) |
| `deposits` | Deposit requests | user_id, amount, status (pending/approved/rejected), admin_message, created_at |
| `withdrawals` | Withdrawal requests | user_id, amount, status, phone, admin_message, created_at |
| `games` | Legacy single-player games | — |
| `bot_content` | Telegram bot messages | Keys for each bot message, JSON body |
| `settings` | App settings | Various cfg_* keys |
| `system` | System flags | admin_status (online/offline) |

## How Taken Cartelas Flow

### Write Path (when Player B joins a round)

```
POST /api/rounds/{id}/join
    │
    ▼
engine.join_round(round_id, user_id, cartela_numbers, user_name)
    │  [round_engine.py:159]
    │
    ├── 1. Validate cartela count (1-2)
    ├── 2. Validate cartela numbers (1-500)
    ├── 3. Check no duplicates in selection
    ├── 4. Read round doc from DB
    ├── 5. Check round status == 'selecting'
    ├── 6. Check cartelas not already in taken_cartelas[]
    ├── 7. Check user not already joined
    ├── 8. Deduct play_wallet from user doc (Increment(-cost))
    ├── 9. Second read of round doc (race condition check)
    ├── 10. If cartelas were taken between 4 and 9 → refund, return error
    │
    └── 11. Update round doc:
            players.{uid} = { cartelas, name, joined_at }
            player_count += Increment(len(cartelas))
            taken_cartelas += ArrayUnion(cartela_numbers)
                │
                ▼
            DocumentRef.update()
                │  [firestore_db.py:381]
                │
                ├── Parse dotted paths
                ├── Handle Increment (numeric addition)
                ├── Handle ArrayUnion (append non-duplicates to list)
                └── INSERT into system_events (event_type='updated')
```

### Read Path (when Player A's onSnapshot fires)

```
onSnapshot callback fires
    │
    ▼
MockDocumentReference.onSnapshot(cb) → Socket.IO subscribe('rounds:{id}')
    │  [firebase.js:186]
    │
    └── Server emits 'snapshot' event:
          sio.emit('snapshot', {id, data, exists}, room='rounds:{id}')
              │  [admin_api.py:1120]
              │
              └── Client callback receives:
                    new MockDocumentSnapshot(data)
                        │
                        ▼
                    Taken sync logic:
                      - Read rd.taken_cartelas[]
                      - Compare with grid cells
                      - Mark newly-taken tiles
                      - Auto-deselect if user had chosen them
```

## Race Condition Window  [round_engine.py:216-238]

```
Step 4: Read round doc                  ←─ Time T1
  ... (other validations, deduct wallet)
Step 9: Re-read round doc               ←─ Time T2
Step 10: If cartelas taken between T1-T2 → refund, error
Step 11: Write cartelas to DB           ←─ Time T3
```

The gap between T2 and T3 is NOT protected. If two requests are concurrent:
- Both pass step 9 (neither sees the other's cartelas yet)
- Both proceed to step 11
- `ArrayUnion` prevents duplicates in `taken_cartelas`, but **both users are charged**
- The `players` dict would have both users, but the second user's cartelas might overlap with the first's

**Mitigation**: `ArrayUnion` prevents corrupt data, but the wallet deduction (step 8) is **not rolled back** for the second user. This is a real bug.

## Database Location

- **Local dev**: `kelembingo.db` (SQLite file in project root)
- **Production**: PostgreSQL via `DATABASE_URL` env var (connection pooling with `pool_pre_ping=True`)

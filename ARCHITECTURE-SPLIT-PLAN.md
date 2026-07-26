# Kelem Bingo — Microservices Split Architecture Plan

## 1. Current State: The Monolith Problem

### Single service on Render free (512MB RAM)
```
┌──────────────────────────────────────────────────┐
│               kelembingo.onrender.com            │
│                    512MB RAM                      │
│                                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ Main     │  │ Game Bot │  │ Admin Bot│       │
│  │ Process  │  │ Process  │  │ Process  │       │
│  │ FastAPI  │  │ ptb      │  │ ptb      │       │
│  │ SocketIO │  │ httpx    │  │ httpx    │       │
│  │ GameLoop │  │ SQLAlch  │  │ SQLAlch  │       │
│  │ Backup   │  │ PIL      │  │          │       │
│  │ SQLite   │  │ 50-80MB  │  │ 50-80MB  │       │
│  │100-150MB │  │          │  │          │       │
│  └──────────┘  └──────────┘  └──────────┘       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ Support  │  │ Admin    │  │ Backup   │       │
│  │ Bot Proc │  │ Supp Bot │  │ Sched    │       │
│  │ 50-80MB  │  │ 50-80MB  │  │ Process  │       │
│  └──────────┘  └──────────┘  └──────────┘       │
│                                                   │
│  Total: ~350-450MB (hits limit with 4+ users)    │
└──────────────────────────────────────────────────┘
```

### RAM Hotspots

| Component | RAM | Why |
|-----------|-----|-----|
| **5 subprocesses** (bots) | ~250-350MB | Each loads full Python + python-telegram-bot + SQLAlchemy + httpx |
| **Main API process** | ~100-150MB | FastAPI + uvicorn + Socket.IO + round_engine + all caching |
| **Cartela cache (×6)** | ~30-50MB × 6 | `_CARTELA_CACHE` duplicated in every process |
| **SQLite (WAL + shared memory)** | ~20-50MB | In-memory pages, WAL file, connection pools |
| **Socket.IO rooms** | ~5-20MB | Per-connection overhead, room subscriptions |

With 4 users connecting via Socket.IO and 5 subprocesses, the 512MB ceiling is easily hit.

---

## 2. Proposed Architecture: 4 Services + Vercel

### Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Vercel (free)                                │
│  kelembingo.vercel.app                                              │
│  ┌─────────────────────────────────────────────────────────┐       │
│  │  Static frontend (HTML, JS, CSS, audio)                  │       │
│  │  Socket.IO client → connects to GATEWAY                  │       │
│  └─────────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────────┘
         │
         │ Socket.IO (real-time game updates)
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  GATEWAY  —  kelembingo-gateway.onrender.com        │
│                        512MB RAM (Render free)                      │
│                                                                     │
│  ONE PROCESS (no subprocesses):                                     │
│  ┌──────────────────────────────────────────────────────┐          │
│  │ • FastAPI REST API (all CRUD endpoints)               │          │
│  │ • Socket.IO server (frontend real-time)               │          │
│  │ • SQLite database (firestore_db.py — source of truth) │          │
│  │ • Backup bot scheduler (@kelembackupbot)              │          │
│  │ • Background round monitor (creates new rounds)       │          │
│  │ • NO bot polling, NO python-telegram-bot              │          │
│  │   RAM estimate: ~120-180MB                            │          │
│  └──────────────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────────────┘
         │                          │                      │
         │ HTTP REST                │ HTTP REST            │ HTTP REST
         ▼                          ▼                      ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  BOT SERVICE     │  │  GAME ENGINE 10  │  │  GAME ENGINE 20  │
│  Render free     │  │  Render free     │  │  Render free     │
│  512MB RAM       │  │  512MB RAM       │  │  512MB RAM       │
│                  │  │                  │  │                  │
│  • Game bot      │  │ • Runs _game_loop│  │ • Runs _game_loop│
│  • Admin bot     │  │   for stake=10   │  │   for stake=20   │
│  • Support bot   │  │ • Calls gateway  │  │ • Calls gateway  │
│  • Admin supp    │  │   API for every  │  │   API for every  │
│  • NO DB         │  │   DB operation   │  │   DB operation   │
│  • NO FastAPI    │  │ • round_engine   │  │ • round_engine   │
│  • NO SocketIO   │  │   logic stays    │  │   logic stays    │
│  • HTTP client   │  │   HERE (not on   │  │   HERE (not on   │
│    → gateway     │  │   gateway)       │  │   gateway)       │
│  • RAM: ~80-120MB│  │ • RAM: ~60-100MB │  │ • RAM: ~60-100MB │
└──────────────────┘  └──────────────────┘  └──────────────────┘
```

### Why This Split Makes Sense

| Current (Monolith) | After Split | Benefit |
|-------------------|-------------|---------|
| 6 processes share 512MB | Each service gets its own 512MB | **~3GB total RAM capacity** |
| Bots + API + games compete for RAM | Bots isolated from game engine | No interference between heavy processes |
| Python-telegram-bot in same process as game loop | PTB only on BOT service | Frees fastapi process from heavy library |
| Game loop competes with bots for CPU | Game engine gets dedicated CPU | Consistent number-calling timing |
| All stake rounds on one process | Stake 10 and 20 on separate processes | Load balancing, one can crash without affecting the other |

---

## 3. Component Breakdown

### Service A: Gateway (kelembingo-gateway.onrender.com)

**Role:** Data layer, real-time push, backup, REST API

**What it runs:**
- `api/admin_api.py` (REST endpoints — all 50+ routes)
- `firestore_db.py` (SQLite — source of truth)
- `backup_common.py` (backup scheduler, restore)
- `config.py` (env vars)
- Socket.IO server (real-time client updates)
- Background round monitor (creates new rounds when old ones end)

**What it does NOT run:**
- Any python-telegram-bot code
- No `bot.py`, `admin_bot.py`, `support_bot.py`, `admin_support_bot.py`
- No game loop (`_game_loop` — stays in game engine services)
- No `round_engine.py` (stays in game engine services)

**New endpoints required:**
```python
POST /api/users/create        # Bot registers user → gateway creates in DB
POST /api/rounds/{id}/status  # Game engine reports round status
POST /api/rounds/{id}/call    # Game engine calls a number
POST /api/rounds/{id}/winner  # Game engine declares winner
GET  /api/engine/task         # Game engine asks "what round should I process?"
```

**RAM estimate:** ~120-180MB (one process, no PTB)

---

### Service B: Bot Service (kelembingo-bot.onrender.com)

**Role:** Telegram bot polling + user interaction

**What it runs:**
- `bot.py` (game bot — user registration, deposits, withdrawals, transfer, balance)
- `admin_bot.py` (admin bot — approve/reject deposits/withdrawals)
- `support_bot.py` (support bot — user support tickets)
- `admin_support_bot.py` (admin support bot — admin replies)
- `support_common.py` (shared support helpers)
- `handlers/user_manager.py` (user data helpers)
- `handlers/bot_content.py` (message text management)
- `handlers/admin_handlers.py`
- `handlers/withdraw_handler.py`
- **gateway_client.py** (NEW — HTTP client wrapper → gateway)

**What it does NOT run:**
- No FastAPI / uvicorn
- No Socket.IO
- No `firestore_db.py` (no local DB at all)
- No game loop
- No backup scheduler

**How data access changes:**
```python
# CURRENT (bot.py):
user_ref = db.collection('users').document(str(uid))
user_doc = user_ref.get()
if user_doc.exists:
    data = user_doc.to_dict()

# NEW (bot.py):
user_data = await gateway.get_user(uid)
if user_data:
    data = user_data
```

**RAM estimate:** ~80-120MB (4 bot subprocesses, each ~20-30MB without SQLAlchemy)

---

### Service C: Game Engine — Stake 10 (kelembingo-engine-10.onrender.com)

**Role:** Run the game loop for all stack-10 rounds

**What it runs:**
- `game/round_engine.py` (RoundEngine class — smart predictor, winner detection)
- `game/engine.py` (engine utilities)
- `game/prediction.py` (predetermined winner algorithm)
- `game/__init__.py`
- `gateway_client.py` (NEW — HTTP client → gateway)
- A thin async main loop (NEW — `run_engine_10.py`):
  ```python
  async def main():
      while True:
          round_info = await gateway.get_next_round(stake=10)
          if round_info:
              await run_game_loop(round_info.id)
          await asyncio.sleep(1)
  ```

**What it does NOT run:**
- No FastAPI / Socket.IO
- No `firestore_db.py` (no local DB)
- No python-telegram-bot
- No bot code at all

**How the game loop changes:**
```python
# CURRENT (admin_api.py — reads/writes DB directly):
round_doc = db.collection('rounds').document(round_id).get()
engine.call_number(round_id)
# → engine reads/writes DB directly via firestore_db.py

# NEW (run_engine_10.py — makes API calls to gateway):
round_data = await gateway.get_round(round_id)
result = await gateway.call_number(round_id)  # gateway runs the number logic
# Or: game engine keeps round_engine logic, calls gateway for DB ops:
called = engine.call_number(round_data)  # pure logic, no DB
await gateway.save_call(round_id, called)
```

**Where round_engine logic lives:** The smart predictor, pattern checking, winner detection, and cartela evaluation should remain in the game engine service. The gateway is "dumb" — it just stores and returns data. The game engine is "smart" — it runs the algorithms.

**RAM estimate:** ~60-100MB (1 asyncio process)

---

### Service D: Game Engine — Stake 20 (kelembingo-engine-20.onrender.com)

**Role:** Run the game loop for all stack-20 rounds

**Identical in structure to Service C**, but only processes rounds with `stake=20`.

**Why separate:** Stack 10 and stack 20 can have simultaneous active rounds. Each game loop calls numbers every 5 seconds. With two rounds active at the same time on the same process, the event loop alternates between them. On separate processes, each gets dedicated CPU — no timing interference.

**RAM estimate:** ~60-100MB

---

### Vercel: Frontend (kelembingo.vercel.app)

**Role:** Static site hosting for admin dashboard + game Mini App

**Already deployed and working.** No changes needed other than confirming `env.js` still points to the gateway URL.

---

## 4. Inter-Service Communication

### Communication Matrix

| From → To | Protocol | Purpose | Frequency |
|-----------|----------|---------|-----------|
| Frontend → Gateway | Socket.IO | Real-time game state, admin dashboard | Continuous |
| Bot Service → Gateway | HTTP REST (httpx) | All CRUD operations (users, deposits, withdrawals) | Per user action |
| Game Engine → Gateway | HTTP REST (httpx) | Round lifecycle, number calling, winner declaration | Every ~5s |
| Any → Backup Bot | Telegram Bot API | Only Gateway creates backups | Every 1 min |

### Gateway API Contract (already exists + additions)

**Already exists** (no changes needed):
```
GET  /api/users/{id}
GET  /api/rounds/{id}
POST /api/rounds/{id}/join
GET  /api/deposits/config/{id}
POST /api/deposits/submit
GET  /api/admin/deposits
POST /api/admin/deposits/{id}/approve
POST /api/admin/deposits/{id}/reject
GET  /api/admin/withdrawals
POST /api/admin/withdrawals/{id}/approve
POST /api/admin/withdrawals/{id}/reject
PATCH /api/admin/users/{id}/balance
PATCH /api/admin/users/{id}/ban
... (all existing endpoints)
```

**New endpoints needed for Game Engine:**
```python
# Called by game engine → gateway
POST /api/engine/call-number
# Body: {"round_id": "...", "previous_state": {...}}
# Returns: {"number_called": 42, "new_state": {...}}

POST /api/engine/check-bingo
# Body: {"round_id": "...", "player_id": "...", "cartela_numbers": [...]}
# Returns: {"is_bingo": bool, "pattern": "..."}

POST /api/engine/end-round
# Body: {"round_id": "...", "winner": {...}, "prizes": {...}}
# Returns: {"ok": true}
```

**Alternative (simpler):** Instead of a separate `/api/engine/` contract, the game engine can use the existing `/api/rounds/` endpoints plus a few additions for game-engine-specific operations.

### Authentication

For inter-service calls, use a shared API key:
```python
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY")  # Same on all services

# Gateway: validate on internal endpoints
if request.headers.get("X-Internal-Key") != INTERNAL_API_KEY:
    raise HTTPException(403)

# Game Engine/Bots: send key with every request
headers = {"X-Internal-Key": INTERNAL_API_KEY}
await client.get(f"{GATEWAY_URL}/api/rounds/{id}", headers=headers)
```

---

## 5. Data Layer Design

### Principle: Single Writer Per Data Type

| Data | Written By | Read By | Notes |
|------|------------|---------|-------|
| `users` | Bot Service (register, transfer) → via Gateway | All services → via Gateway | Gateway executes atomic writes |
| `users.play_wallet` | Bot Service (deposit/withdraw/win) → via Gateway | All services → via Gateway | Gateway uses SQLite atomic increments |
| `rounds` | Game Engine (create, call, end) → via Gateway | Game Engine, Frontend → via Gateway/SocketIO | Game engine owns round lifecycle |
| `cartelas_master` | Admin (generate) → direct via Gateway | Game Engine, Frontend | Read-only after generation; cached in game engine service |
| `deposits` | Bot Service → Gateway | Bot Service, Admin → Gateway | |
| `withdrawals` | Bot Service → Gateway | Bot Service, Admin → Gateway | |
| `settings` | Admin → Gateway | All services | Rarely written, frequently read |
| `bot_content` | Admin → Gateway | Bot Service → Gateway | Message text cache |
| `system` | Gateway | Gateway | Internal flags |

### The Gateway as Transactional Boundary

All writes go through the Gateway because:
1. SQLite only supports a single writer at a time
2. WAL mode allows concurrent readers + 1 writer
3. Gateway serializes writes from all services via HTTP request queue

**Atomic increment fix** (needed regardless of split):
```sql
-- Instead of read-modify-write in Python:
UPDATE firestore_documents
SET data = json_set(data,
    '$.play_wallet',
    json_extract(data, '$.play_wallet') + 50)
WHERE collection = 'users' AND doc_id = '123'
```

This eliminates TOCTOU race conditions even with concurrent requests to the gateway.

### Caching Strategy

| Cache | Where | TTL | Invalidation |
|-------|-------|-----|-------------|
| Cartelas (500 items) | Each Game Engine service | Forever (immutable after generation) | Manual regeneration clears cache |
| Pattern cache | Each Game Engine service | Forever (depends on cartelas) | Same as cartela cache |
| Bot content messages | Bot Service | 60s (existing) | Time-based expiry |
| User data | Bot Service | None (always fresh from gateway) | Not cached — always read through |
| Round state | Game Engine | Duration of the round | Held in memory, ends when round completes |

---

## 6. Implementation Plan

### Phase 1: Gateway Client Library (Day 1)

Create `gateway_client.py`:
```python
"""HTTP client wrapper for inter-service Gateway communication."""
import os
import httpx

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
API_KEY = os.getenv("INTERNAL_API_KEY", "")

class GatewayClient:
    def __init__(self, base_url=GATEWAY_URL):
        self.client = httpx.AsyncClient(base_url=base_url, timeout=15.0,
            headers={"X-Internal-Key": API_KEY})
    
    async def get_user(self, user_id):
        r = await self.client.get(f"/api/users/{user_id}")
        r.raise_for_status()
        return r.json().get("data")
    
    async def create_user(self, user_id, data):
        r = await self.client.post(f"/api/db/users/{user_id}", json=data)
        r.raise_for_status()
        return r.json()
    
    # ... one method per CRUD operation
```

### Phase 2: Gateway Internal Auth (Day 1)

Add `INTERNAL_API_KEY` validation to gateway endpoint groups that bots/game-engines call.

### Phase 3: Refactor Bot Service (Days 2-3)

Replace all `db.collection(...)` calls in `bot.py`, `admin_bot.py`, `support_bot.py`, `admin_support_bot.py` with `gateway_client.*` calls.

**Pattern:**
```python
# BEFORE (bot.py:register_user):
user_ref = db.collection('users').document(str(user_id))
user_doc = user_ref.get()
if not user_doc.exists:
    user_ref.set({...})

# AFTER:
user = await gateway.get_user(user_id)
if not user:
    await gateway.create_user(user_id, {...})
```

**Key: the bot service has NO `firestore_db.py` import at all.**

### Phase 4: Extract Game Engine (Days 3-5)

**Decision: where does round_engine.py run?**

Two options:

**Option A: round_engine logic on Gateway**
- Game engine services are pure timers
- Gateway runs the smart predictor, winner detection
- Pro: simpler game engine, no duplicate logic
- Con: Gateway does heavy computation, more RAM on gateway

**Option B: round_engine logic on Game Engine**
- Game engine services import round_engine.py
- They call Gateway only for raw data CRUD
- Pro: compute is distributed across services
- Con: round_engine must be refactored to separate pure logic from DB calls

**Recommendation: Option B** — Keeps gateway lightweight, distributes CPU load, and the game engine already has the logic.

**Refactoring round_engine.py:**
```python
# BEFORE — mixed logic + DB (current):
async def call_number(self, round_id: str) -> dict:
    round_doc = await asyncio.to_thread(db.collection('rounds').document(round_id).get())
    round_data = round_doc.to_dict()
    # ... smart predictor logic ...
    # ... write called number back to DB ...
    await asyncio.to_thread(round_ref.update, {"last_called": n, ...})

# AFTER — pure logic, calls gateway for DB:
async def call_number(self, round_data: dict) -> dict:
    # ... smart predictor logic (pure Python) ...
    # Return what to write:
    return {"last_called": n, "called_numbers": [...], "next_number_at": ...}
```

The game engine's main loop:
```python
async def run_game_loop(round_id):
    while True:
        round_data = await gateway.get_round(round_id)
        if round_data["status"] != "playing":
            break
        now = time.time()
        if now >= round_data.get("next_number_at", now):
            # Pure computation — no DB calls:
            update = engine.call_number(round_data)
            # Write result via gateway:
            await gateway.update_round(round_id, update)
            # Check for winner:
            winner = engine.evaluate_winners(round_data, update)
            if winner:
                await gateway.declare_winner(round_id, winner)
                break
        await asyncio.sleep(0.5)
```

### Phase 5: Dockerfiles + Config (Day 5)

**Gateway Dockerfile** (`Dockerfile.gateway`):
```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY api/ api/
COPY game/ game/
COPY firestore_db.py backup_common.py config.py ./
COPY handlers/ handlers/
CMD ["python", "run_api.py"]
```

**Bot Service Dockerfile** (`Dockerfile.bot`):
```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y gcc tesseract-ocr && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py admin_bot.py support_bot.py admin_support_bot.py ./
COPY support_common.py gateway_client.py ./
COPY handlers/ handlers/
COPY game/ game/  # Only if engine needs game/
CMD ["python", "run_bots.py"]
```

**Game Engine Dockerfile** (`Dockerfile.engine`):
```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY game/ game/
COPY gateway_client.py ./
COPY config.py firestore_db.py ./
CMD ["python", "run_engine.py"]  # Takes --stake 10 or --stake 20
```

**render.yaml:**
```yaml
services:
  - type: web
    name: kelembingo-gateway
    runtime: docker
    plan: free
    dockerfilePath: ./Dockerfile.gateway
    healthCheckPath: /api/health
    envVars:
      - key: SERVICE
        value: gateway
      - key: RENDER_API_ONLY
        value: "true"

  - type: web
    name: kelembingo-bots
    runtime: docker
    plan: free
    dockerfilePath: ./Dockerfile.bot
    healthCheckPath: /api/health
    envVars:
      - key: SERVICE
        value: bot
      - key: GATEWAY_URL
        value: https://kelembingo-gateway.onrender.com
      - key: INTERNAL_API_KEY
        generateValue: true

  - type: web
    name: kelembingo-engine-10
    runtime: docker
    plan: free
    dockerfilePath: ./Dockerfile.engine
    healthCheckPath: /api/health
    envVars:
      - key: SERVICE
        value: engine
      - key: ENGINE_STAKE
        value: "10"
      - key: GATEWAY_URL
        value: https://kelembingo-gateway.onrender.com
      - key: INTERNAL_API_KEY
        generateValue: true

  - type: web
    name: kelembingo-engine-20
    runtime: docker
    plan: free
    dockerfilePath: ./Dockerfile.engine
    healthCheckPath: /api/health
    envVars:
      - key: SERVICE
        value: engine
      - key: ENGINE_STAKE
        value: "20"
      - key: GATEWAY_URL
        value: https://kelembingo-gateway.onrender.com
      - key: INTERNAL_API_KEY
        generateValue: true
```

### Phase 6: Update Frontend (Day 5)

- `dashboard/env.js` → confirm `window.BACKEND_URL` points to `https://kelembingo-gateway.onrender.com`
- No other frontend changes needed (frontend always talked to the API, and the API is now the Gateway)

### Phase 7: Backup Bot (Day 5)

- Backup bot runs **only on Gateway** (scheduler in `run_backup_scheduler()`)
- Other services do NOT run backup logic
- `restore_if_empty()` runs on Gateway startup only, restores from Telegram → Gateways's local SQLite
- Bot services and game engines start fresh every deploy and rely on Gateway for data

---

## 7. Files to Create

| New File | Location | Purpose |
|----------|----------|---------|
| `gateway_client.py` | Root | HTTP client wrapper for services → Gateway |
| `run_engine.py` | Root | Game engine entry point (takes `--stake` arg) |
| `Dockerfile.gateway` | Root | Gateway service build |
| `Dockerfile.bot` | Root | Bot service build |
| `Dockerfile.engine` | Root | Game engine build (shared for stake 10 + 20) |

## 8. Files to Modify

| File | Change |
|------|--------|
| `bot.py` | Replace `db.collection(...)` with `gateway_client.*()` |
| `admin_bot.py` | Same replacement |
| `support_bot.py` | Same replacement |
| `admin_support_bot.py` | Same replacement |
| `api/admin_api.py` | Add `INTERNAL_API_KEY` validation; remove game loop + `_monitor()`; add engine-facing endpoints |
| `game/round_engine.py` | Refactor to separate pure logic from DB calls |
| `handlers/user_manager.py` | Replace `db` calls with gateway client |
| `handlers/bot_content.py` | Replace `db` calls with gateway client (keep in-memory cache) |
| `handlers/withdraw_handler.py` | Replace `db` calls with gateway client |
| `handlers/admin_handlers.py` | Replace `db` calls with gateway client |
| `run_bots.py` | Add `GATEWAY_URL` env; remove backup scheduler (runs on gateway only) |
| `run_api.py` | Clean up — remove multiprocessing startup |
| `firestore_db.py` | Add atomic JSON increment (`json_set`/`json_extract`) for race condition fix |
| `render.yaml` | Define 4 services |

## 9. Files to Remove/Conditionalize

| File | Reason |
|------|--------|
| `run_all.py` | Obsolete, replaced by new entry points |
| `clear_index.py` | Not needed in split architecture |
| `dashboard/` from Gateway | Serve from Vercel only (save ~80MB RAM on Gateway via `RENDER_API_ONLY=true`) |

---

## 10. Migration Steps (Zero-Downtime Transition)

### Step 1: Deploy Gateway first
- Push code with `gateway_client.py` and internal API key support
- Gateway runs the existing monolith code PLUS new engine-facing endpoints
- All existing clients (frontend, bots) continue working unchanged

### Step 2: Deploy Bot Service
- Build `Dockerfile.bot` with gateway client
- Bot service starts, connects to Gateway
- Keep old monolith bot running briefly — verify new bot service works
- DNS: point bot webhooks to new bot service

### Step 3: Deploy Game Engines
- Deploy engine-10 and engine-20 services
- They start polling Gateway for rounds
- Gateway's `_monitor()` creates rounds, game engines pick them up
- Remove `_game_loop` and `_monitor` from Gateway

### Step 4: Cleanup
- Remove old monolith service from Render
- Remove game loop code from Gateway codebase
- Verify all 4 services running

---

## 11. Edge Cases & Risks

### Latency on Number Calls
**Risk:** Game engine → Gateway HTTP call takes ~50ms. With 5-second intervals, this is negligible. But if Gateway is under heavy load, calls could take longer.

**Mitigation:** Gateway should prioritize engine-facing requests (use FastAPI's async, keep DB queries fast).

### Gateway Goes Down
**Risk:** If Gateway crashes, all services are blind. No user registration, no deposits, no game.

**Mitigation:** 
- Gateway auto-restarts on Render (health check)
- Bot services can cache some user data locally for read-only fallback
- Game engines pause and retry Gateway connection

### In-flight Round During Gateway Restart
**Risk:** Gateway restarts while a round is in progress. The round data is in SQLite (persists across Gateway restarts in same deploy). But if Gateway deploys (filesystem wipe), round state is gone.

**Mitigation:** Game engines hold round state in memory. If Gateway restarts, game engines re-create the round via Gateway API. Use `restore_if_empty()` on Gateway to restore from Telegram backup.

### Socket.IO Disconnect
**Risk:** Gateway restart drops all Socket.IO connections. Frontend reconnects.

**Mitigation:** Socket.IO client auto-reconnects. Game state is in DB, not in memory. On reconnect, frontend re-reads current state from Gateway.

### Race Condition: Two Game Engines Process Same Round
**Risk:** Due to bug, both engine-10 and engine-20 try to process the same round.

**Mitigation:**
- Game engines filter by `stake` field when polling for rounds
- Use optimistic locking: add `lock_version` field to rounds
- Gateway rejects stale updates: `UPDATE ... WHERE lock_version = X AND round_id = ...`

### Telegram Bot 409 Conflict
**Risk:** If old monolith is still running when new bot service starts, both poll the same bot token → 409 errors.

**Mitigation:** Stop old monolith before starting new bot service (Render deploy handles this automatically if service names change).

---

## 12. Effort Estimate

| Phase | Tasks | Estimated Time |
|-------|-------|---------------|
| 1 | Gateway client library | 2-4 hours |
| 2 | Gateway internal auth | 1-2 hours |
| 3 | Refactor bot service (4 bot files + handlers) | 8-16 hours |
| 4a | Refactor round_engine.py (separate logic from DB) | 4-8 hours |
| 4b | Create run_engine.py with main loop | 4-6 hours |
| 5 | Dockerfiles + render.yaml + deployment config | 2-4 hours |
| 6 | Frontend URL update | 30 min |
| 7 | Testing + debugging | 8-16 hours |
| **Total** | | **~30-56 hours (1-2 weeks)** |

---

## 13. Simpler Alternative (if 4 servers seems too aggressive)

If vertical split (separating concerns) is too much work, consider a **simpler horizontal split** — just 2 backend services:

```
Server 1: GATEWAY (kelembingo-gateway.onrender.com)
  - FastAPI + Socket.IO + SQLite + Backup + Game engines (both stakes)
  - NO bots
  - RAM: ~150-200MB

Server 2: BOTS (kelembingo-bots.onrender.com)
  - All 4 Telegram bots
  - HTTP client → Gateway for data
  - RAM: ~80-120MB
```

This gives you:
- ~320MB total (vs ~450MB in monolith) → well under 512MB each
- Bots don't compete with API for RAM
- Much less code to change (~30% of the full split)
- Can later split game engines into separate services if needed

**Trade-off:**
- Game engines and API still share a process
- Stack 10 and 20 rounds on same process
- But still eliminates the main RAM pressure (bot processes + PTB)

---

## 14. Recommendation

**Start with Phase 1-3 (gateway client + bot refactor) as the first deployable milestone.** This immediately reduces the monolith's RAM load by proving the Gateway pattern works. Then extract game engines in a follow-up milestone.

### Immediate Next Actions

1. Create `gateway_client.py`
2. Add `INTERNAL_API_KEY` to Gateway endpoints
3. Refactor `bot.py` to use gateway client (replaces all `db.collection()` calls)
4. Create `Dockerfile.bot` + update `render.yaml`
5. Deploy bot service → verify it works
6. Remove bot processes from original monolith → verify RAM drops
7. Then extract game engines

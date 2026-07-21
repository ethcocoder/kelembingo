# HIGH-LEVEL ARCHITECTURE OVERVIEW

## What This App Is

Kelem Bingo is a **Telegram Mini App** (TMA) — a real-time multiplayer Bingo game where users:
1. Open the web app from a Telegram bot (`bot.py`)
2. Join rounds by selecting cartelas (bingo cards) during a 35s selection window
3. Watch numbers get called automatically every 5s
4. Win when all numbers on a line/column/diagonal are called (derash = 75% of pool)

## System Components

```
                    ┌──────────────────────────────────────────────────┐
                    │         Render Cloud (Docker, 1 container)       │
                    │                                                  │
                    │  ┌────────────────────────────────────────────┐  │
                    │  │   run_bots.py (multiprocessing launcher)   │  │
                    │  │                                            │  │
                    │  │  Process 1: Game Bot (bot.py)              │  │
                    │  │    └─ Telegram bot: registration,          │  │
                    │  │       deposits, withdrawals, webapp link    │  │
                    │  │                                            │  │
                    │  │  Process 2: Admin Bot (admin_bot.py)       │  │
                    │  │    └─ Telegram bot: deposit/withdraw admin  │  │
                    │  │                                            │  │
                    │  │  Process 3: FastAPI + Socket.IO (main)     │  │
                    │  │    └─ Serves dashboard, REST API,           │  │
                    │  │       Socket.IO, game loop bg tasks         │  │
                    │  └────────────────────────────────────────────┘  │
                    │                         │                        │
                    │                    ┌────▼─────┐                  │
                    │                    │ Database │                  │
                    │                    │ SQLite   │                  │
                    │                    │ (or PG)  │                  │
                    │                    └──────────┘                  │
                    └──────────────────────────────────────────────────┘
                                │           │
                    ┌───────────┘           └───────────┐
                    ▼                                     ▼
          Telegram Users                          Web Browser
          (bot.py)                           (dashboard HTML/JS)
                                              Socket.IO client
```

## Key Technologies

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, uvicorn |
| Real-time | python-socketio v5.11, Socket.IO JS v4.7.5 |
| Database | SQLite (dev) / PostgreSQL (prod) via SQLAlchemy |
| "Firebase" | **Fully mocked** — the app implements `MockFirestoreClient` (firestore_db.py), a SQLAlchemy-backed Firestore API emulator. All `db.collection(...)` calls hit a local SQL table. |
| Frontend | Vanilla JS, TailwindCSS v4 (CDN), no build step |
| Telegram | python-telegram-bot v21+ (2 bots: game + admin) |
| Deployment | Render (Docker, Free plan, auto-deploy) |

## The "Firebase" Illusion

The app declares Firebase env vars (`FIREBASE_PROJECT_ID`, `FIREBASE_PRIVATE_KEY`, etc.) but **never uses real Firebase**. In `config.py`, mock modules replace `firebase_admin`, `firebase_admin.credentials`, and `firebase_admin.firestore`. The frontend `firebase.js` builds a `MockFirestore` class that:

- Translates `db.collection('X').doc('Y').get()` into `GET /api/db/X/Y`
- Translates `db.collection('X').where(...).orderBy(...).limit(N).get()` into `GET /api/db/X?filters=...`
- Translates `.onSnapshot(callback)` into a Socket.IO `subscribe` / `snapshot` event subscription

This means **all database reads/writes go through the Python FastAPI backend**, which stores data in SQL rows via SQLAlchemy.

## Key Files

| File | Lines | Purpose |
|------|-------|---------|
| `api/admin_api.py` | 1234 | FastAPI app + Socket.IO server + all REST endpoints + game loop |
| `game/round_engine.py` | 520 | Round lifecycle, join logic, number calling, bingo checking |
| `firestore_db.py` | 479 | SQL-backed Firestore emulator (MockFirestoreClient) |
| `dashboard/js/firebase.js` | 365 | Client-side Firestore mock (Socket.IO + REST bridge) |
| `dashboard/js/card-select.js` | 531 | Card selection screen: grid, toggle, confirm, onSnapshot |
| `dashboard/js/game-board.js` | 310 | Game board display, number listening, auto-mark |
| `bot.py` | 1168 | Main Telegram bot |
| `config.py` | 59 | Env vars + Firebase mocking |
| `render.yaml` | 24 | Render deployment config (2 services, same Dockerfile) |
| `run_bots.py` | 63 | Production entry point (multiprocessing launcher) |

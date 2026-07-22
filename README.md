# 🎱 Kelem Bingo

A real-time, multiplayer **Telegram Bingo** platform. Players open a Telegram
Mini App to join rounds, pick cartelas (bingo cards), and watch numbers get
called live; admins manage deposits, withdrawals, players, and bot content from
a web dashboard.

The whole platform — game bot, admin bot, two support bots, a backup bot, the
REST/real-time API, and the web dashboard — runs from a **single container**.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Repository Layout](#repository-layout)
- [The "Firebase" Emulator](#the-firebase-emulator)
- [Bots](#bots)
- [Game Rules](#game-rules)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Running the App](#running-the-app)
- [Admin Dashboard](#admin-dashboard)
- [Data Backup & Restore](#data-backup--restore)
- [Deployment (Render)](#deployment-render)
- [REST API Reference](#rest-api-reference)
- [Troubleshooting](#troubleshooting)

---

## Features

- 🎮 **Live multiplayer Bingo** — automatic rounds per stake, 35s selection
  window, a number called every 5s, single-winner resolution.
- 💸 **Wallets & payments** — TeleBirr-based deposits and withdrawals with
  admin approval, per-day limits, cooldowns, and minimum thresholds.
- 👥 **Invitations** — personal referral links to invite friends (invitation
  tracking only; no monetary bonus).
- 🆘 **Support system** — a user support bot (3 messages/day) that forwards to
  an admin support bot; admins reply without exposing their real account.
- 🛠️ **Admin dashboard** — users, games, cartelas, reports, payments, editable
  bot messages, and editable money/limits that apply instantly.
- 💾 **JSON backup/restore** — snapshots the whole database to a Telegram bot so
  data survives Render's ephemeral-disk redeploys.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                Render Cloud — single Docker container              │
│                                                                    │
│  run_bots.py  (multiprocessing launcher)                           │
│  ├─ Process: Game Bot          bot.py                              │
│  ├─ Process: Admin Bot         admin_bot.py                        │
│  ├─ Process: Support Bot       support_bot.py        (@kelemsupportbot)      │
│  ├─ Process: Admin Support Bot admin_support_bot.py  (@kelemadminsupportbot) │
│  ├─ Process: Backup Scheduler  backup_common.py      (@kelembackupbot)       │
│  └─ Main:    FastAPI + Socket.IO  api/admin_api.py                 │
│                 ├─ serves the web dashboard + game Mini App         │
│                 ├─ REST API + Socket.IO real-time events           │
│                 └─ background game loop (calls numbers, pays out)  │
│                                   │                                 │
│                              ┌────▼─────┐                           │
│                              │ Database │  SQLite (dev)             │
│                              │ SQLAlchemy│  or PostgreSQL (prod)    │
│                              └──────────┘                           │
└──────────────────────────────────────────────────────────────────┘
        │                                            │
   Telegram users                              Web browsers
   (bots + Mini App)                     (dashboard + game board,
                                          Socket.IO client)
```

All processes share **one database** (via SQLAlchemy), so the bots and the API
see the same data.

---

## Tech Stack

| Layer      | Technology |
|------------|-----------|
| Backend    | Python 3.12, FastAPI, Uvicorn |
| Real-time  | python-socketio v5, Socket.IO JS v4 |
| Database   | SQLite (dev) / PostgreSQL (prod) via SQLAlchemy |
| Telegram   | python-telegram-bot v21+ |
| Frontend   | Vanilla JS + TailwindCSS (CDN, no build step) |
| Deployment | Docker on Render (free plan, auto-deploy) |

---

## Repository Layout

```
kelembingo/
├── run_bots.py            # 🚀 Production entry point (launches everything)
├── bot.py                 # Main game bot (registration, wallet, invites, webapp link)
├── admin_bot.py           # Admin game bot (approve deposits/withdrawals)
├── support_bot.py         # User support bot (@kelemsupportbot)
├── admin_support_bot.py   # Admin support bot (@kelemadminsupportbot)
├── support_common.py      # Shared support helpers + hard-coded support tokens
├── backup_common.py       # JSON backup/restore via @kelembackupbot
├── config.py              # Env vars + Firebase mocking + db init
├── firestore_db.py        # SQLAlchemy-backed Firestore emulator + export/import
├── requirements.txt
├── Dockerfile
├── render.yaml            # Render deployment config
│
├── api/
│   └── admin_api.py       # FastAPI app: REST + Socket.IO + game loop
│
├── game/
│   ├── round_engine.py    # Round lifecycle, join, number calling, payouts
│   ├── engine.py
│   └── prediction.py      # Smart number predictor (bounded game length)
│
├── handlers/
│   ├── user_manager.py    # User CRUD, withdrawals, transfers, referrals
│   ├── admin_handlers.py
│   ├── withdraw_handler.py
│   └── bot_content.py     # Editable bot messages + config defaults
│
├── dashboard/             # Web dashboard + game Mini App (static, served by API)
│   ├── index.html         # Admin dashboard
│   ├── game.html          # Player game board / Mini App
│   ├── js/admin/          # Dashboard modules (users, payments, backup, …)
│   └── js/firebase.js     # Client-side Firestore mock (REST + Socket.IO bridge)
│
└── status/                # In-depth architecture notes
```

---

## The "Firebase" Emulator

The code is written against a Firestore-style API (`db.collection(...).document(...)`),
but **no real Firebase is used**. Instead:

- `firestore_db.py` implements `MockFirestoreClient`, backed by a single
  SQLAlchemy table (`firestore_documents`) storing `(collection, doc_id, json)`.
- `config.py` injects mock `firebase_admin` modules so existing imports work.
- The frontend `dashboard/js/firebase.js` mirrors the same API in the browser,
  translating calls into REST (`/api/db/...`) and Socket.IO subscriptions.

This means every database read/write flows through the FastAPI backend into SQL.

---

## Bots

| Bot | Username | Token source | Purpose |
|-----|----------|--------------|---------|
| Game        | *(your bot)*            | `BOT_TOKEN` (env)        | Registration, wallet, invites, opens the Mini App |
| Admin        | *(your bot)*            | `ADMIN_BOT_TOKEN` (env)  | Approve/reject deposits & withdrawals |
| Support      | `@kelemsupportbot`      | hard-coded (`support_common.py`) | Users send support messages (3/day), forwarded to admin |
| Admin support| `@kelemadminsupportbot` | hard-coded (`support_common.py`) | Admin replies to players without exposing their account |
| Backup       | `@kelembackupbot`       | hard-coded (`backup_common.py`)  | Stores JSON DB snapshots (see [Backup](#data-backup--restore)) |

The admin's Telegram user id (`ADMIN_CHAT_ID`) is used to authorize the admin
support bot and to route support replies and backups. It is **never exposed to
users**.

---

## Game Rules

- Stakes: **10** or **20 ETB** (`VALID_STAKES`).
- Selection window: **35 seconds** to pick cartelas.
- Up to **2 cartelas** per player per round.
- A new number is called every **5 seconds**.
- Rounds resolve within **15–30 calls** (smart predictor keeps games snappy).
- Winner takes the **Derash = 75%** of the total stake pool.

---

## Getting Started

### Prerequisites

- Python **3.12**
- `gcc` and `tesseract-ocr` (for `pytesseract`; also handled by the Dockerfile)
- Telegram bot tokens from [@BotFather](https://t.me/BotFather)

### Install

```bash
git clone https://github.com/ethcocoder/kelembingo.git
cd kelembingo

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Configure

Create a `.env` file in the project root (see [Environment Variables](#environment-variables)):

```env
BOT_TOKEN=123456:your-game-bot-token
ADMIN_BOT_TOKEN=123456:your-admin-bot-token
ADMIN_CHAT_ID=123456789
WEBAPP_URL=https://your-app.onrender.com
# DATABASE_URL=postgresql://user:pass@host/db   # optional; defaults to local SQLite
```

> The support and backup bot tokens are hard-coded in `support_common.py` and
> `backup_common.py`. Replace them there if you use your own bots.

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|:--------:|---------|-------------|
| `BOT_TOKEN` | ✅ | — | Game bot token |
| `ADMIN_BOT_TOKEN` | ✅ | — | Admin bot token (must differ from `BOT_TOKEN`) |
| `ADMIN_CHAT_ID` | ✅ | — | Admin's Telegram user id (auth + support routing + backups) |
| `DATABASE_URL` | ➖ | `sqlite:///kelembingo.db` | SQLAlchemy URL; use Postgres in production |
| `WEBAPP_URL` | ➖ | — | Public URL of the Mini App / dashboard |
| `SUPPORT_USERNAME` | ➖ | `kelemsupportbot` | Support handle shown in the game bot |
| `TELEBIRR_NUMBER` | ➖ | `+251911000000` | Deposit destination number |
| `DEFAULT_STAKE_10` / `DEFAULT_STAKE_20` | ➖ | `10` / `20` | Stake presets |
| `GAME_TIMER_SECONDS` | ➖ | `35` | Selection window |
| `MIN_WITHDRAW` / `MAX_WITHDRAW` | ➖ | `50` / `50000` | Withdrawal bounds (ETB) |
| `MIN_INITIAL_DEPOSIT` | ➖ | `50` | Minimum first deposit (ETB) |
| `MAX_WITHDRAW_PER_DAY` | ➖ | `3` | Daily withdrawal count limit |
| `WITHDRAW_COOLDOWN_HOURS` | ➖ | `4` | Cooldown between withdrawals |
| `BONUS_TO_ETB_RATE` | ➖ | `10` | Bonus-coin → ETB conversion rate |
| `BACKUP_INTERVAL_MINUTES` | ➖ | `15` | Auto-backup interval |

> Most money/limit values are also editable at runtime from the dashboard's
> **💰 Amounts & Limits** tab (stored in the `bot_content` collection) and take
> effect instantly.

---

## Running the App

### Everything (production layout)

```bash
python run_bots.py
```

Launches all bots, the backup scheduler, and the FastAPI + Socket.IO server on
`PORT` (default `8000`).

### API / dashboard only

```bash
python run_api.py         # serves dashboard + API at http://localhost:8000
```

### With Docker

```bash
docker compose up --build
# dashboard → http://localhost:8000
```

---

## Admin Dashboard

Served at `/` by the API (login at `/login`). Sections:

- **Dashboard** — live stats.
- **Users** — search, view, adjust balance, ban/unban.
- **Games** — round history and outcomes.
- **Cartelas** — generate / inspect the 500-card pool.
- **Reports** — revenue and activity.
- **Payments** — approve/reject deposits and withdrawals.
- **Settings** — bot config and admin password.
- **Bot Content** — edit every bot message; the first tab **💰 Amounts & Limits**
  edits money/limits live.
- **💾 Data Backup** — status, "Back Up Now", and "Restore".

---

## Data Backup & Restore

Render's free plan **wipes the container disk on every deploy**, so a local
SQLite database (and all user data) would be lost each time. To prevent this,
the platform keeps a single JSON snapshot of the whole database inside the
**backup bot** (`@kelembackupbot`).

**How it works**

1. **Backup** — `create_backup()` exports the entire document store to JSON,
   uploads it to the admin's chat with the backup bot, and **pins** that
   message.
2. **Finding the latest snapshot after a restart** — because a bot can read a
   chat's *pinned* message on startup, no extra storage is needed to locate the
   most recent backup.
3. **Restore** — on a fresh (empty) deploy, `restore_if_empty()` downloads the
   pinned JSON and seeds every record back **by id**. A safe restore only
   inserts missing documents and never clobbers live data (overwrite is opt-in).
4. **Automation** — a background scheduler backs up every
   `BACKUP_INTERVAL_MINUTES` (default 15); manual **Back Up Now** / **Restore**
   buttons live in the dashboard's Data Backup section.

**One-time setup:** the admin must press **Start** on `@kelembackupbot` once, and
`ADMIN_CHAT_ID` must be set. Until then, backups stay disabled and the dashboard
shows a clear warning.

> ⚠️ This is a **safety net, not a live replica** — data written between the
> last snapshot and a deploy can still be lost. For zero-data-loss, point
> `DATABASE_URL` at a managed PostgreSQL instance instead.

---

## Deployment (Render)

The repo ships a `render.yaml` and a `Dockerfile`. On Render:

1. Create a new **Web Service** from this repo (Docker runtime).
2. Set the environment variables above (at minimum `BOT_TOKEN`,
   `ADMIN_BOT_TOKEN`, `ADMIN_CHAT_ID`).
3. Deploy. The container runs `python run_bots.py`.
4. Health check: `GET /api/health`.

For durable data, either attach a managed PostgreSQL database and set
`DATABASE_URL`, or rely on the [backup bot](#data-backup--restore).

---

## REST API Reference

Selected endpoints (see `api/admin_api.py` for the full list):

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/api/health` | Health check |
| `GET`  | `/api/time` | Server time (client clock sync) |
| `GET`  | `/api/dashboard` | Aggregate dashboard stats |
| `GET`  | `/api/users` · `/api/users/{id}` | List / fetch users |
| `GET`/`POST` | `/api/rounds*` | Round lifecycle (create, join, select, call, end) |
| `GET`/`POST` | `/api/admin/deposits*` | Deposit review |
| `GET`/`POST` | `/api/admin/withdrawals*` | Withdrawal review |
| `GET`/`POST` | `/api/admin/bot-content*` | Read / edit bot messages |
| `GET`  | `/api/admin/backup/status` | Latest backup metadata |
| `POST` | `/api/admin/backup/create` | Create a backup now |
| `POST` | `/api/admin/backup/restore` | Restore from the latest backup |
| `*`    | `/api/db/{collection}[/{doc}]` | Generic Firestore-emulator CRUD |

Real-time updates are delivered over **Socket.IO** (`subscribe` → `snapshot`
events), mirroring Firestore's `onSnapshot`.

---

## Troubleshooting

- **`409 Conflict` from Telegram** — `BOT_TOKEN` and `ADMIN_BOT_TOKEN` must be
  two *different* bots; `config.py` logs a critical error if they match.
- **Data disappears after deploy** — expected on ephemeral disks; enable the
  backup bot or use a managed `DATABASE_URL`. See [Backup](#data-backup--restore).
- **Backups disabled** — press Start on `@kelembackupbot` and set `ADMIN_CHAT_ID`.
- **Support replies not routing** — ensure `ADMIN_CHAT_ID` is set and the admin
  has started the admin support bot.

---

## License

ISC (see `package.json`).

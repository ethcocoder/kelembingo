# DEPLOYMENT CONFIGURATION

## Render: render.yaml  [render.yaml]

```yaml
services:
  - type: web
    name: kelembingo
    runtime: docker
    plan: free
    dockerfilePath: ./Dockerfile
    healthCheckPath: /api/health
    autoDeploy: true
  - type: web
    name: kelem-bingo-api
    runtime: docker
    plan: free
    dockerfilePath: ./Dockerfile
    healthCheckPath: /api/health
    autoDeploy: true
```

**Two web services**, both Free plan, both using the **exact same Dockerfile**.

**Critical problem**: Both services run `python run_bots.py` which starts:
- The game Telegram bot (`bot.py`)
- The admin Telegram bot (`admin_bot.py`)
- The FastAPI/Socket.IO server on port 8000

Two instances → Telegram "409 Conflict" errors + port 8000 conflicts.

**No `replicas` count** → default 1 replica per service = 2 total instances.

**No environment variables** defined in render.yaml — must be set via Render dashboard or `.env` (which is in `.gitignore` but copied at build time).

## Dockerfile  [Dockerfile]

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y gcc tesseract-ocr && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["python", "run_bots.py"]
```

**Process**: Builds from slim image, installs packages, copies all files, runs `run_bots.py`.

## Docker-Compose (Local Dev)  [docker-compose.yml]

```yaml
services:
  bingo-bot:
    build: .
    container_name: kelem-bingo
    ports: ["8000:8000"]
    env_file: .env
    volumes: ["./data:/app/data"]
    healthcheck: { test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"] }
```

Single service, port 8000, no PostgreSQL (uses SQLite + `./data` mount).

## Production Entry Point: run_bots.py  [run_bots.py]

```python
import multiprocessing as mp
mp.set_start_method("spawn")

def run_game_bot():  # runs bot.py
def run_admin_bot(): # runs admin_bot.py

if __name__ == "__main__":
    p1 = mp.Process(target=run_game_bot)
    p2 = mp.Process(target=run_admin_bot)
    p1.start(); p2.start()
    # Main process runs uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

**Three processes**: Game bot, admin bot, and the API server in the main process.

## Environment Variables (from .env)

| Variable | Purpose |
|----------|---------|
| `BOT_TOKEN` | Telegram game bot token |
| `ADMIN_BOT_TOKEN` | Telegram admin bot token |
| `PAYMENT_BOT_TOKEN` | Payment bot (unused in code) |
| `ADMIN_CHAT_ID` | Admin Telegram user ID |
| `FIREBASE_*` | Firebase credentials (UNUSED — Firebase is mocked) |
| `DATABASE_URL` | PostgreSQL connection string (falls back to SQLite) |
| `DEFAULT_STAKE_10/20` | 10 and 20 ETB |
| `GAME_TIMER_SECONDS` | 180 (OVERRIDDEN by code constant `SELECTION_DURATION=35`) |
| `TELEBIRR_NUMBER` | Payment phone number |
| `HOST` / `PORT` | Bind address (0.0.0.0:8000) |

## Current Deployment URLs

| Service | URL |
|---------|-----|
| Web app | `https://kelembingo.onrender.com` |
| API + Socket.IO | `https://kelem-bingo-api.onrender.com` |

The frontend hardcodes `window.API_BASE = 'https://kelem-bingo-api.onrender.com'` (in `dashboard/pages/home.html`).

## Known Deployment Issues

1. **Two services, one codebase**: Both `kelembingo` and `kelem-bingo-api` run the same code. Only one is needed. The second creates conflicts.
2. **Telegram bot duplication**: Two running instances of `bot.py` → Telegram "409: Conflict: terminated by other getUpdates request".
3. **Socket.IO per-process**: Rooms are in-memory, not shared across instances.
4. **Free plan sleeping**: Render Free spins down after 15 min idle. First request after sleep takes ~30s to spin up.
5. **Git history contains secrets**: The `.env` file with Firebase private key and bot tokens has been in commits.

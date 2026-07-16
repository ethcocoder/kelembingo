import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
from config import db, BOT_TOKEN
from game.round_engine import RoundEngine
from handlers.user_manager import UserManager
from datetime import datetime
from telegram import Bot
import asyncio

app = FastAPI(title="Yegara Bingo Admin API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = RoundEngine(db)
user_manager = UserManager(db)


# ─── Models ───
class JoinRoundRequest(BaseModel):
    user_id: int
    cartela_numbers: List[int]
    user_name: str = "Player"


class BingoCheckRequest(BaseModel):
    user_id: int


class EndRoundRequest(BaseModel):
    winner_ids: List[int]

class NotifyRequest(BaseModel):
    user_id: int
    text: str


# ═══════════════════════════════════════════════════════════════
# Cartela Management
# ═══════════════════════════════════════════════════════════════
@app.post("/api/cartelas/generate")
async def generate_cartelas():
    """Generate 500 fixed cartelas (idempotent)."""
    result = await engine.generate_all_cartelas()
    return result


@app.get("/api/cartelas")
async def get_cartelas():
    """Get all 500 master cartelas."""
    cartelas = await engine.get_all_cartelas()
    return {"cartelas": cartelas, "count": len(cartelas)}


@app.get("/api/cartelas/{number}")
async def get_cartela(number: int):
    """Get a single cartela by number."""
    if number < 1 or number > 500:
        raise HTTPException(status_code=400, detail="Cartela number must be 1-500")
    cartela = await engine.get_cartela(number)
    if not cartela:
        raise HTTPException(status_code=404, detail="Cartela not found")
    return {"cartela": cartela}


# ═══════════════════════════════════════════════════════════════
# Round Management
# ═══════════════════════════════════════════════════════════════
@app.get("/api/rounds/active")
async def get_active_round():
    """Get the current active round."""
    round_data = await engine.get_active_round()
    if not round_data:
        return {"round": None}
    return {"round": round_data}


@app.post("/api/rounds/create")
async def create_round():
    """Create a new round (or return existing active one)."""
    result = await engine.create_round()
    return {"round": result}


@app.post("/api/rounds/{round_id}/join")
async def join_round(round_id: str, req: JoinRoundRequest):
    """Player joins a round with chosen cartelas."""
    result = await engine.join_round(
        round_id, req.user_id, req.cartela_numbers, req.user_name
    )
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    return result


@app.post("/api/rounds/{round_id}/start")
async def start_round(round_id: str):
    """Start the round (transition from selecting to playing)."""
    result = await engine.start_round(round_id)
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    return result


@app.post("/api/rounds/{round_id}/call")
async def call_number(round_id: str):
    """Call the next random number."""
    number = await engine.call_number(round_id)
    if number is None:
        raise HTTPException(status_code=400, detail="No more numbers to call or round not playing")
    return {"number": number}


@app.post("/api/rounds/{round_id}/check-bingo")
async def check_bingo(round_id: str, req: BingoCheckRequest):
    """Check if a player has bingo."""
    result = await engine.check_bingo(round_id, req.user_id)
    return result


@app.post("/api/rounds/{round_id}/end")
async def end_round(round_id: str, req: EndRoundRequest):
    """End the round and distribute prizes."""
    result = await engine.end_round(round_id, req.winner_ids)
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    return result


@app.get("/api/rounds/{round_id}")
async def get_round(round_id: str):
    """Get round details."""
    round_data = await engine.get_round(round_id)
    if not round_data:
        raise HTTPException(status_code=404, detail="Round not found")
    return {"round": round_data}


@app.get("/api/rounds")
async def get_rounds(limit: int = 20):
    """Get recent rounds."""
    rounds = await engine.get_recent_rounds(limit)
    return {"rounds": rounds, "count": len(rounds)}


# ═══════════════════════════════════════════════════════════════
# Dashboard / Stats
# ═══════════════════════════════════════════════════════════════
@app.get("/api/dashboard")
async def get_dashboard():
    """Get dashboard overview."""
    users = await user_manager.get_all_users()
    total_balance = sum(u.get('balance', 0) for u in users)
    total_play = sum(u.get('play_wallet', 0) for u in users)
    total_wins = sum(u.get('wins', 0) for u in users)
    active_playing = sum(1 for u in users if u.get('is_playing'))

    # Count rounds
    try:
        all_rounds = list(db.collection('rounds').get())
        completed = sum(1 for r in all_rounds if r.to_dict().get('status') == 'completed')
        total_admin_profit = sum(r.to_dict().get('admin_profit', 0) for r in all_rounds if r.to_dict().get('status') == 'completed')
    except Exception:
        completed = 0
        total_admin_profit = 0

    # Count cartelas
    try:
        cartela_count = len(list(db.collection('cartelas_master').limit(501).get()))
    except Exception:
        cartela_count = 0

    return {
        "total_users": len(users),
        "total_balance": total_balance,
        "total_play_wallets": total_play,
        "total_wins": total_wins,
        "active_players": active_playing,
        "completed_rounds": completed,
        "total_admin_profit": total_admin_profit,
        "cartela_count": cartela_count,
    }


@app.get("/api/users")
async def get_users(limit: int = 100):
    """Get all users."""
    users = await user_manager.get_all_users(limit)
    return {"users": users}


@app.get("/api/users/{user_id}")
async def get_user(user_id: int):
    """Get specific user."""
    user = await user_manager.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user": user}

@app.post("/api/notify")
async def notify_user(req: NotifyRequest):
    try:
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(chat_id=req.user_id, text=req.text)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
async def health_check():
    """Health check."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


# ─── Dashboard & game (served from same service as API + bots) ───
DASHBOARD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard")


@app.get("/")
async def dashboard_home():
    return FileResponse(os.path.join(DASHBOARD_DIR, "index.html"))


@app.get("/game")
async def game_page():
    return FileResponse(os.path.join(DASHBOARD_DIR, "game.html"))


@app.get("/login")
async def login_page():
    return FileResponse(os.path.join(DASHBOARD_DIR, "login.html"))


if os.path.isdir(os.path.join(DASHBOARD_DIR, "css")):
    app.mount("/css", StaticFiles(directory=os.path.join(DASHBOARD_DIR, "css")), name="css")
if os.path.isdir(os.path.join(DASHBOARD_DIR, "js")):
    app.mount("/js", StaticFiles(directory=os.path.join(DASHBOARD_DIR, "js")), name="js")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
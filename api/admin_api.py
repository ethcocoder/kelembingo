import os
import random
import asyncio
import logging
import time
import socketio
from fastapi import FastAPI, HTTPException, Query as FastAPIQuery
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from typing import List, Optional
import json
import datetime
from config import db, BOT_TOKEN
from firestore_db import MockFirestoreClient, SessionLocal, SystemEvent, FieldFilter, Increment, ArrayUnion

from game.round_engine import RoundEngine, DEFAULT_STAKE, VALID_STAKES, SELECTION_DURATION
from handlers.user_manager import UserManager
from datetime import datetime, timedelta, timezone
from telegram import Bot
# Firebase replaced by SQLAlchemy emulator (firestore_db.py)

logger = logging.getLogger(__name__)

ALLOWED_ORIGINS = [
    "https://yegarabingo.onrender.com",
    "https://yegara-bingo-api.onrender.com",
]


# ─── Socket.IO Server ───
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins=ALLOWED_ORIGINS)

app = FastAPI(title="Yegara Bingo Admin API", version="2.0.0")



# ─── Outer CORS ASGI Middleware ───
# Wraps the ENTIRE app (including Socket.IO) so that preflight OPTIONS
# and CORS response headers work for ALL paths, not just FastAPI routes.
class CORSASGIMiddleware:
    """ASGI middleware that adds CORS headers to ALL responses.

    The Starlette CORSMiddleware only covers the inner FastAPI app,
    but socketio.ASGIApp wraps FastAPI, so preflight/OPTIONS requests
    to /socket.io/* and sometimes /api/* never reach FastAPI's middleware.
    This outer wrapper guarantees every HTTP response carries the
    correct Access-Control-* headers.
    """

    def __init__(self, app, allowed_origins):
        self.app = app
        self.allowed_origins = set(allowed_origins)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            # WebSocket / lifespan — pass through unchanged
            await self.app(scope, receive, send)
            return

        # Extract Origin header from the request
        origin = ""
        for key, val in scope.get("headers", []):
            if key == b"origin":
                origin = val.decode("latin-1")
                break

        if not origin or origin not in self.allowed_origins:
            # No origin or not allowed — pass through without CORS headers
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")

        # ── Handle preflight OPTIONS ──
        if method == "OPTIONS":
            cors_headers = [
                (b"access-control-allow-origin", origin.encode()),
                (b"access-control-allow-methods", b"GET, POST, PUT, DELETE, PATCH, OPTIONS, HEAD"),
                (b"access-control-allow-headers", b"content-type, authorization, x-requested-with, accept, origin"),
                (b"access-control-allow-credentials", b"true"),
                (b"access-control-max-age", b"86400"),
                (b"content-length", b"0"),
            ]
            await send({"type": "http.response.start", "status": 200, "headers": cors_headers})
            await send({"type": "http.response.body", "body": b""})
            return

        # ── Normal requests — inject CORS headers if not already present ──
        async def send_with_cors(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {k.lower() for k, _ in headers}
                if b"access-control-allow-origin" not in existing:
                    headers.append((b"access-control-allow-origin", origin.encode()))
                if b"access-control-allow-credentials" not in existing:
                    headers.append((b"access-control-allow-credentials", b"true"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_cors)


# Mount Socket.IO on the FastAPI app, then wrap with outer CORS
_raw_socket_app = socketio.ASGIApp(sio, app)
socket_app = CORSASGIMiddleware(_raw_socket_app, ALLOWED_ORIGINS)

engine = RoundEngine(db)
user_manager = UserManager(db)

@app.get("/api/time")
def get_server_time():
    """Returns the current server time in ISO format for client sync."""
    return {"iso": datetime.now(tz=timezone.utc).isoformat()}

# ─── Background game loop state ───
_active_game_tasks = {}  # round_id -> asyncio.Task
BINGO_NUMBERS = list(range(1, 76))
NUMBER_CALL_INTERVAL = 5  # seconds

# Cartela generation progress tracking
_cartela_gen_progress = {"status": "idle", "generated": 0, "total": 500, "error": None}


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
# Server-Side Game Loop
# ═══════════════════════════════════════════════════════════════
async def _game_loop(round_id: str):
    """Background task: wait for selection deadline, then start if players exist."""
    try:
        while True:
            round_doc = db.collection('rounds').document(round_id).get()
            if not round_doc.exists:
                return
            data = round_doc.to_dict()
            status = data.get('status')

            if status == 'completed' or status is None:
                return

            if status == 'playing':
                break

            # Wait for selection deadline to expire before starting
            deadline = data.get('selection_deadline')
            if deadline:
                if isinstance(deadline, datetime):
                    dl_dt = deadline
                elif isinstance(deadline, str):
                    try:
                        dl_dt = datetime.fromisoformat(deadline)
                    except:
                        dl_dt = datetime.now(tz=timezone.utc)
                else:
                    dl_dt = datetime.now(tz=timezone.utc)
                
                if dl_dt.tzinfo is None:
                    dl_dt = dl_dt.replace(tzinfo=timezone.utc)
                
                if datetime.now(tz=timezone.utc) >= dl_dt:
                    # Timer expired — start game if players exist
                    player_count = data.get('player_count', 0)
                    if player_count > 0:
                        now = datetime.now(tz=timezone.utc)
                        round_stake = data.get('stake', DEFAULT_STAKE)
                        total_pool = player_count * round_stake
                        derash = total_pool * 0.75
                        db.collection('rounds').document(round_id).update({
                            'status': 'playing',
                            'derash': derash,
                            'game_started_at': now,
                            'next_number_at': now + timedelta(seconds=NUMBER_CALL_INTERVAL),
                        })
                        await broadcast_event('rounds', round_id)
                        break
                    else:
                        # Grace period: wait 5s for late joins before cancelling
                        await asyncio.sleep(5)
                        recheck = db.collection('rounds').document(round_id).get()
                        if not recheck.exists:
                            return
                        recheck_data = recheck.to_dict()
                        if recheck_data.get('status') != 'selecting':
                            # Status changed (e.g. player joined via transaction), re-enter loop
                            continue
                        recheck_pc = recheck_data.get('player_count', 0)
                        if recheck_pc > 0:
                            # Player joined during grace period — start the game
                            now = datetime.now(tz=timezone.utc)
                            round_stake = recheck_data.get('stake', DEFAULT_STAKE)
                            total_pool = recheck_pc * round_stake
                            derash = total_pool * 0.75
                            db.collection('rounds').document(round_id).update({
                                'status': 'playing',
                                'derash': derash,
                                'game_started_at': now,
                                'next_number_at': now + timedelta(seconds=NUMBER_CALL_INTERVAL),
                            })
                            await broadcast_event('rounds', round_id)
                            break
                        # Still no players — cancel
                        db.collection('rounds').document(round_id).update({
                            'status': 'completed',
                            'winners': [],
                            'winner_name': 'No players',
                            'prize_per_winner': 0,
                            'admin_profit': 0,
                            'payout_processed': True,
                            'completed_at': datetime.now(tz=timezone.utc),
                        })
                        await broadcast_event('rounds', round_id)
                        return

            await asyncio.sleep(1)

        # Now call numbers every 5 seconds
        called = []
        while True:
            round_doc = db.collection('rounds').document(round_id).get()
            if not round_doc.exists:
                return
            data = round_doc.to_dict()

            if data.get('status') != 'playing':
                # The frontend completes the round when someone hits Bingo.
                # If there are winners, distribute the dynamic derash here cleanly.
                winners = data.get('winners', [])
                if winners and not data.get('payout_processed'):
                    try:
                        await engine.end_round(round_id, [int(w) for w in winners])
                    except Exception as e:
                        logger.error(f"[GameLoop] Error distributing prizes for {round_id}: {e}")
                        return  # Don't mark as processed if payout failed
                    for uid in winners:
                        try: await broadcast_event('users', str(uid))
                        except: pass
                    db.collection('rounds').document(round_id).update({'payout_processed': True})
                    await broadcast_event('rounds', round_id)
                return

            already_called = set(data.get('called_numbers', []))
            available = [n for n in BINGO_NUMBERS if n not in already_called]

            if not available:
                # All 75 numbers called, no winner — complete the round
                player_count = data.get('player_count', 0)
                # Mark all players as not playing and count as losses
                for uid_str in data.get('players', {}):
                    user_ref = db.collection('users').document(uid_str)
                    user_doc = user_ref.get()
                    if user_doc.exists:
                        ud = user_doc.to_dict()
                        user_ref.update({
                            'losses': ud.get('losses', 0) + 1,
                            'is_playing': False,
                            'updated_at': datetime.now(tz=timezone.utc),
                        })

                db.collection('rounds').document(round_id).update({
                    'status': 'completed',
                    'winners': [],
                    'winner_name': 'No winner',
                    'prize_per_winner': 0,
                    'admin_profit': 0,
                    'payout_processed': True,
                    'completed_at': datetime.now(tz=timezone.utc),
                })
                await broadcast_event('rounds', round_id)
                return
            # After 60 numbers, bypass predictor to ensure a winner is found
            num_called_so_far = len(data.get('called_numbers', []))
            try:
                if num_called_so_far >= 60:
                    import random as _rand
                    number = _rand.choice(available)
                    now_ts = datetime.now(tz=timezone.utc)
                    called_list = list(data.get('called_numbers', []))
                    called_list.append(number)
                    db.collection('rounds').document(round_id).update({
                        'called_numbers': called_list,
                        'last_called_number': number,
                        'last_called_at': now_ts,
                        'next_number_at': now_ts + timedelta(seconds=NUMBER_CALL_INTERVAL),
                    })
                    await broadcast_event('rounds', round_id)
                else:
                    number = await engine.call_number(round_id)
                    await broadcast_event('rounds', round_id)
            except Exception as e:
                logger.warning(f"Smart predictor error for {round_id}: {e}")
                # Fallback to pure random choice if predictor crashes
                import random
                number = random.choice(available)
                called = list(data.get('called_numbers', []))
                called.append(number)
                now = datetime.now(tz=timezone.utc)
                db.collection('rounds').document(round_id).update({
                    'called_numbers': called,
                    'last_called_number': number,
                    'last_called_at': now,
                    'next_number_at': now + timedelta(seconds=NUMBER_CALL_INTERVAL),
                })
                await broadcast_event('rounds', round_id)
                
            if number is None:
                await asyncio.sleep(NUMBER_CALL_INTERVAL)
                continue

            # ── SERVER-SIDE BINGO CHECK (authoritative) ──
            round_doc = db.collection('rounds').document(round_id).get()
            if not round_doc.exists:
                return
            rd_after = round_doc.to_dict()
            if rd_after.get('status') != 'playing':
                # Client already completed it; handle payout
                winners = rd_after.get('winners', [])
                if winners and not rd_after.get('payout_processed'):
                    try:
                        await engine.end_round(round_id, [int(w) for w in winners])
                    except Exception as e:
                        logger.error(f"[GameLoop] Error distributing prizes: {e}")
                    db.collection('rounds').document(round_id).update({'payout_processed': True})
                return

            called_now = rd_after.get('called_numbers', [])
            players = rd_after.get('players', {})
            bingo_winner_id = None
            bingo_cartela = None

            for uid_str, p_info in players.items():
                for cnum in p_info.get('cartelas', []):
                    cartela_doc = db.collection('cartelas_master').document(str(cnum)).get()
                    if not cartela_doc.exists:
                        continue
                    flat = cartela_doc.to_dict().get('cartela', [])
                    if engine.check_bingo_for_cartela(flat, called_now):
                        bingo_winner_id = uid_str
                        bingo_cartela = cnum
                        break
                if bingo_winner_id:
                    break

            if bingo_winner_id:
                now = datetime.now(tz=timezone.utc)
                player_count = rd_after.get('player_count', 1)
                round_stake = rd_after.get('stake', DEFAULT_STAKE)
                prize_per_winner = round(player_count * round_stake * 0.75)
                db.collection('rounds').document(round_id).update({
                    'status': 'completed',
                    'winners': [bingo_winner_id],
                    'winner_name': players.get(bingo_winner_id, {}).get('name', 'Player'),
                    'winning_cartela': int(bingo_cartela),
                    'prize_per_winner': prize_per_winner,
                    'completed_at': now,
                })
                await broadcast_event('rounds', round_id)
                # Process payout (handles wallet credit, wins/losses tracking)
                try:
                    await engine.end_round(round_id, [int(bingo_winner_id)])
                except Exception as e:
                    logger.error(f"[GameLoop] Error distributing prizes: {e}")
                # Broadcast user updates so frontend sees balance/wins change
                for uid in list(players.keys()) + [bingo_winner_id]:
                    try: await broadcast_event('users', str(uid))
                    except: pass
                db.collection('rounds').document(round_id).update({'payout_processed': True})
                await broadcast_event('rounds', round_id)
                logger.info(f"[GameLoop] BINGO! Player {bingo_winner_id} won round {round_id} with cartela {bingo_cartela}")
                return

            await asyncio.sleep(NUMBER_CALL_INTERVAL)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"[GameLoop] Error for round {round_id}: {e}", exc_info=True)
    finally:
        _active_game_tasks.pop(round_id, None)


def _start_game_loop(round_id: str):
    """Start a background game loop for a round if one isn't already running."""
    if round_id in _active_game_tasks:
        return  # already running
    task = asyncio.create_task(_game_loop(round_id))
    _active_game_tasks[round_id] = task


@app.on_event("startup")
async def start_background_monitor():
    """Startup: monitors rounds AND broadcasts WS events."""
    async def _monitor():
        while True:
            try:
                # Find all currently active rounds (selecting or playing)
                def _read_rounds():
                    selecting = list(db.collection('rounds').where('status', '==', 'selecting').get())
                    playing = list(db.collection('rounds').where('status', '==', 'playing').get())
                    return selecting, playing
                selecting_docs, playing_docs = await asyncio.to_thread(_read_rounds)
                
                # Start game loops for any selecting rounds that haven't been started
                for doc in selecting_docs:
                    rid = doc.id
                    if rid not in _active_game_tasks:
                        _start_game_loop(rid)
                        
                # ── Continuous Loop Enforcement ──
                # Ensure every stake has an active round (selecting or playing).
                active_stakes = set()
                for doc in selecting_docs + playing_docs:
                    rd = doc.to_dict()
                    s = rd.get('stake', DEFAULT_STAKE)
                    active_stakes.add(s)
                for stake_val in VALID_STAKES:
                    if stake_val not in active_stakes:
                        result = await engine.create_round(stake=stake_val)
                        if 'id' in result:
                            _start_game_loop(result['id'])
                        
            except Exception as e:
                logger.warning(f"Error in background monitor: {e}")
            await asyncio.sleep(5)
    asyncio.create_task(_monitor())
    asyncio.create_task(_event_broadcast_loop())


# ═══════════════════════════════════════════════════════════════
# Cartela Management
# ═══════════════════════════════════════════════════════════════
@app.post("/api/cartelas/generate")
async def generate_cartelas():
    global _cartela_gen_progress
    import threading
    logger.info(f"[CART-DBG] ENDPOINT ENTERED thread={threading.current_thread().name}")
    
    # If already generating, return current status
    if _cartela_gen_progress["status"] == "generating":
        logger.info("[CART-DBG] Already generating, returning current progress")
        return {"status": "generating", "generated": _cartela_gen_progress["generated"], "total": _cartela_gen_progress["total"]}
    
    # Check if cartelas already exist
    existing = list(engine.master_ref.limit(1).get())
    if existing:
        count = len(list(engine.master_ref.get()))
        logger.info(f"[CART-DBG] Cartelas already exist, count={count}")
        return {"status": "already_exists", "count": count}
    
    # Start background generation
    _cartela_gen_progress = {"status": "generating", "generated": 0, "total": 500, "error": None}
    logger.info("[CART-DBG] Starting background cartela generation")
    
    def _run_generation():
        global _cartela_gen_progress
        try:
            result = engine._generate_all_cartelas_sync()
            _cartela_gen_progress["status"] = "done"
            _cartela_gen_progress["generated"] = result.get("count", 0)
            logger.info(f"[CART-DBG] Background generation complete: {result}")
            # Schedule broadcast
            try:
                asyncio.get_event_loop().call_soon_threadsafe(
                    lambda: asyncio.ensure_future(broadcast_cartelas_update())
                )
            except Exception as broadcast_err:
                logger.warning(f"[CART-DBG] Failed to schedule broadcast: {broadcast_err}")
        except Exception as e:
            _cartela_gen_progress["status"] = "error"
            _cartela_gen_progress["error"] = str(e)
            logger.error(f"[CART-DBG] Background generation FAILED: {e}", exc_info=True)
    
    thread = threading.Thread(target=_run_generation, daemon=True)
    thread.start()
    
    return {"status": "generating", "generated": 0, "total": 500}


@app.get("/api/cartelas/status")
async def cartela_status():
    """Check cartela generation progress."""
    return _cartela_gen_progress


@app.post("/api/cartelas/reset")
async def reset_cartela_status():
    """Reset cartela generation status (admin use)."""
    global _cartela_gen_progress
    _cartela_gen_progress = {"status": "idle", "generated": 0, "total": 500, "error": None}
    return {"status": "reset"}


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
async def create_round(stake: int = FastAPIQuery(default=DEFAULT_STAKE)):
    """Create a new round (or return existing active one) for a given stake."""
    result = await engine.create_round(stake=stake)
    if 'id' in result:
        _start_game_loop(result['id'])
    return {"round": result}


@app.post("/api/rounds/{round_id}/join")
async def join_round(round_id: str, req: JoinRoundRequest):
    """Player joins a round with chosen cartelas."""
    result = await engine.join_round(
        round_id, req.user_id, req.cartela_numbers, req.user_name
    )
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    # Broadcast real-time cartela pool update
    await broadcast_cartela_pool(round_id)
    await broadcast_event('rounds', round_id)
    return result


@app.post("/api/rounds/{round_id}/start")
async def start_round(round_id: str):
    """Start the round (transition from selecting to playing)."""
    result = await engine.start_round(round_id)
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    _start_game_loop(round_id)
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
    # Cancel game loop if running
    task = _active_game_tasks.pop(round_id, None)
    if task:
        task.cancel()
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
    return {"status": "healthy", "timestamp": datetime.now(tz=timezone.utc).isoformat()}


@app.head("/")
async def head_root():
    return Response(status_code=200)



# ═══════════════════════════════════════════════════════════════
# Admin-Specific Endpoints  (Dashboard → SQL directly)
# ═══════════════════════════════════════════════════════════════

class DepositActionRequest(BaseModel):
    note: str = ""

class BalanceEditRequest(BaseModel):
    new_balance: float

class UserBanRequest(BaseModel):
    banned: bool

class SystemStatusRequest(BaseModel):
    online: bool

class SettingsRequest(BaseModel):
    data: dict


@app.get("/api/validate-withdrawal/{user_id}")
async def validate_withdrawal(user_id: str, amount: float):
    """Validate a withdrawal request from the web dashboard."""
    from handlers.user_manager import UserManager
    um = UserManager(db)
    result = await um.validate_withdrawal(int(user_id), amount)
    return result


@app.get("/api/admin/deposits")
async def admin_get_deposits(status: Optional[str] = None, limit: int = 50):
    ref = db.collection('deposits')
    if status:
        ref = ref.where('status', '==', status)
    ref = ref.order_by('createdAt', 'DESCENDING').limit(limit)
    docs = ref.get()
    return [{"id": d.id, **d.to_dict()} for d in docs]


@app.post("/api/admin/deposits/{deposit_id}/approve")
async def admin_approve_deposit(deposit_id: str, req: DepositActionRequest):
    dep_snap = db.collection('deposits').document(deposit_id).get()
    if not dep_snap.exists:
        raise HTTPException(status_code=404, detail="Deposit not found")
    d = dep_snap.to_dict()
    if d.get('status') != 'pending':
        raise HTTPException(status_code=400, detail=f"Deposit already {d.get('status')}")
    amount = d.get('amount', 0)
    user_id = str(d.get('userId', ''))

    # Credit user balance
    user_snap = db.collection('users').document(user_id).get()
    if not user_snap.exists:
        raise HTTPException(status_code=404, detail="User not found")
    user_data = user_snap.to_dict()
    db.collection('users').document(user_id).update({
        'balance': (user_data.get('balance', 0) or 0) + amount,
        'updated_at': datetime.now(tz=timezone.utc).isoformat()
    })
    db.collection('deposits').document(deposit_id).update({
        'status': 'approved',
        'processedAt': datetime.now(tz=timezone.utc).isoformat(),
        'adminNote': req.note or 'Approved by admin'
    })

    # Notify user via bot
    try:
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(
            chat_id=int(user_id),
            text=f"✅ Deposit approved!\n💰 {amount} ETB has been added to your wallet."
        )
    except Exception:
        pass

    return {"ok": True, "amount": amount, "user_id": user_id}


@app.post("/api/admin/deposits/{deposit_id}/reject")
async def admin_reject_deposit(deposit_id: str, req: DepositActionRequest):
    dep_snap = db.collection('deposits').document(deposit_id).get()
    if not dep_snap.exists:
        raise HTTPException(status_code=404, detail="Deposit not found")
    d = dep_snap.to_dict()
    if d.get('status') != 'pending':
        raise HTTPException(status_code=400, detail=f"Deposit already {d.get('status')}")
    user_id = str(d.get('userId', ''))
    note = req.note or 'Rejected by admin'

    db.collection('deposits').document(deposit_id).update({
        'status': 'rejected',
        'processedAt': datetime.now(tz=timezone.utc).isoformat(),
        'adminNote': note
    })
    try:
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(
            chat_id=int(user_id),
            text=f"❌ Deposit rejected.\nReason: {note}\nPlease contact support if you need help."
        )
    except Exception:
        pass
    return {"ok": True}


class WithdrawalNotifyRequest(BaseModel):
    withdrawal_id: str
    user_id: int
    first_name: str
    username: str
    amount: int
    phone: str
    telebirr_name: str


@app.post("/api/admin/withdrawals/notify")
async def notify_admin_withdrawal(req: WithdrawalNotifyRequest):
    """Send Telegram notification to admin when withdrawal is created from web dashboard."""
    try:
        from config import ADMIN_BOT_TOKEN, ADMIN_CHAT_ID
        if ADMIN_BOT_TOKEN and ADMIN_CHAT_ID:
            import httpx
            text = (
                f"🎰 *New Withdrawal Request*\n\n"
                f"👤 User: {req.first_name} (@{req.username})\n"
                f"🆔 ID: `{req.user_id}`\n"
                f"💰 Amount: *{req.amount} ETB*\n"
                f"📱 Phone: {req.phone}\n"
                f"📛 TeleBirr: {req.telebirr_name}\n"
                f"📋 ID: `{req.withdrawal_id}`"
            )
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "✅ Approve", "callback_data": f"approve_withdraw_{req.withdrawal_id}"},
                        {"text": "❌ Reject", "callback_data": f"reject_withdraw_{req.withdrawal_id}"}
                    ]
                ]
            }
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.telegram.org/bot{ADMIN_BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": int(ADMIN_CHAT_ID),
                        "text": text,
                        "parse_mode": "Markdown",
                        "reply_markup": keyboard
                    },
                    timeout=10
                )
        return {"ok": True}
    except Exception as e:
        logger.warning(f"[NotifyAdmin] Error: {e}")
        return {"ok": True}


@app.get("/api/admin/withdrawals")
async def admin_get_withdrawals(status: Optional[str] = None, limit: int = 50):
    ref = db.collection('withdrawals')
    if status:
        ref = ref.where('status', '==', status)
    ref = ref.order_by('createdAt', 'DESCENDING').limit(limit)
    docs = ref.get()
    return [{"id": d.id, **d.to_dict()} for d in docs]


@app.post("/api/admin/withdrawals/{withdrawal_id}/approve")
async def admin_approve_withdrawal(withdrawal_id: str, req: DepositActionRequest):
    snap = db.collection('withdrawals').document(withdrawal_id).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Withdrawal not found")
    d = snap.to_dict()
    if d.get('status') != 'pending':
        raise HTTPException(status_code=400, detail=f"Already {d.get('status')}")
    amount = d.get('amount', 0)
    user_id = str(d.get('userId', ''))

    db.collection('withdrawals').document(withdrawal_id).update({
        'status': 'approved',
        'processedAt': datetime.now(tz=timezone.utc).isoformat(),
        'adminNote': req.note or 'Approved by admin'
    })
    # Deduct balance on approval
    user_snap = db.collection('users').document(user_id).get()
    if user_snap.exists:
        u = user_snap.to_dict()
        db.collection('users').document(user_id).update({
            'balance': (u.get('balance', 0) or 0) - amount,
            'updated_at': datetime.now(tz=timezone.utc).isoformat()
        })
    try:
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(
            chat_id=int(user_id),
            text=f"✅ Withdrawal approved!\n💸 {amount} ETB will be sent to your TeleBirr account."
        )
    except Exception:
        pass
    return {"ok": True, "amount": amount, "user_id": user_id}


@app.post("/api/admin/withdrawals/{withdrawal_id}/reject")
async def admin_reject_withdrawal(withdrawal_id: str, req: DepositActionRequest):
    snap = db.collection('withdrawals').document(withdrawal_id).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Withdrawal not found")
    d = snap.to_dict()
    if d.get('status') != 'pending':
        raise HTTPException(status_code=400, detail=f"Already {d.get('status')}")
    amount = d.get('amount', 0)
    user_id = str(d.get('userId', ''))
    note = req.note or 'Rejected by admin'

    db.collection('withdrawals').document(withdrawal_id).update({
        'status': 'rejected',
        'processedAt': datetime.now(tz=timezone.utc).isoformat(),
        'adminNote': note
    })
    try:
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(
            chat_id=int(user_id),
            text=f"❌ Withdrawal rejected.\nReason: {note}"
        )
    except Exception:
        pass
    return {"ok": True}


@app.patch("/api/admin/users/{user_id}/balance")
async def admin_edit_balance(user_id: int, req: BalanceEditRequest):
    snap = db.collection('users').document(str(user_id)).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="User not found")
    db.collection('users').document(str(user_id)).update({
        'balance': req.new_balance,
        'updated_at': datetime.now(tz=timezone.utc).isoformat()
    })
    return {"ok": True}


@app.patch("/api/admin/users/{user_id}/ban")
async def admin_ban_user(user_id: int, req: UserBanRequest):
    snap = db.collection('users').document(str(user_id)).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="User not found")
    db.collection('users').document(str(user_id)).update({
        'banned': req.banned,
        'updated_at': datetime.now(tz=timezone.utc).isoformat()
    })
    return {"ok": True}


@app.get("/api/admin/status")
async def admin_get_status():
    snap = db.collection('system').document('admin_status').get()
    if snap.exists:
        return snap.to_dict()
    return {"online": False}


@app.post("/api/admin/status")
async def admin_set_status(req: SystemStatusRequest):
    db.collection('system').document('admin_status').set({
        'online': req.online,
        'updatedAt': datetime.now(tz=timezone.utc).isoformat()
    })
    return {"ok": True, "online": req.online}


@app.get("/api/admin/settings")
async def admin_get_settings():
    snap = db.collection('settings').document('game').get()
    if snap.exists:
        return snap.to_dict()
    return {}


@app.post("/api/admin/settings")
async def admin_save_settings(req: SettingsRequest):
    db.collection('settings').document('game').set(req.data, merge=True)
    return {"ok": True}


@app.post("/api/admin/bot-content/seed")
async def seed_bot_content():
    """Seed the bot_content collection with all default messages."""
    from handlers.bot_content import DEFAULTS, invalidate_cache
    count = 0
    for key, value in DEFAULTS.items():
        cat = key.split('_')[0]
        db.collection('bot_content').document(key).set({
            'key': key,
            'content': value,
            'category': cat,
            'updatedAt': datetime.now(tz=timezone.utc).isoformat(),
        })
        count += 1
    invalidate_cache()
    return {"ok": True, "seeded": count}


@app.get("/api/admin/bot-content")
async def get_bot_content():
    """Get all bot content messages."""
    docs = db.collection('bot_content').get()
    return [{"id": d.id, **d.to_dict()} for d in docs]


@app.post("/api/admin/bot-content/{key}")
async def save_bot_content(key: str, req: SettingsRequest):
    """Save a bot content message."""
    from handlers.bot_content import invalidate_cache
    db.collection('bot_content').document(key).set(req.data, merge=True)
    invalidate_cache(key)
    return {"ok": True}


# ─── Dashboard & game (served from same service as API + bots) ───


class DocSetRequest(BaseModel):
    data: dict
    merge: bool = False

class DocUpdateRequest(BaseModel):
    data: dict

class QueryRequest(BaseModel):
    filters: list = []
    order_by: Optional[str] = None
    order_dir: str = "ASCENDING"
    limit_n: Optional[int] = None


@app.get("/api/db/{collection}/{doc_id}")
async def db_get_doc(collection: str, doc_id: str):
    snap = db.collection(collection).document(doc_id).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"id": snap.id, "data": snap.to_dict()}


@app.post("/api/db/{collection}/{doc_id}")
async def db_set_doc(collection: str, doc_id: str, req: DocSetRequest):
    db.collection(collection).document(doc_id).set(req.data, merge=req.merge)
    await broadcast_event(collection, doc_id)
    return {"ok": True}


@app.patch("/api/db/{collection}/{doc_id}")
async def db_update_doc(collection: str, doc_id: str, req: DocUpdateRequest):
    try:
        db.collection(collection).document(doc_id).update(req.data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await broadcast_event(collection, doc_id)
    return {"ok": True}


@app.delete("/api/db/{collection}/{doc_id}")
async def db_delete_doc(collection: str, doc_id: str):
    db.collection(collection).document(doc_id).delete()
    return {"ok": True}


@app.get("/api/db/{collection}")
async def db_query_collection(
    collection: str,
    filters: Optional[str] = None,  # JSON string: [[field,op,val],...]
    order_by: Optional[str] = None,
    order_dir: str = "ASCENDING",
    limit_n: Optional[int] = None
):
    ref = db.collection(collection)
    if filters:
        try:
            for f in json.loads(filters):
                ref = ref.where(f[0], f[1], f[2])
        except Exception:
            pass
    if order_by:
        ref = ref.order_by(order_by, order_dir)
    if limit_n:
        ref = ref.limit(limit_n)
    docs = ref.get()
    return [{"id": d.id, "data": d.to_dict()} for d in docs]


@app.post("/api/db/{collection}")
async def db_add_doc(collection: str, req: DocSetRequest):
    ref = db.collection(collection).add(req.data)
    return {"id": ref.id}


# ─── Socket.IO Events ───
@sio.event
async def connect(sid, environ):
    """Client connected."""
    pass

@sio.event
async def disconnect(sid):
    """Client disconnected."""
    pass

@sio.event
async def subscribe(sid, data):
    """Client subscribes to a collection/doc for real-time updates."""
    collection = data.get('collection')
    doc_id = data.get('doc_id')
    room = f"{collection}:{doc_id}" if doc_id else collection
    await sio.enter_room(sid, room)

@sio.event
async def unsubscribe(sid, data):
    """Client unsubscribes from a collection/doc."""
    collection = data.get('collection')
    doc_id = data.get('doc_id')
    room = f"{collection}:{doc_id}" if doc_id else collection
    await sio.leave_room(sid, room)

async def broadcast_event(collection: str, doc_id: str):
    """Emit updated snapshot to all subscribers of this collection/doc."""
    room_exact = f"{collection}:{doc_id}"
    room_collection = collection

    def _read_doc():
        return db.collection(collection).document(doc_id).get()

    def _read_all():
        return db.collection(collection).get()

    snap = await asyncio.to_thread(_read_doc)
    payload = {
        "type": "snapshot",
        "collection": collection,
        "id": doc_id,
        "data": snap.to_dict() if snap.exists else None,
        "exists": snap.exists
    }
    await sio.emit('snapshot', payload, room=room_exact)

    docs = await asyncio.to_thread(_read_all)
    query_payload = {
        "type": "query_snapshot",
        "collection": collection,
        "docs": [{"id": d.id, "data": d.to_dict()} for d in docs]
    }
    await sio.emit('query_snapshot', query_payload, room=room_collection)

async def broadcast_cartelas_update():
    """Safely broadcast cartela pool update to all admin dashboards."""
    try:
        def _read_cartelas():
            docs = db.collection('cartelas_master').get()
            return [{"id": d.id, "data": d.to_dict()} for d in docs]
        cartela_list = await asyncio.to_thread(_read_cartelas)
        await sio.emit('query_snapshot', {
            "type": "query_snapshot",
            "collection": "cartelas_master",
            "docs": cartela_list,
        }, room="cartelas_master")
    except Exception as e:
        logger.warning(f"Error broadcasting cartelas update: {e}")


async def broadcast_cartela_pool(round_id: str):
    """Emit real-time cartela pool update to all clients watching this round."""
    round_snap = db.collection('rounds').document(round_id).get()
    if round_snap.exists:
        rd = round_snap.to_dict()
        await sio.emit('cartela_pool', {
            "type": "cartela_pool",
            "round_id": round_id,
            "taken_cartelas": rd.get('taken_cartelas', []),
            "player_count": rd.get('player_count', 0),
        }, room=f"rounds:{round_id}")


# ─── Background event broadcaster ───
async def _event_broadcast_loop():
    """Poll system_events table and push Socket.IO updates to subscribed clients."""
    last_id = ""
    while True:
        sess = None
        try:
            sess = SessionLocal()
            events = sess.query(SystemEvent)
            if last_id:
                events = events.filter(SystemEvent.id > last_id)
            events = events.order_by(SystemEvent.created_at).limit(50).all()
            for ev in events:
                last_id = ev.id
                try:
                    await broadcast_event(ev.collection, ev.doc_id)
                except Exception as ev_err:
                    logger.warning(f"Error broadcasting event {ev.collection}/{ev.doc_id}: {ev_err}")
        except Exception as e:
            logger.warning(f"Error in event broadcast loop: {e}")
        finally:
            if sess:
                sess.close()
        await asyncio.sleep(0.5)


# (startup merged into start_background_monitor above)


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


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


if os.path.isdir(os.path.join(DASHBOARD_DIR, "css")):
    app.mount("/css", StaticFiles(directory=os.path.join(DASHBOARD_DIR, "css")), name="css")
if os.path.isdir(os.path.join(DASHBOARD_DIR, "js")):
    app.mount("/js", StaticFiles(directory=os.path.join(DASHBOARD_DIR, "js")), name="js")
if os.path.isdir(os.path.join(DASHBOARD_DIR, "pages")):
    app.mount("/pages", StaticFiles(directory=os.path.join(DASHBOARD_DIR, "pages")), name="pages")
if os.path.isdir(os.path.join(DASHBOARD_DIR, "components")):
    app.mount("/components", StaticFiles(directory=os.path.join(DASHBOARD_DIR, "components")), name="components")
if os.path.isdir(os.path.join(DASHBOARD_DIR, "public", "audio")):
    app.mount("/audio", StaticFiles(directory=os.path.join(DASHBOARD_DIR, "public", "audio")), name="audio")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(socket_app, host="0.0.0.0", port=port)

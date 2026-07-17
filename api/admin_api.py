import os
import random
import asyncio
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query as FastAPIQuery
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from typing import List, Optional
import json
import datetime
from config import db, BOT_TOKEN
from firestore_db import MockFirestoreClient, SessionLocal, SystemEvent, FieldFilter, Increment, ArrayUnion

from game.round_engine import RoundEngine, STAKE, PRIZE_MULTIPLIER
from handlers.user_manager import UserManager
from datetime import datetime, timedelta, timezone
from telegram import Bot
# Firebase replaced by SQLAlchemy emulator (firestore_db.py)

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

# ─── Background game loop state ───
_active_game_tasks = {}  # round_id -> asyncio.Task
BINGO_NUMBERS = list(range(1, 76))
NUMBER_CALL_INTERVAL = 4  # seconds


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
    """Background task: auto-start round after selection deadline, then call numbers."""
    try:
        # Wait for selection deadline to pass
        while True:
            round_doc = db.collection('rounds').document(round_id).get()
            if not round_doc.exists:
                return
            data = round_doc.to_dict()
            status = data.get('status')

            if status == 'completed' or status is None:
                return  # round was cancelled/completed externally

            if status == 'playing':
                break  # already started (e.g. by client)

            # Check if selection deadline has passed
            deadline = data.get('selection_deadline')
            if deadline:
                dl_dt = deadline if isinstance(deadline, datetime) else deadline.to_datetime()
                if datetime.now(tz=timezone.utc) >= dl_dt:
                    # Auto-start the round (even with 0 players)
                    now = datetime.now(tz=timezone.utc)
                    player_count = data.get('player_count', 0)
                    total_pool = player_count * STAKE
                    derash = total_pool * 0.75
                    
                    db.collection('rounds').document(round_id).update({
                        'status': 'playing',
                        'derash': derash,
                        'game_started_at': now,
                        'next_number_at': now + timedelta(seconds=NUMBER_CALL_INTERVAL),
                    })
                    break

            await asyncio.sleep(1)

        # Now call numbers every 4 seconds
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
                        pass
                    db.collection('rounds').document(round_id).update({'payout_processed': True})
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
                return

            # Pick a random number
            number = random.choice(available)
            called.append(number)

            now = datetime.now(tz=timezone.utc)
            next_at = now + timedelta(seconds=NUMBER_CALL_INTERVAL)
            db.collection('rounds').document(round_id).update({
                'called_numbers': firestore.ArrayUnion([number]),
                'last_called_number': number,
                'last_called_at': now,
                'next_number_at': next_at,
            })

            await asyncio.sleep(NUMBER_CALL_INTERVAL)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[GameLoop] Error for round {round_id}: {e}")
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
                selecting_docs = list(db.collection('rounds').where('status', '==', 'selecting').get())
                playing_docs = list(db.collection('rounds').where('status', '==', 'playing').get())
                
                # Start game loops for any selecting rounds that haven't been started
                for doc in selecting_docs:
                    rid = doc.id
                    if rid not in _active_game_tasks:
                        _start_game_loop(rid)
                        
                # ── Continuous Loop Enforcement ──
                # If there are NO active rounds at all, create a new one immediately.
                if not selecting_docs and not playing_docs:
                    result = await engine.create_round()
                    if 'id' in result:
                        _start_game_loop(result['id'])
                        
            except Exception as e:
                pass  # silently skip — no Firebase quota hits
            await asyncio.sleep(5)
    asyncio.create_task(_monitor())
    asyncio.create_task(_event_broadcast_loop())


# ═══════════════════════════════════════════════════════════════
# Cartela Management
# ═══════════════════════════════════════════════════════════════
@app.post("/api/cartelas/generate")
async def generate_cartelas():
    """Generate 500 fixed cartelas (idempotent)."""
    try:
        result = await engine.generate_all_cartelas()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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

    user_snap = db.collection('users').document(user_id).get()
    if not user_snap.exists:
        raise HTTPException(status_code=404, detail="User not found")
    user_data = user_snap.to_dict()
    bal = user_data.get('balance', 0) or 0
    if bal < amount:
        raise HTTPException(status_code=400, detail=f"Insufficient balance: {bal} ETB")

    db.collection('users').document(user_id).update({
        'balance': bal - amount,
        'updated_at': datetime.now(tz=timezone.utc).isoformat()
    })
    db.collection('withdrawals').document(withdrawal_id).update({
        'status': 'approved',
        'processedAt': datetime.now(tz=timezone.utc).isoformat(),
        'adminNote': req.note or 'Approved by admin'
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
    user_id = str(d.get('userId', ''))
    amount = d.get('amount', 0)
    note = req.note or 'Rejected by admin'

    # Refund balance
    user_snap = db.collection('users').document(user_id).get()
    if user_snap.exists:
        u = user_snap.to_dict()
        db.collection('users').document(user_id).update({
            'balance': (u.get('balance', 0) or 0) + amount,
            'updated_at': datetime.now(tz=timezone.utc).isoformat()
        })
    db.collection('withdrawals').document(withdrawal_id).update({
        'status': 'rejected',
        'processedAt': datetime.now(tz=timezone.utc).isoformat(),
        'adminNote': note
    })
    try:
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(
            chat_id=int(user_id),
            text=f"❌ Withdrawal rejected.\nAmount {amount} ETB has been refunded.\nReason: {note}"
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
    return {"ok": True}


@app.patch("/api/db/{collection}/{doc_id}")
async def db_update_doc(collection: str, doc_id: str, req: DocUpdateRequest):
    try:
        db.collection(collection).document(doc_id).update(req.data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
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


# ─── WebSocket Manager ───
class ConnectionManager:
    def __init__(self):
        # Each connection: {ws, collection, doc_id (or None for collection watch)}
        self.connections: list = []

    async def connect(self, ws: WebSocket, collection: str, doc_id: Optional[str]):
        await ws.accept()
        self.connections.append({"ws": ws, "collection": collection, "doc_id": doc_id})

    def disconnect(self, ws: WebSocket):
        self.connections = [c for c in self.connections if c["ws"] is not ws]

    async def broadcast_event(self, collection: str, doc_id: str):
        """Send updated snapshot to any subscriber watching this collection/doc."""
        dead = []
        for conn in self.connections:
            if conn["collection"] != collection:
                continue
            try:
                if conn["doc_id"]:
                    if conn["doc_id"] != doc_id:
                        continue
                    snap = db.collection(collection).document(doc_id).get()
                    payload = {
                        "type": "snapshot",
                        "collection": collection,
                        "id": doc_id,
                        "data": snap.to_dict() if snap.exists else None,
                        "exists": snap.exists
                    }
                else:
                    # Query snapshot for whole collection
                    docs = db.collection(collection).get()
                    payload = {
                        "type": "query_snapshot",
                        "collection": collection,
                        "docs": [{"id": d.id, "data": d.to_dict()} for d in docs]
                    }
                await conn["ws"].send_text(json.dumps(payload))
            except Exception:
                dead.append(conn["ws"])
        for ws in dead:
            self.disconnect(ws)

ws_manager = ConnectionManager()


@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Client sends: {collection, doc_id?}  then receives live updates."""
    await websocket.accept()
    sub = None
    try:
        # First message = subscription request
        raw = await websocket.receive_text()
        msg = json.loads(raw)
        collection = msg.get("collection")
        doc_id = msg.get("doc_id")
        if not collection:
            await websocket.close(code=1003)
            return
        sub = {"ws": websocket, "collection": collection, "doc_id": doc_id}
        ws_manager.connections.append(sub)
        # Send initial snapshot
        if doc_id:
            snap = db.collection(collection).document(doc_id).get()
            payload = {
                "type": "snapshot",
                "collection": collection,
                "id": doc_id,
                "data": snap.to_dict() if snap.exists else None,
                "exists": snap.exists
            }
            await websocket.send_text(json.dumps(payload))
        else:
            docs = db.collection(collection).get()
            payload = {
                "type": "query_snapshot",
                "collection": collection,
                "docs": [{"id": d.id, "data": d.to_dict()} for d in docs]
            }
            await websocket.send_text(json.dumps(payload))
        # Keep alive and handle client disconnects
        while True:
            await websocket.receive_text()  # ping or ignored
    except WebSocketDisconnect:
        pass
    finally:
        if sub:
            ws_manager.connections = [c for c in ws_manager.connections if c["ws"] is not websocket]


# ─── Background event broadcaster ───
async def _event_broadcast_loop():
    """Poll system_events table and push WebSocket updates to subscribed clients."""
    last_id = ""
    while True:
        try:
            sess = SessionLocal()
            events = sess.query(SystemEvent)
            if last_id:
                events = events.filter(SystemEvent.id > last_id)
            events = events.order_by(SystemEvent.created_at).limit(50).all()
            for ev in events:
                last_id = ev.id
                await ws_manager.broadcast_event(ev.collection, ev.doc_id)
            sess.close()
        except Exception as e:
            pass
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


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

"""
Game engine — runs the game loop for a single stake value (10 or 20 ETB).

Communicates with the Gateway via HTTP (gateway_client.py). No local DB,
no FastAPI, no Socket.IO, no Telegram bots.

Usage:
    python run_engine.py --stake 10
    python run_engine.py --stake 20
"""

import argparse
import asyncio
import logging
import os
import sys
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

VALID_STAKES = [10, 20]


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stake", type=int, default=None, choices=VALID_STAKES)
    args = parser.parse_args()
    stake = args.stake or int(os.getenv("ENGINE_STAKE", "10"))
    if stake not in VALID_STAKES:
        print(f"Invalid stake: {stake}. Valid: {VALID_STAKES}")
        sys.exit(1)

    from gateway_client import GatewayClient
    from game.round_engine import RoundEngine
    gateway = GatewayClient()
    engine = RoundEngine(gateway)

    logger.info(f"Engine started for stake={stake} ETB")

    while True:
        try:
            active = gateway.collection('rounds') \
                .where('stake', '==', stake) \
                .where('status', 'in', ['selecting', 'playing']) \
                .limit(5).get()

            for snap in active:
                r = snap.to_dict()
                rid = snap.id

                if r.get('status') == 'selecting':
                    await _handle_selection(rid, r, engine)
                elif r.get('status') == 'playing':
                    await _call_next_number(rid, r, engine, gateway)

        except Exception as e:
            logger.error(f"Engine error: {e}", exc_info=True)

        await asyncio.sleep(2)


async def _handle_selection(round_id: str, data: dict, engine):
    """Start round if selection deadline passed."""
    from datetime import datetime, timezone

    deadline_str = data.get('selection_deadline')
    if not deadline_str:
        return

    deadline = datetime.fromisoformat(deadline_str.replace('Z', '+00:00'))
    now = datetime.now(tz=timezone.utc)
    wait = (deadline - now).total_seconds() + 5  # 5s grace

    if wait > 0:
        return  # Not yet — will check again next poll

    players = data.get('players', {}) or {}
    if not players:
        from gateway_client import GatewayClient
        gw = GatewayClient()
        gw.collection('rounds').document(round_id).update({
            'status': 'completed',
            'completedAt': now.isoformat(),
            'reason': 'no_players'
        })
        return

    await engine.start_round(round_id)
    logger.info(f"Round {round_id} started: {len(players)} players, stake {data.get('stake')} ETB")


async def _call_next_number(round_id: str, data: dict, engine, gateway):
    """Call next number if it's time. After each call, check for a single winner and end round."""
    from datetime import datetime, timezone

    next_at = data.get('next_number_at')
    if not next_at:
        return

    if isinstance(next_at, str):
        next_at = datetime.fromisoformat(next_at.replace('Z', '+00:00'))

    if datetime.now(tz=timezone.utc) < next_at:
        return  # Not yet

    try:
        number = await engine.call_number(round_id)
        if number is not None:
            logger.info(f"Round {round_id}: called #{number}")
        else:
            return
    except Exception as e:
        logger.error(f"Round {round_id}: call_number failed: {e}")
        return

    # Re-read round after calling to check for winners
    try:
        snap = gateway.collection('rounds').document(round_id).get()
        if not snap.exists:
            return
        rd = snap.to_dict()
        if rd.get('status') != 'playing':
            return

        called_now = rd.get('called_numbers', [])
        players = rd.get('players', {}) or {}

        if not players:
            gateway.collection('rounds').document(round_id).update({
                'status': 'completed',
                'winners': [],
                'winner_name': 'No players',
                'completed_at': datetime.now(tz=timezone.utc).isoformat(),
            })
            return

        MAX_CALLS = 30
        player_cartelas = engine.build_player_cartelas(players)
        winner_entries = engine.evaluate_winners(player_cartelas, called_now)

        if winner_entries:
            chosen_winner = engine.choose_single_winner(winner_entries, players)
            if chosen_winner:
                winner_id = int(chosen_winner['user_id'])
                await engine.end_round(round_id, [winner_id])
                logger.info(f"Round {round_id}: single winner={chosen_winner.get('user_id')} cartela={chosen_winner.get('cartela_number')} after {len(called_now)} calls")
                return

        if len(called_now) >= MAX_CALLS:
            gateway.collection('rounds').document(round_id).update({
                'status': 'completed',
                'winners': [],
                'winner_name': 'No winner',
                'completed_at': datetime.now(tz=timezone.utc).isoformat(),
            })
            logger.info(f"Round {round_id}: no winner after {len(called_now)} calls")
            return
    except Exception as e:
        logger.error(f"Round {round_id}: winner check failed: {e}", exc_info=True)


async def run_health_server():
    """Minimal HTTP server for Render health checks."""
    import uvicorn
    from fastapi import FastAPI, Response
    health_app = FastAPI()

    @health_app.get("/api/health")
    async def health():
        return Response(status_code=200, content='{"status":"ok"}', media_type="application/json")

    port = int(os.environ.get("PORT", 8000))
    config = uvicorn.Config(health_app, host="0.0.0.0", port=port, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()


def start_health_server():
    import threading
    t = threading.Thread(target=lambda: asyncio.run(run_health_server()), daemon=True)
    t.start()


if __name__ == "__main__":
    start_health_server()
    asyncio.run(main())

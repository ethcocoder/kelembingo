#!/usr/bin/env python3
"""
Simulate two smart-predictor round scenarios:
1. Natural single-winner finish at the target call.
2. Forced single-winner resolution at the 30-call hard cap.

Run: python simulate_round_scenarios.py
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


TEMP_DB_PATH = Path(tempfile.gettempdir()) / f"bingo_round_sim_{uuid.uuid4().hex}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEMP_DB_PATH.as_posix()}"

from firestore_db import MockFirestoreClient  # noqa: E402
from game.round_engine import GAME_LENGTH_RANGE, RoundEngine, _CARTELA_CACHE  # noqa: E402


def make_flat_card(rows: List[List[int]]) -> List[int]:
    flat: List[int] = []
    for row in rows:
        flat.extend(row)
    return flat


def seed_cartela(db: MockFirestoreClient, number: int, flat: List[int]) -> None:
    db.collection("cartelas_master").document(str(number)).set(
        {
            "number": number,
            "cartela": flat,
            "generated_at": datetime.now(tz=timezone.utc),
        }
    )


def create_playing_round(
    db: MockFirestoreClient,
    round_id: str,
    players: Dict[str, dict],
    called_numbers: List[int],
    game_target: int,
    stake: int = 10,
) -> None:
    taken_cartelas: List[int] = []
    player_count = 0
    for info in players.values():
        cartelas = [int(num) for num in info.get("cartelas", [])]
        taken_cartelas.extend(cartelas)
        player_count += len(cartelas)

    db.collection("rounds").document(round_id).set(
        {
            "status": "playing",
            "stake": stake,
            "players": players,
            "player_count": player_count,
            "taken_cartelas": taken_cartelas,
            "called_numbers": list(called_numbers),
            "winners": [],
            "prize_per_winner": 0,
            "admin_profit": 0,
            "game_target": game_target,
            "created_at": datetime.now(tz=timezone.utc),
            "completed_at": None,
        }
    )


async def simulate_like_admin(engine: RoundEngine, round_id: str) -> dict:
    number = await engine.call_number(round_id)
    round_doc = engine.rounds_ref.document(round_id).get()
    if not round_doc.exists:
        raise RuntimeError(f"Round {round_id} disappeared during simulation")

    round_data = round_doc.to_dict()
    players = round_data.get("players", {})
    called_now = round_data.get("called_numbers", [])
    player_cartelas = engine.build_player_cartelas(players)
    winner_entries = engine.evaluate_winners(player_cartelas, called_now)

    completion_reason = None
    chosen_winner = None

    if winner_entries:
        chosen_winner = engine.choose_single_winner(winner_entries, players)
        completion_reason = (
            "smart_single_winner"
            if len(winner_entries) == 1
            else "smart_tie_break_single_winner"
        )
    elif len(called_now) >= GAME_LENGTH_RANGE[1]:
        chosen_winner = engine.get_closest_contender(player_cartelas, called_now, players)
        completion_reason = "forced_single_winner_max_30"

    return {
        "called_number": number,
        "call_count": len(called_now),
        "winner_entries": winner_entries,
        "chosen_winner": chosen_winner,
        "completion_reason": completion_reason,
    }


async def scenario_natural_single_winner() -> dict:
    _CARTELA_CACHE.clear()
    db = MockFirestoreClient()
    engine = RoundEngine(db)

    seed_cartela(
        db,
        101,
        make_flat_card(
            [
                [1, 2, 3, 4, 5],
                [31, 32, 33, 34, 35],
                [51, 52, 0, 53, 54],
                [51, 52, 53, 54, 55],
                [61, 62, 63, 64, 65],
            ]
        ),
    )
    seed_cartela(
        db,
        202,
        make_flat_card(
            [
                [1, 2, 3, 4, 6],
                [36, 37, 38, 39, 40],
                [56, 57, 0, 58, 59],
                [56, 57, 58, 59, 60],
                [66, 67, 68, 69, 70],
            ]
        ),
    )

    players = {
        "1001": {
            "cartelas": [101],
            "name": "Alpha",
            "joined_at": "2026-07-22T10:00:00+00:00",
        },
        "1002": {
            "cartelas": [202],
            "name": "Beta",
            "joined_at": "2026-07-22T10:01:00+00:00",
        },
    }
    called_numbers = [1, 2, 3, 4, 11, 12, 13, 14, 15, 16, 17, 71, 72, 73]
    create_playing_round(db, "natural-target-round", players, called_numbers, game_target=15)
    result = await simulate_like_admin(engine, "natural-target-round")

    assert result["called_number"] in {5, 6}, "Expected the predictor to finish one player cleanly"
    assert result["call_count"] == 15, "Expected the round to finish exactly at the target call"
    assert len(result["winner_entries"]) == 1, "Expected exactly one natural winner"
    assert result["completion_reason"] == "smart_single_winner", "Expected natural completion reason"
    assert result["chosen_winner"]["user_id"] in {"1001", "1002"}, "Unexpected winner chosen"
    return result


async def scenario_forced_single_winner_at_30() -> dict:
    _CARTELA_CACHE.clear()
    db = MockFirestoreClient()
    engine = RoundEngine(db)

    seed_cartela(
        db,
        301,
        make_flat_card(
            [
                [1, 2, 3, 4, 5],
                [31, 32, 33, 34, 35],
                [41, 42, 0, 43, 44],
                [51, 52, 53, 54, 55],
                [61, 62, 63, 64, 65],
            ]
        ),
    )
    seed_cartela(
        db,
        302,
        make_flat_card(
            [
                [6, 7, 8, 9, 10],
                [36, 37, 38, 39, 40],
                [45, 46, 0, 47, 48],
                [56, 57, 58, 59, 60],
                [66, 67, 68, 69, 70],
            ]
        ),
    )

    players = {
        "2001": {
            "cartelas": [301],
            "name": "Gamma",
            "joined_at": "2026-07-22T11:00:00+00:00",
        },
        "2002": {
            "cartelas": [302],
            "name": "Delta",
            "joined_at": "2026-07-22T11:01:00+00:00",
        },
    }
    called_numbers = [
        1, 2, 3,
        6, 7, 8,
        11, 12, 13, 14, 15,
        16, 17, 18, 19, 20,
        21, 22, 23, 24, 25,
        26, 27, 28, 29, 30,
        71, 72, 73,
    ]
    create_playing_round(db, "forced-cap-round", players, called_numbers, game_target=29)
    result = await simulate_like_admin(engine, "forced-cap-round")

    assert result["call_count"] == 30, "Expected the round to hit the hard 30-call cap"
    assert len(result["winner_entries"]) == 0, "Expected no natural winner at the hard cap"
    assert result["completion_reason"] == "forced_single_winner_max_30", "Expected forced completion reason"
    assert result["chosen_winner"] is not None, "Expected a forced winner selection"
    assert result["chosen_winner"]["user_id"] == "2001", "Expected tie-break to choose the earliest contender"
    return result


async def main() -> int:
    try:
        natural = await scenario_natural_single_winner()
        forced = await scenario_forced_single_winner_at_30()

        print("=" * 72)
        print("SMART PREDICTOR ROUND SIMULATION")
        print("=" * 72)
        print(
            f"[OK] Natural finish: call {natural['call_count']} used number "
            f"{natural['called_number']} -> winner {natural['chosen_winner']['user_id']} "
            f"({natural['completion_reason']})"
        )
        print(
            f"[OK] Forced finish:  call {forced['call_count']} used number "
            f"{forced['called_number']} -> winner {forced['chosen_winner']['user_id']} "
            f"({forced['completion_reason']})"
        )
        print("-" * 72)
        print("Both round simulations passed.")
        return 0
    except AssertionError as exc:
        print(f"[FAIL] {exc}")
        return 1
    finally:
        try:
            if TEMP_DB_PATH.exists():
                TEMP_DB_PATH.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

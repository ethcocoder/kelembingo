"""
Kelem Bingo — Round-Based Multiplayer Engine
=============================================
Manages 500 fixed cartelas, round lifecycle, number calling, bingo checking,
and prize distribution.
"""

import random
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple
from firestore_db import FieldFilter, transactional as firestore_transactional, Increment, ArrayUnion
from firestore_db import MockFirestoreClient

logger = logging.getLogger(__name__)


# ─── Constants ───
TOTAL_CARTELAS = 500
DEFAULT_STAKE = 10
VALID_STAKES = [10, 20]
ADMIN_CUT_RATIO = 0.25          # 25% of pool goes to admin
SELECTION_DURATION = 35          # seconds for card selection phase
NUMBER_CALL_INTERVAL = 5        # seconds between each called number (5s countdown)
MAX_CARTELAS_PER_PLAYER = 2
BINGO_NUMBERS = range(1, 76)    # 1-75
GAME_LENGTH_RANGE = (15, 30)    # random target: each round ends between 15-30 numbers

_CARTELA_CACHE = {}  # Global in-memory cache for all 500 cartela structures

class RoundEngine:
    def __init__(self, db):
        self.db = db
        self.master_ref = db.collection('cartelas_master')
        self.rounds_ref = db.collection('rounds')

    # ═══════════════════════════════════════════════════════════════
    # Cartela Generation (one-time, admin-triggered)
    # ═══════════════════════════════════════════════════════════════
    def _generate_single_cartela(self, seed: int) -> List[int]:
        """Generate a deterministic 5×5 bingo card as flat 25-int list.
        Uses seed so the same cartela number always produces the same card."""
        rng = random.Random(seed)
        cols = {
            'B': rng.sample(range(1, 16), 5),
            'I': rng.sample(range(16, 31), 5),
            'N': rng.sample(range(31, 46), 5),
            'G': rng.sample(range(46, 61), 5),
            'O': rng.sample(range(61, 76), 5),
        }
        flat = []
        for row_idx in range(5):
            flat.append(cols['B'][row_idx])
            flat.append(cols['I'][row_idx])
            # Free center space
            flat.append(0 if row_idx == 2 else cols['N'][row_idx])
            flat.append(cols['G'][row_idx])
            flat.append(cols['O'][row_idx])
        return flat

    async def generate_all_cartelas(self) -> dict:
        """Generate 500 fixed cartelas in cartelas_master. Idempotent."""
        return await asyncio.to_thread(self._generate_all_cartelas_sync)

    def _generate_all_cartelas_sync(self) -> dict:
        import threading, time as _time
        t_start = _time.monotonic()
        logger.info(f"[CART-DBG] _sync ENTERED thread={threading.current_thread().name}")
        logger.info("[CART-DBG] Checking for existing cartelas...")
        t0 = _time.monotonic()
        existing = list(self.master_ref.limit(1).get())
        logger.info(f"[CART-DBG] Existence check took {round(_time.monotonic()-t0, 2)}s, found={len(existing)}")
        if existing:
            t0 = _time.monotonic()
            count = len(list(self.master_ref.get()))
            logger.info(f"[CART-DBG] Cartelas already exist, count={count} (count query took {round(_time.monotonic()-t0, 2)}s)")
            return {'status': 'already_exists', 'count': count}

        logger.info("[CART-DBG] Starting generation of 500 cartelas...")
        batch_size = 100
        generated = 0
        for start in range(1, TOTAL_CARTELAS + 1, batch_size):
            t_batch = _time.monotonic()
            batch = self.db.batch(skip_events=True)
            end = min(start + batch_size, TOTAL_CARTELAS + 1)
            for num in range(start, end):
                cartela = self._generate_single_cartela(num * 1337)
                doc_ref = self.master_ref.document(str(num))
                batch.set(doc_ref, {
                    'number': num,
                    'cartela': cartela,
                    'generated_at': datetime.now(tz=timezone.utc),
                })
                generated += 1
            batch.commit()
            logger.info(f"[CART-DBG] Batch {start}-{end-1} committed in {round(_time.monotonic()-t_batch, 2)}s ({generated}/{TOTAL_CARTELAS})")

        total = round(_time.monotonic() - t_start, 2)
        logger.info(f"[CART-DBG] Generated {generated} cartelas in {total}s")
        return {'status': 'generated', 'count': generated}

    async def get_all_cartelas(self) -> List[dict]:
        """Return all 500 master cartelas."""
        docs = self.master_ref.order_by('number').get()
        return [{'id': doc.id, **doc.to_dict()} for doc in docs]

    async def get_cartela(self, number: int) -> Optional[dict]:
        """Get a single cartela by number."""
        doc = self.master_ref.document(str(number)).get()
        if doc.exists:
            return {'id': doc.id, **doc.to_dict()}
        return None

    # ═══════════════════════════════════════════════════════════════
    # Round Lifecycle
    # ═══════════════════════════════════════════════════════════════
    async def get_active_round(self, stake: int = DEFAULT_STAKE) -> Optional[dict]:
        """Find the current active round (selecting or playing) for a given stake."""
        for status in ['selecting', 'playing']:
            docs = list(self.rounds_ref
                       .where('status', '==', status)
                       .where('stake', '==', stake)
                       .order_by('created_at', 'DESCENDING')
                       .limit(1)
                       .get())
            if docs:
                doc = docs[0]
                return {'id': doc.id, **doc.to_dict()}
        return None

    async def create_round(self, stake: int = DEFAULT_STAKE) -> dict:
        """Create a new round in 'selecting' state."""
        if stake not in VALID_STAKES:
            stake = DEFAULT_STAKE
        # Check for existing active round with same stake
        active = await self.get_active_round(stake=stake)
        if active:
            return active

        now = datetime.now(tz=timezone.utc)
        game_target = self.normalize_game_target()
        round_data = {
            'status': 'selecting',
            'stake': stake,
            'players': {},
            'player_count': 0,
            'taken_cartelas': [],
            'called_numbers': [],
            'winners': [],
            'prize_per_winner': 0,
            'admin_profit': 0,
            'game_target': game_target,
            'selection_deadline': now + timedelta(seconds=SELECTION_DURATION),
            'created_at': now,
            'completed_at': None,
        }
        doc_ref = self.rounds_ref.document()
        doc_ref.set(round_data)
        return {'id': doc_ref.id, **round_data}

    async def join_round(self, round_id: str, user_id: int, 
                         cartela_numbers: List[int], user_name: str) -> dict:
        """Player joins a round with chosen cartelas (max 2)."""
        if len(cartela_numbers) > MAX_CARTELAS_PER_PLAYER:
            return {'error': f'Maximum {MAX_CARTELAS_PER_PLAYER} cartelas allowed'}
        if len(cartela_numbers) == 0:
            return {'error': 'Must select at least 1 cartela'}

        # Validate cartela numbers
        for num in cartela_numbers:
            if num < 1 or num > TOTAL_CARTELAS:
                return {'error': f'Invalid cartela number: {num}'}

        # Check for duplicates in selection
        if len(cartela_numbers) != len(set(cartela_numbers)):
            return {'error': 'Duplicate cartela numbers in selection'}

        round_doc = self.rounds_ref.document(round_id).get()
        if not round_doc.exists:
            return {'error': 'Round not found'}

        round_data = round_doc.to_dict()
        if round_data['status'] != 'selecting':
            return {'error': 'Round is no longer accepting players'}

        # Check if cartelas are already taken
        taken = set(round_data.get('taken_cartelas', []))
        for num in cartela_numbers:
            if num in taken:
                return {'error': f'Cartela #{num} is already taken'}

        # Check if user already joined
        uid_str = str(user_id)
        if uid_str in round_data.get('players', {}):
            return {'error': 'You already joined this round'}

        # Deduct play wallet
        round_stake = round_data.get('stake', DEFAULT_STAKE)
        total_cost = round_stake * len(cartela_numbers)
        user_ref = self.db.collection('users').document(uid_str)
        user_doc = user_ref.get()
        if not user_doc.exists:
            return {'error': 'User not found'}

        user_data = user_doc.to_dict()
        pw = user_data.get('play_wallet', 0)
        if pw < total_cost:
            return {'error': f'Not enough balance. Need {total_cost} ETB, have {pw} ETB'}

        # Deduct and update
        user_ref.update({
            'play_wallet': pw - total_cost,
            'is_playing': True,
            'updated_at': datetime.now(tz=timezone.utc),
        })

        # Second validation check right before update (reduce race condition window)
        round_doc_final = self.rounds_ref.document(round_id).get()
        if round_doc_final.exists:
            round_data_final = round_doc_final.to_dict()
            taken_final = set(round_data_final.get('taken_cartelas', []))
            for num in cartela_numbers:
                if num in taken_final:
                    # Rollback: refund the user
                    user_ref.update({
                        'play_wallet': pw,
                        'is_playing': False,
                        'updated_at': datetime.now(tz=timezone.utc),
                    })
                    return {'error': f'Cartela #{num} was just taken by another player. Please select different cards.'}

        self.rounds_ref.document(round_id).update({
            f'players.{uid_str}': {
                'cartelas': cartela_numbers,
                'name': user_name,
                'joined_at': datetime.now(tz=timezone.utc).isoformat(),
            },
            'player_count': Increment(len(cartela_numbers)),
            'taken_cartelas': ArrayUnion(cartela_numbers),
        })

        return {
            'status': 'joined',
            'cost': total_cost,
            'cartelas': cartela_numbers,
            'player_count': round_data.get('player_count', 0) + len(cartela_numbers),
        }

    async def start_round(self, round_id: str) -> dict:
        """Transition round from 'selecting' to 'playing'."""
        round_doc = self.rounds_ref.document(round_id).get()
        if not round_doc.exists:
            return {'error': 'Round not found'}

        data = round_doc.to_dict()
        if data['status'] != 'selecting':
            return {'error': 'Round already started or completed'}

        player_count = data.get('player_count', 0)
        round_stake = data.get('stake', DEFAULT_STAKE)
        total_pool = player_count * round_stake
        derash = total_pool * 0.75

        now = datetime.now(tz=timezone.utc)
        game_target = self.normalize_game_target(data.get('game_target'))
        self.rounds_ref.document(round_id).update({
            'status': 'playing',
            'game_target': game_target,
            'game_started_at': now,
            'derash': derash,
            'next_number_at': now + timedelta(seconds=NUMBER_CALL_INTERVAL),
        })

        return {'status': 'playing', 'player_count': player_count, 'derash': derash, 'game_target': game_target}

    def normalize_game_target(self, game_target: Optional[int] = None) -> int:
        """Return a random call number between 15-30 where Phase 2
        (targeted winner making) begins. The exact game-end depends
        on how many extra calls Phase 2 needs to complete the target
        pattern (typically 0-2)."""
        min_calls, max_calls = GAME_LENGTH_RANGE
        if game_target is None:
            return random.randint(min_calls, max_calls)
        try:
            target = int(game_target)
        except (TypeError, ValueError):
            return random.randint(min_calls, max_calls)
        return max(min_calls, min(max_calls, target))

    def build_player_cartelas(self, players: Dict[str, dict]) -> Dict[str, List[dict]]:
        """Load all cartelas for active players once so predictor and resolver share the same state."""
        if not _CARTELA_CACHE:
            try:
                docs = self.master_ref.get()
                for doc in docs:
                    _CARTELA_CACHE[doc.id] = doc.to_dict().get('cartela', [])
            except Exception:
                pass

        player_cartelas = {}
        for uid_str, p_info in (players or {}).items():
            player_cartelas[uid_str] = []
            for cnum in p_info.get('cartelas', []):
                ctype = str(cnum)
                flat = _CARTELA_CACHE.get(ctype)
                if flat is None:
                    cdoc = self.master_ref.document(ctype).get()
                    if not cdoc.exists:
                        continue
                    flat = cdoc.to_dict().get('cartela', [])
                    _CARTELA_CACHE[ctype] = flat
                player_cartelas[uid_str].append({
                    'cartela_number': int(cnum),
                    'flat': flat,
                })
        return player_cartelas

    def evaluate_winners(self, player_cartelas: Dict[str, List[dict]], called_numbers: List[int]) -> List[dict]:
        """Return unique player winners and the first winning cartela for each player."""
        winners = []
        for uid_str, cartelas in player_cartelas.items():
            for entry in cartelas:
                if self.check_bingo_for_cartela(entry.get('flat', []), called_numbers):
                    winners.append({
                        'user_id': uid_str,
                        'cartela_number': int(entry.get('cartela_number', 0)),
                    })
                    break
        return winners

    def _winner_sort_key(self, user_id: str, cartela_number: int, players: Dict[str, dict]) -> Tuple[str, int, str]:
        joined_at = (players or {}).get(user_id, {}).get('joined_at') or "9999-12-31T23:59:59"
        return (str(joined_at), int(cartela_number), str(user_id))

    def choose_single_winner(self, winners: List[dict], players: Dict[str, dict]) -> Optional[dict]:
        """Pick exactly one winner deterministically when multiple players hit on the same call."""
        if not winners:
            return None
        return min(
            winners,
            key=lambda item: self._winner_sort_key(
                item.get('user_id', ''),
                item.get('cartela_number', 0),
                players,
            ),
        )

    def _candidate_progress(self, player_cartelas: Dict[str, List[dict]],
                             simulated_called: List[int]) -> int:
        """Return the minimum number of additional calls needed for ANY player
        to complete a winning pattern with these called numbers.
        Lower = closer to a real bingo. 0 means a winner already exists."""
        called_set = set(simulated_called)
        min_missing = 999
        for uid_str, cartelas in player_cartelas.items():
            for entry in cartelas:
                for pattern in self.get_cartela_patterns(entry.get('flat', [])):
                    missing = sum(1 for num in pattern if num not in called_set)
                    if missing == 0:
                        return 0
                    if missing < min_missing:
                        min_missing = missing
        return min_missing

    def _pick_target_winner(self, player_cartelas: Dict[str, List[dict]],
                             called_numbers: List[int],
                             players: Dict[str, dict]) -> Optional[dict]:
        """Pick a player/cartela/pattern to become the designated winner.
        Chooses the pattern closest to completion across all players' cartelas,
        with randomness among equal-distance contenders."""
        called_set = set(called_numbers)
        candidates = []
        for uid_str, cartelas in player_cartelas.items():
            for entry in cartelas:
                flat = entry.get('flat', [])
                for pattern in self.get_cartela_patterns(flat):
                    missing = [n for n in pattern if n not in called_set and n != 0]
                    if not missing:
                        continue
                    candidates.append({
                        'user_id': uid_str,
                        'cartela_number': entry['cartela_number'],
                        'pattern': pattern,
                        'missing': len(missing),
                    })
        if not candidates:
            return None
        min_missing = min(c['missing'] for c in candidates)
        tier = [c for c in candidates if c['missing'] == min_missing]
        return random.choice(tier)

    async def call_number(self, round_id: str) -> Optional[int]:
        """Call the next number for the round.
        Phase 1 (calls 1-15): random safe numbers, avoid any winner.
        Phase 2 (calls 16+): pick a target winner and feed their numbers
        until they complete a winning pattern — guaranteeing a real winner
        between 15-30 calls."""
        round_doc = self.rounds_ref.document(round_id).get()
        if not round_doc.exists:
            return None

        data = round_doc.to_dict()
        if data['status'] != 'playing':
            return None

        called = list(data.get('called_numbers', []))
        available = [n for n in BINGO_NUMBERS if n not in called]
        if not available:
            return None

        num_called = len(called)
        next_call_index = num_called + 1
        min_calls, max_calls = GAME_LENGTH_RANGE
        game_target = self.normalize_game_target(data.get('game_target'))
        players = data.get('players', {})
        player_cartelas = self.build_player_cartelas(players)

        if data.get('game_target') != game_target:
            self.rounds_ref.document(round_id).update({'game_target': game_target})

        number = available[0]

        # ── Phase 1 (1 to game_target-1): random safe, avoid any winner ──
        if next_call_index < game_target:
            random.shuffle(available)
            for candidate in available:
                if len(self.evaluate_winners(player_cartelas, called + [candidate])) == 0:
                    number = candidate
                    break
        else:
            # ── Phase 2 (16-30): target one winner and make them win ──
            existing = self.evaluate_winners(player_cartelas, called)
            if existing:
                number = available[0]
            else:
                target_winner = data.get('target_winner')
                if not target_winner:
                    target_winner = self._pick_target_winner(
                        player_cartelas, called, players,
                    )
                    if target_winner:
                        self.rounds_ref.document(round_id).update({
                            'target_winner': target_winner,
                        })

                best_number = available[0]
                best_score = None

                for candidate in available:
                    simulated = called + [candidate]
                    wc = len(self.evaluate_winners(player_cartelas, simulated))

                    if wc == 1:
                        best_number = candidate
                        break

                    progress = self._candidate_progress(player_cartelas, simulated)
                    is_target = (
                        1 if (target_winner
                              and candidate in target_winner.get('pattern', []))
                        else 0
                    )

                    score = (
                        0 if wc == 0 else 1,
                        -is_target,
                        -progress,
                    )
                    if best_score is None or score < best_score:
                        best_score = score
                        best_number = candidate

                number = best_number

        called.append(number)
        now = datetime.now(tz=timezone.utc)
        self.rounds_ref.document(round_id).update({
            'called_numbers': called,
            'last_called_number': number,
            'last_called_at': now,
            'next_number_at': now + timedelta(seconds=NUMBER_CALL_INTERVAL),
        })
        return number

    def get_cartela_patterns(self, flat_cartela: List[int]) -> List[List[int]]:
        """Return all winning patterns for a cartela as flat number lists."""
        grid = []
        for row in range(5):
            grid.append(flat_cartela[row * 5:(row + 1) * 5])

        patterns = []
        patterns.extend([[num for num in row if num != 0] for row in grid])
        for col in range(5):
            patterns.append([grid[row][col] for row in range(5) if grid[row][col] != 0])
        patterns.append([grid[i][i] for i in range(5) if grid[i][i] != 0])
        patterns.append([grid[i][4 - i] for i in range(5) if grid[i][4 - i] != 0])
        patterns.append([flat_cartela[0], flat_cartela[4], flat_cartela[20], flat_cartela[24]])
        return patterns

    def check_bingo_for_cartela(self, flat_cartela: List[int], 
                                 called_numbers: List[int]) -> bool:
        """Check if a flat 25-int cartela has bingo given called numbers."""
        called_set = set(called_numbers)
        # Reconstruct 5×5 grid
        grid = []
        for row in range(5):
            grid.append(flat_cartela[row * 5:(row + 1) * 5])

        def is_marked(num):
            return num == 0 or num in called_set

        # Check rows
        for row in grid:
            if all(is_marked(n) for n in row):
                return True

        # Check columns
        for col in range(5):
            if all(is_marked(grid[row][col]) for row in range(5)):
                return True

        # Check diagonals
        if all(is_marked(grid[i][i]) for i in range(5)):
            return True
        if all(is_marked(grid[i][4 - i]) for i in range(5)):
            return True

        # Check 4 corners (free space does NOT count for corners)
        corners = [flat_cartela[0], flat_cartela[4], flat_cartela[20], flat_cartela[24]]
        if all(c != 0 and c in called_set for c in corners):
            return True

        return False

    async def check_bingo(self, round_id: str, user_id: int) -> dict:
        """Check if a player has bingo in the current round."""
        round_doc = self.rounds_ref.document(round_id).get()
        if not round_doc.exists:
            return {'bingo': False, 'error': 'Round not found'}

        data = round_doc.to_dict()
        uid_str = str(user_id)
        player_info = data.get('players', {}).get(uid_str)
        if not player_info:
            return {'bingo': False, 'error': 'Player not in round'}

        called = data.get('called_numbers', [])
        winning_cartelas = []

        for cartela_num in player_info.get('cartelas', []):
            cartela_doc = self.master_ref.document(str(cartela_num)).get()
            if not cartela_doc.exists:
                continue
            flat = cartela_doc.to_dict().get('cartela', [])
            if self.check_bingo_for_cartela(flat, called):
                winning_cartelas.append(cartela_num)

        return {'bingo': len(winning_cartelas) > 0, 'winning_cartelas': winning_cartelas}

    async def end_round(self, round_id: str, winner_ids: List[int]) -> dict:
        """End the round, distribute prizes."""
        round_doc = self.rounds_ref.document(round_id).get()
        if not round_doc.exists:
            return {'error': 'Round not found'}

        data = round_doc.to_dict()
        if data['status'] not in ('playing', 'completed'):
            return {'error': 'Round not in a valid state for ending'}

        player_count = data.get('player_count', 0)
        round_stake = data.get('stake', DEFAULT_STAKE)
        total_pool = player_count * round_stake
        derash = total_pool * 0.75
        admin_profit = total_pool * 0.25

        prize_per_winner = 0
        if winner_ids:
            prize_per_winner = derash / len(winner_ids)
            # Credit each winner
            for wid in winner_ids:
                user_ref = self.db.collection('users').document(str(wid))
                user_doc = user_ref.get()
                if user_doc.exists:
                    ud = user_doc.to_dict()
                    user_ref.update({
                        'play_wallet': ud.get('play_wallet', 0) + prize_per_winner,
                        'wins': ud.get('wins', 0) + 1,
                        'is_playing': False,
                        'updated_at': datetime.now(tz=timezone.utc),
                    })

        # Mark all players as not playing
        for uid_str in data.get('players', {}):
            try:
                uid_int = int(uid_str)
            except ValueError:
                continue
            if uid_int not in winner_ids:
                user_ref = self.db.collection('users').document(uid_str)
                user_doc = user_ref.get()
                if user_doc.exists:
                    ud = user_doc.to_dict()
                    user_ref.update({
                        'losses': ud.get('losses', 0) + 1,
                        'is_playing': False,
                        'updated_at': datetime.now(tz=timezone.utc),
                    })

        # Get winner names for spectator display
        winner_names = []
        for wid in winner_ids:
            user_ref = self.db.collection('users').document(str(wid))
            user_doc = user_ref.get()
            if user_doc.exists:
                winner_names.append(user_doc.to_dict().get('first_name', 'Unknown'))
            else:
                winner_names.append('Unknown')

        # Update round
        self.rounds_ref.document(round_id).update({
            'status': 'completed',
            'winners': [str(w) for w in winner_ids],
            'winner_name': winner_names[0] if len(winner_names) == 1 else ', '.join(winner_names),
            'prize_per_winner': prize_per_winner,
            'admin_profit': admin_profit,
            'completed_at': datetime.now(tz=timezone.utc),
        })

        return {
            'status': 'completed',
            'winners': winner_ids,
            'prize_per_winner': prize_per_winner,
            'admin_profit': admin_profit,
        }

    async def get_round(self, round_id: str) -> Optional[dict]:
        """Get round data by ID."""
        doc = self.rounds_ref.document(round_id).get()
        if doc.exists:
            return {'id': doc.id, **doc.to_dict()}
        return None

    async def get_recent_rounds(self, limit: int = 20) -> List[dict]:
        """Get recent rounds."""
        docs = (self.rounds_ref
                .order_by('created_at', direction='DESCENDING')
                .limit(limit)
                .get())
        return [{'id': doc.id, **doc.to_dict()} for doc in docs]

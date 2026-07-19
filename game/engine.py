import random
from datetime import datetime, timezone
from firestore_db import FieldFilter, transactional as firestore_transactional

TOTAL_CARTELAS = 500


class GameEngine:
    def __init__(self, db):
        self.db = db
        self.games_ref = db.collection('games')
        self.cartelas_ref = db.collection('cartelas')
        self.master_ref = db.collection('cartelas_master')

    def _generate_single_cartela(self, seed: int):
        """Generate a deterministic 5x5 bingo card as flat 25-int list."""
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
            flat.append(0 if row_idx == 2 else cols['N'][row_idx])
            flat.append(cols['G'][row_idx])
            flat.append(cols['O'][row_idx])
        return flat

    async def generate_all_cartelas(self) -> dict:
        """Generate 500 fixed cartelas in cartelas_master. Idempotent."""
        existing = list(self.master_ref.limit(1).get())
        if existing:
            count = len(list(self.master_ref.get()))
            return {'status': 'already_exists', 'count': count}

        batch_size = 100
        generated = 0
        for start in range(1, TOTAL_CARTELAS + 1, batch_size):
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

        return {'status': 'generated', 'count': generated}

    def get_stats(self):
        """Get game statistics (synchronous)"""
        try:
            active_players = len(list(self.db.collection('users').where('is_playing', '==', True).get()))
            games = self.db.collection('games').get()
            games_played = len(list(games))

            today = datetime.now(tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            winners_today = len(list(self.db.collection('games').where('winner', '!=', None).where('created_at', '>=', today).get()))

            return {
                'active_players': active_players,
                'games_played': games_played,
                'winners_today': winners_today
            }
        except Exception as e:
            return {'active_players': 0, 'games_played': 0, 'winners_today': 0}

    async def create_game(self, user_id, stake):
        """Create a new game session"""
        game_data = {
            'user_id': user_id,
            'stake': stake,
            'status': 'waiting',
            'called_numbers': [],
            'marked_numbers': [],
            'winner': None,
            'prize': 0,
            'created_at': datetime.now(tz=timezone.utc),
            'updated_at': datetime.now(tz=timezone.utc)
        }

        doc_ref = self.games_ref.document()
        doc_ref.set(game_data)
        return {'id': doc_ref.id, **game_data}

    async def generate_cartela(self):
        """Generate a random Bingo cartela (5x5 card) - standard ranges"""
        columns = {
            'B': random.sample(range(1, 16), 5),
            'I': random.sample(range(16, 31), 5),
            'N': random.sample(range(31, 46), 5),
            'G': random.sample(range(46, 61), 5),
            'O': random.sample(range(61, 76), 5)
        }

        cartela = []
        for i in range(5):
            row = [
                columns['B'][i],
                columns['I'][i],
                columns['N'][i] if i != 2 else 0,
                columns['G'][i],
                columns['O'][i]
            ]
            cartela.append(row)

        return cartela

    async def save_cartela(self, game_id, user_id, cartela):
        """Save cartela to database"""
        flat = []
        for row in cartela:
            for num in row:
                flat.append(num)

        cartela_data = {
            'game_id': game_id,
            'user_id': user_id,
            'cartela': flat,
            'marked': [],
            'created_at': datetime.now(tz=timezone.utc)
        }

        doc_ref = self.cartelas_ref.document()
        doc_ref.set(cartela_data)
        return {'id': doc_ref.id, **cartela_data}

    async def call_number(self, game_id):
        """Call a random number for the game"""
        game_doc = self.games_ref.document(game_id).get()
        game = game_doc.to_dict()

        called = game.get('called_numbers', [])
        available = [n for n in range(1, 76) if n not in called]

        if not available:
            return None

        number = random.choice(available)
        called.append(number)

        self.games_ref.document(game_id).update({
            'called_numbers': called,
            'updated_at': datetime.now(tz=timezone.utc)
        })

        return number

    async def mark_number(self, game_id, user_id, number):
        """Mark a number on player's cartela using transaction"""
        cartelas = self.cartelas_ref.where('game_id', '==', game_id).where('user_id', '==', user_id).get()

        for cartela_doc in cartelas:
            @firestore_transactional
            def update_in_transaction(transaction, doc_ref):
                snapshot = doc_ref.get(transaction=transaction)
                marked = snapshot.to_dict().get('marked', [])
                if number not in marked:
                    marked.append(number)
                    transaction.update(doc_ref, {'marked': marked})

            transaction = self.db.transaction()
            update_in_transaction(transaction, self.cartelas_ref.document(cartela_doc.id))

        return True

    async def check_bingo(self, game_id, user_id):
        """Check if player has Bingo"""
        cartelas = self.cartelas_ref.where('game_id', '==', game_id).where('user_id', '==', user_id).get()

        for cartela_doc in cartelas:
            flat = cartela_doc.to_dict().get('cartela', [])
            marked = set(cartela_doc.to_dict().get('marked', []))

            cartela = []
            for row in range(5):
                cartela.append(flat[row*5:(row+1)*5])

            for row in cartela:
                if all((n in marked or n == 0) for n in row):
                    return True

            for col in range(5):
                if all((row[col] in marked or row[col] == 0) for row in cartela):
                    return True

            if all((cartela[i][i] in marked or cartela[i][i] == 0) for i in range(5)):
                return True
            if all((cartela[i][4-i] in marked or cartela[i][4-i] == 0) for i in range(5)):
                return True

        return False

    async def end_game(self, game_id, winner_id=None):
        """End game and distribute prize"""
        game_doc = self.games_ref.document(game_id).get()
        game = game_doc.to_dict()

        prize = game['stake'] * 1.5 if winner_id else 0

        self.games_ref.document(game_id).update({
            'status': 'completed',
            'winner': winner_id,
            'prize': prize,
            'updated_at': datetime.now(tz=timezone.utc)
        })

        return prize

    def format_game_board(self, cartela, called_numbers, stake, play_wallet):
        """Format the game board for display"""
        header = f"🎯 *Yegara Bingo*\n"
        header += f"💰 Stake: {stake} ETB | Play Wallet: {play_wallet} ETB\n"
        header += f"⏰ Timer: 35s\n\n"

        board = "```"
        board += "  B    I    N    G    O\n"
        board += "┌────┬────┬────┬────┬────┐\n"

        for row in cartela:
            board += "│"
            for num in row:
                if num == 0:
                    board += "  ★  │"
                elif num in called_numbers:
                    board += f" [{num:2d}]│"
                else:
                    board += f"  {num:2d} │"
            board += "\n"
            board += "├────┼────┼────┼────┼────┤\n"

        board = board[:-27] + "└────┴────┴────┴────┴────┘"
        board += "```"

        return header + board

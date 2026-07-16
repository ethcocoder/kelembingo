from firebase_admin import firestore
from datetime import datetime
from typing import Dict, Optional


class UserManager:
    def __init__(self, db):
        self.db = db
        self.users_ref = db.collection('users')

    async def get_or_create_user(self, user_id: int, first_name: str, username: str) -> Dict:
        user_doc = self.users_ref.document(str(user_id)).get()
        if user_doc.exists:
            return user_doc.to_dict()
        user_data = {
            'user_id': user_id,
            'first_name': first_name,
            'username': username or '',
            'balance': 0,
            'play_wallet': 0,
            'bonus': 0,
            'phone': '',
            'registered': False,
            'total_games': 0,
            'wins': 0,
            'losses': 0,
            'is_playing': False,
            'awaiting_screenshot': False,
            'referred_by': None,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
        }
        self.users_ref.document(str(user_id)).set(user_data)
        return user_data

    async def get_user(self, user_id: int) -> Optional[Dict]:
        user_doc = self.users_ref.document(str(user_id)).get()
        return user_doc.to_dict() if user_doc.exists else None

    async def update_balance(self, user_id: int, amount: float) -> bool:
        user = await self.get_user(user_id)
        if not user:
            return False
        new_balance = user.get('balance', 0) + amount
        if new_balance < 0:
            return False
        self.users_ref.document(str(user_id)).update({
            'balance': new_balance,
            'updated_at': datetime.utcnow(),
        })
        return True

    async def deduct_balance(self, user_id: int, amount: float) -> bool:
        user = await self.get_user(user_id)
        if not user or user.get('balance', 0) < amount:
            return False
        self.users_ref.document(str(user_id)).update({
            'balance': user['balance'] - amount,
            'updated_at': datetime.utcnow(),
        })
        return True

    async def transfer_to_play_wallet(self, user_id: int, amount: float) -> bool:
        user = await self.get_user(user_id)
        if not user or user.get('balance', 0) < amount:
            return False
        self.users_ref.document(str(user_id)).update({
            'balance': user['balance'] - amount,
            'play_wallet': user.get('play_wallet', 0) + amount,
            'updated_at': datetime.utcnow(),
        })
        return True

    async def add_winnings(self, user_id: int, amount: float) -> bool:
        user = await self.get_user(user_id)
        if not user:
            return False
        self.users_ref.document(str(user_id)).update({
            'play_wallet': user.get('play_wallet', 0) + amount,
            'wins': user.get('wins', 0) + 1,
            'updated_at': datetime.utcnow(),
        })
        return True

    async def update_game_stats(self, user_id: int, won: bool) -> bool:
        user = await self.get_user(user_id)
        if not user:
            return False
        update_data = {
            'total_games': user.get('total_games', 0) + 1,
            'updated_at': datetime.utcnow(),
        }
        if won:
            update_data['wins'] = user.get('wins', 0) + 1
        else:
            update_data['losses'] = user.get('losses', 0) + 1
        self.users_ref.document(str(user_id)).update(update_data)
        return True

    async def set_playing_status(self, user_id: int, is_playing: bool) -> bool:
        self.users_ref.document(str(user_id)).update({
            'is_playing': is_playing,
            'updated_at': datetime.utcnow(),
        })
        return True

    async def get_user_history(self, user_id: int, limit: int = 10) -> list:
        games = self.db.collection('games').where('user_id', '==', user_id).order_by('created_at', direction=firestore.Query.DESCENDING).limit(limit).get()
        return [game.to_dict() for game in games]

    async def get_all_users(self, limit: int = 100) -> list:
        users = self.users_ref.limit(limit).get()
        return [user.to_dict() for user in users]

    async def get_leaderboard(self, limit: int = 10) -> list:
        users = self.users_ref.order_by('wins', direction=firestore.Query.DESCENDING).limit(limit).get()
        return [user.to_dict() for user in users]

    async def register_user(self, user_id: int, name: str, phone: str, telebirr_name: str = '') -> bool:
        user = await self.get_user(user_id)
        if not user:
            return False
        self.users_ref.document(str(user_id)).update({
            'first_name': name,
            'phone': phone,
            'telebirr_name': telebirr_name,
            'registered': True,
            'updated_at': datetime.utcnow(),
        })
        return True

    async def is_registered(self, user_id: int) -> bool:
        user = await self.get_user(user_id)
        if not user:
            return False
        return bool(user.get('registered')) and bool(user.get('phone')) and bool(user.get('telebirr_name'))

    async def get_balance_info(self, user_id: int) -> Optional[Dict]:
        user = await self.get_user(user_id)
        if not user:
            return None
        return {
            'balance': user.get('balance', 0),
            'play_wallet': user.get('play_wallet', 0),
            'bonus': user.get('bonus', 0),
            'first_name': user.get('first_name', ''),
        }

    async def transfer_funds(self, sender_id: int, recipient_id: int, amount: float) -> bool:
        if sender_id == recipient_id:
            return False
        sender_ref = self.users_ref.document(str(sender_id))
        recipient_ref = self.users_ref.document(str(recipient_id))
        transaction = self.db.transaction()

        @firestore.transactional
        def _transfer(txn):
            sender_snap = sender_ref.get(transaction=txn)
            recipient_snap = recipient_ref.get(transaction=txn)
            if not sender_snap.exists or not recipient_snap.exists:
                return False
            sender_data = sender_snap.to_dict()
            if sender_data.get('balance', 0) < amount:
                return False
            txn.update(sender_ref, {
                'balance': sender_data['balance'] - amount,
                'updated_at': datetime.utcnow(),
            })
            recipient_data = recipient_snap.to_dict()
            txn.update(recipient_ref, {
                'balance': recipient_data.get('balance', 0) + amount,
                'updated_at': datetime.utcnow(),
            })
            return True

        return _transfer(transaction)

    async def convert_bonus(self, user_id: int, rate: int = 10) -> Optional[float]:
        user = await self.get_user(user_id)
        if not user:
            return None
        coins = user.get('bonus', 0)
        if coins <= 0:
            return None
        etb = coins / rate
        self.users_ref.document(str(user_id)).update({
            'bonus': 0,
            'play_wallet': user.get('play_wallet', 0) + etb,
            'updated_at': datetime.utcnow(),
        })
        return etb

    async def add_referral_bonus(self, referrer_id: int, bonus_amount: float) -> bool:
        user = await self.get_user(referrer_id)
        if not user:
            return False
        self.users_ref.document(str(referrer_id)).update({
            'balance': user.get('balance', 0) + bonus_amount,
            'updated_at': datetime.utcnow(),
        })
        return True

    async def set_referred_by(self, new_user_id: int, referrer_id: int) -> bool:
        self.users_ref.document(str(new_user_id)).update({
            'referred_by': referrer_id,
            'updated_at': datetime.utcnow(),
        })
        return True

    async def set_awaiting_screenshot(self, user_id: int, awaiting: bool) -> None:
        self.users_ref.document(str(user_id)).update({
            'awaiting_screenshot': awaiting,
            'updated_at': datetime.utcnow(),
        })

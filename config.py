import os
import logging
from dotenv import load_dotenv
import sys
import types
import firestore_db

load_dotenv()
logger = logging.getLogger(__name__)

# Create in-memory mock modules to satisfy existing bot code imports
firebase_admin_mock = types.ModuleType("firebase_admin")
firebase_admin_mock._apps = [True]
firebase_admin_mock.initialize_app = lambda *args, **kwargs: None

class MockCredentialsCertificate:
    def __init__(self, *args, **kwargs):
        pass

credentials_mock = types.ModuleType("firebase_admin.credentials")
credentials_mock.Certificate = MockCredentialsCertificate

firestore_mock = types.ModuleType("firebase_admin.firestore")
firestore_mock.Increment = firestore_db.Increment
firestore_mock.ArrayUnion = firestore_db.ArrayUnion
firestore_mock.FieldFilter = firestore_db.FieldFilter
firestore_mock.transactional = firestore_db.transactional

sys.modules["firebase_admin"] = firebase_admin_mock
sys.modules["firebase_admin.credentials"] = credentials_mock
sys.modules["firebase_admin.firestore"] = firestore_mock

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")

db = firestore_db.MockFirestoreClient()
logger.info("SQL database emulator initialized successfully")


DEFAULT_STAKE_10 = int(os.getenv("DEFAULT_STAKE_10", 10))
DEFAULT_STAKE_20 = int(os.getenv("DEFAULT_STAKE_20", 20))
GAME_TIMER_SECONDS = int(os.getenv("GAME_TIMER_SECONDS", 35))
MAX_PLAYERS_PER_GAME = int(os.getenv("MAX_PLAYERS_PER_GAME", 500))
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "yegarasupport")
REFERRAL_BONUS = int(os.getenv("REFERRAL_BONUS", 10))
BONUS_TO_ETB_RATE = int(os.getenv("BONUS_TO_ETB_RATE", 10))
MIN_WITHDRAW = int(os.getenv("MIN_WITHDRAW", 10))
TELEBIRR_NUMBER = os.getenv("TELEBIRR_NUMBER", "+251911000000")

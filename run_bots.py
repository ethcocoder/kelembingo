import os
import logging
import multiprocessing
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_game_bot():
    try:
        from bot import main
        main()
    except Exception as e:
        logger.error(f"Game bot error: {e}", exc_info=True)


def run_admin_bot():
    try:
        from admin_bot import main
        main()
    except Exception as e:
        logger.error(f"Admin bot error: {e}", exc_info=True)


def run_api():
    try:
        import uvicorn
        from api.admin_api import socket_app as app
        port = int(os.environ.get("PORT", 8000))
        uvicorn.run(app, host="0.0.0.0", port=port)
    except Exception as e:
        logger.error(f"API error: {e}", exc_info=True)


if __name__ == "__main__":
    try:
        multiprocessing.set_start_method("spawn")
    except RuntimeError:
        pass

    logger.info("🚀 Starting Kelem Bingo Platform...")

    game_proc = multiprocessing.Process(target=run_game_bot, name="GameBot")
    admin_proc = multiprocessing.Process(target=run_admin_bot, name="AdminBot")

    game_proc.start()
    logger.info("✅ Game Bot started")
    admin_proc.start()
    logger.info("✅ Admin Bot started")
    logger.info("✅ API Server starting...")
    logger.info("🎯 All services running!")

    try:
        run_api()
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down...")
    finally:
        for proc in (game_proc, admin_proc):
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=5)

import threading
import logging
import time
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_game_bot():
    """Run the main game bot"""
    try:
        from bot import main
        import asyncio
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Game bot error: {e}")

def run_payment_bot():
    """Run the payment processing bot"""
    try:
        from payment_bot import main
        main()
    except Exception as e:
        logger.error(f"Payment bot error: {e}")

def run_admin_bot():
    """Run the admin notification bot"""
    try:
        from admin_bot import main
        main()
    except Exception as e:
        logger.error(f"Admin bot error: {e}")

def run_api():
    """Run the FastAPI server"""
    try:
        import uvicorn
        from api.admin_api import app
        uvicorn.run(app, host="0.0.0.0", port=8000)
    except Exception as e:
        logger.error(f"API error: {e}")

if __name__ == "__main__":
    logger.info("🚀 Starting Yegara Bingo Platform - All Services...")

    # Start all services in separate threads
    threads = []

    services = [
        ("Game Bot", run_game_bot),
        ("Payment Bot", run_payment_bot),
        ("Admin Bot", run_admin_bot),
        ("API Server", run_api),
    ]

    for name, target in services:
        t = threading.Thread(target=target, daemon=True, name=name)
        t.start()
        threads.append(t)
        logger.info(f"✅ {name} started")
        time.sleep(0.5)

    logger.info("🎯 All services running! Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down...")

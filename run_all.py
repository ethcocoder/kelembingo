import threading
import asyncio
import uvicorn
from api.admin_api import socket_app as api_app
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_bot():
    """Run Telegram bot in separate thread"""
    from bot import main
    asyncio.run(main())

def run_api():
    """Run FastAPI server"""
    uvicorn.run(api_app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    logger.info("🚀 Starting Kelem Bingo Bot + API...")
    
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    logger.info("✅ Bot started")
    
    run_api()

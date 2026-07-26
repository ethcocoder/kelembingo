"""
Gateway service entry point — API + backup scheduler.

This is the "source of truth" service. It runs:
  • FastAPI REST API (all CRUD endpoints)
  • Socket.IO (real-time client updates)
  • Backup scheduler (periodic dumps to @kelembackupbot)
  • Background round monitor (creates new rounds)

No Telegram bots run here. Bot services and game engine services
connect to this gateway via HTTP (gateway_client.py).
"""

import os
import logging
import threading
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_backup_scheduler():
    """Periodically snapshot the DB to the backup bot."""
    import firestore_db
    import backup_common as bc

    interval = max(1, int(os.getenv("BACKUP_INTERVAL_MINUTES", "1"))) * 60
    if not bc.BACKUP_CHAT_ID:
        logger.warning("BACKUP_CHAT_ID not set — automatic backups disabled.")
        return

    # Initial delay to let the DB initialize
    time.sleep(5)
    while True:
        try:
            if firestore_db.count_documents() > 0:
                meta = bc.create_backup()
                logger.info(f"Auto-backup: {meta.get('documents')} records saved.")
            else:
                logger.info("Auto-backup skipped: no documents.")
        except Exception as e:
            logger.warning(f"Auto-backup failed: {e}")
        time.sleep(interval)


def auto_restore_on_startup():
    """Re-seed the DB from the latest backup when it comes up empty."""
    try:
        import backup_common as bc
        result = bc.restore_if_empty()
        if result.get("restored"):
            logger.info(f"♻️ Restored data from backup: {result}")
    except Exception as e:
        logger.warning(f"Startup restore skipped: {e}")


if __name__ == "__main__":
    logger.info("🚀 Starting Kelem Bingo Gateway...")
    auto_restore_on_startup()

    # Start backup scheduler in background thread
    t = threading.Thread(target=run_backup_scheduler, daemon=True)
    t.start()
    logger.info("✅ Backup Scheduler started")

    # Run the API server (blocking)
    import uvicorn
    from api.admin_api import socket_app as app
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"✅ API Server starting on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)

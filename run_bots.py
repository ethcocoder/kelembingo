import os
import logging
import multiprocessing
import threading
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


def run_support_bot():
    try:
        from support_bot import main
        main()
    except Exception as e:
        logger.error(f"Support bot error: {e}", exc_info=True)


def run_admin_support_bot():
    try:
        from admin_support_bot import main
        main()
    except Exception as e:
        logger.error(f"Admin support bot error: {e}", exc_info=True)


def run_api():
    try:
        import uvicorn
        from api.admin_api import socket_app as app
        port = int(os.environ.get("PORT", 8000))
        uvicorn.run(app, host="0.0.0.0", port=port)
    except Exception as e:
        logger.error(f"API error: {e}", exc_info=True)


def run_backup_scheduler():
    """Periodically snapshot the DB to the backup bot so data survives deploys."""
    import time
    try:
        import backup_common as bc
        import firestore_db
    except Exception as e:
        logger.error(f"Backup scheduler import error: {e}", exc_info=True)
        return

    interval = max(1, int(os.getenv("BACKUP_INTERVAL_MINUTES", "1"))) * 60
    if not bc.BACKUP_CHAT_ID:
        logger.warning("ADMIN_CHAT_ID not set — automatic backups are disabled.")
        return

    # Small delay to let DB initialize, then create an immediate backup
    time.sleep(5)
    while True:
        try:
            if firestore_db.count_documents() > 0:
                meta = bc.create_backup()
                logger.info(f"Auto-backup: {meta.get('documents')} records saved.")
            else:
                logger.info("Auto-backup skipped: no documents to back up.")
        except Exception as e:
            logger.warning(f"Auto-backup failed (will retry next cycle): {e}")
        time.sleep(interval)


def auto_restore_on_startup():
    """Re-seed the DB from the latest backup when it comes up empty (fresh deploy)."""
    try:
        import backup_common as bc
        result = bc.restore_if_empty()
        if result.get("restored"):
            logger.info(f"♻️ Restored data from backup: {result}")
        else:
            logger.info(f"Startup restore skipped: {result.get('reason')}")
    except Exception as e:
        logger.warning(f"Startup restore error (continuing with empty DB): {e}")


def run_health_server():
    """Minimal HTTP server for Render health checks (no full API)."""
    import uvicorn
    from fastapi import FastAPI, Response
    health_app = FastAPI()

    @health_app.get("/api/health")
    async def health():
        return Response(status_code=200, content='{"status":"ok"}', media_type="application/json")

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(health_app, host="0.0.0.0", port=port, log_level="warning")


if __name__ == "__main__":
    try:
        multiprocessing.set_start_method("spawn")
    except RuntimeError:
        pass

    is_gateway_mode = bool(os.getenv("USE_GATEWAY"))

    if is_gateway_mode:
        logger.info("🚀 Starting Kelem Bingo Bots (Gateway mode)...")
    else:
        logger.info("🚀 Starting Kelem Bingo Platform...")
        auto_restore_on_startup()

    game_proc = multiprocessing.Process(target=run_game_bot, name="GameBot")
    admin_proc = multiprocessing.Process(target=run_admin_bot, name="AdminBot")
    support_proc = multiprocessing.Process(target=run_support_bot, name="SupportBot")
    admin_support_proc = multiprocessing.Process(target=run_admin_support_bot, name="AdminSupportBot")

    game_proc.start()
    logger.info("✅ Game Bot started")
    admin_proc.start()
    logger.info("✅ Admin Bot started")
    support_proc.start()
    logger.info("✅ Support Bot started")
    admin_support_proc.start()
    logger.info("✅ Admin Support Bot started")

    if not is_gateway_mode:
        backup_proc = multiprocessing.Process(target=run_backup_scheduler, name="BackupScheduler")
        backup_proc.start()
        logger.info("✅ Backup Scheduler started")
        logger.info("✅ API Server starting...")
        logger.info("🎯 All services running!")
        try:
            run_api()
        except KeyboardInterrupt:
            logger.info("🛑 Shutting down...")
        finally:
            procs = [game_proc, admin_proc, support_proc, admin_support_proc, backup_proc]
            for proc in procs:
                if proc.is_alive():
                    proc.terminate()
                    proc.join(timeout=5)
    else:
        logger.info("🎯 Bot service running (no API, no backup — those are on the Gateway)!")
        # Start minimal health check server for Render
        health_thread = threading.Thread(target=run_health_server, daemon=True)
        health_thread.start()
        logger.info("✅ Health check server started")

        # Keep the main process alive waiting for bot subprocesses
        try:
            procs = [game_proc, admin_proc, support_proc, admin_support_proc]
            while any(p.is_alive() for p in procs):
                for p in procs:
                    p.join(timeout=1)
        except KeyboardInterrupt:
            logger.info("🛑 Shutting down...")
            for proc in procs:
                if proc.is_alive():
                    proc.terminate()
                    proc.join(timeout=5)

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
    except Exception as e:
        logger.error(f"Backup scheduler import error: {e}", exc_info=True)
        return

    interval = max(1, int(os.getenv("BACKUP_INTERVAL_MINUTES", "15"))) * 60
    if not bc.BACKUP_CHAT_ID:
        logger.warning("ADMIN_CHAT_ID not set — automatic backups are disabled.")
        return

    while True:
        time.sleep(interval)
        try:
            meta = bc.create_backup()
            logger.info(f"⏱️ Auto-backup: {meta.get('documents')} records saved.")
        except Exception as e:
            logger.warning(f"Auto-backup failed (will retry next cycle): {e}")


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


if __name__ == "__main__":
    try:
        multiprocessing.set_start_method("spawn")
    except RuntimeError:
        pass

    logger.info("🚀 Starting Kelem Bingo Platform...")

    # Re-seed from the latest backup if this deploy came up with an empty DB.
    auto_restore_on_startup()

    game_proc = multiprocessing.Process(target=run_game_bot, name="GameBot")
    admin_proc = multiprocessing.Process(target=run_admin_bot, name="AdminBot")
    support_proc = multiprocessing.Process(target=run_support_bot, name="SupportBot")
    admin_support_proc = multiprocessing.Process(target=run_admin_support_bot, name="AdminSupportBot")
    backup_proc = multiprocessing.Process(target=run_backup_scheduler, name="BackupScheduler")

    game_proc.start()
    logger.info("✅ Game Bot started")
    admin_proc.start()
    logger.info("✅ Admin Bot started")
    support_proc.start()
    logger.info("✅ Support Bot started")
    admin_support_proc.start()
    logger.info("✅ Admin Support Bot started")
    backup_proc.start()
    logger.info("✅ Backup Scheduler started")
    logger.info("✅ API Server starting...")
    logger.info("🎯 All services running!")

    try:
        run_api()
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down...")
    finally:
        for proc in (game_proc, admin_proc, support_proc, admin_support_proc, backup_proc):
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=5)

import asyncio
import logging
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Import functions and dispatcher from the respective modules
from bot import start_bot_polling, register_bot_jobs, TZ
from scraper import scrape_one_page_for_today # Import the scraping function

# -----------------------------
# CONFIG
# -----------------------------
SCRAPE_TIME_HOUR = 10 # IST hour for scraping (e.g., 4:00 PM IST)
SCRAPE_TIME_MINUTE = 52 # IST minute for scraping (e.g., 4:02 PM IST)

# -----------------------------
# Logging Setup
# -----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("main")

# -----------------------------
# Scheduler Setup
# -----------------------------
scheduler = AsyncIOScheduler(timezone=pytz.timezone(TZ))

def register_all_jobs():
    """Registers jobs from both bot.py and scraper.py."""
    
    # Register Scraper Job
    # Scrape one new page daily at the specified time
    scheduler.add_job(
        scrape_one_page_for_today, 
        "cron", 
        hour=SCRAPE_TIME_HOUR, 
        minute=SCRAPE_TIME_MINUTE, 
        timezone=TZ
    )
    logger.info(f"Main: Scraper job scheduled for daily at {SCRAPE_TIME_HOUR:02d}:{SCRAPE_TIME_MINUTE:02d} {TZ}")

    # Register Bot Jobs
    register_bot_jobs(scheduler)
    
    logger.info("Main: All jobs registered.")


# -----------------------------
# MAIN EXECUTION
# -----------------------------
async def main():
    logger.info("Main: Starting application (Bot & Scheduler)...")
    
    # 1. Register all scheduled tasks (Bot Posting & Scraper)
    register_all_jobs()
    
    # 2. Start the APScheduler
    scheduler.start()
    logger.info("Main: Scheduler started.")
    
    # 3. Start the Telegram Bot polling (this is a blocking call until stopped)
    try:
        await start_bot_polling()
    finally:
        # Stop the scheduler when the bot polling stops (e.g., on KeyboardInterrupt)
        if scheduler.running:
            scheduler.shutdown()
            logger.info("Main: Scheduler shut down.")
        
    logger.info("Main: Application finished.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Main: Application shutting down due to KeyboardInterrupt...")
    except Exception as e:
        logger.error(f"Main: Fatal error during execution: {e}")

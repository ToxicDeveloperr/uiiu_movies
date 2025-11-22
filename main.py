#!/usr/bin/env python3
"""
Main runner script to run both scraper and bot together
"""
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
import sys

# Import main functions from both scripts
from scraper import run_daily_scheduler as run_scraper
from bot import main as run_bot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)


def start_scraper():
    """Run scraper in separate thread"""
    try:
        logger.info("🔥 Starting Scraper...")
        asyncio.run(run_scraper())
    except Exception as e:
        logger.error(f"Scraper crashed: {e}")
        sys.exit(1)


async def start_bot():
    """Run bot in main async loop"""
    try:
        logger.info("🤖 Starting Bot...")
        await run_bot()
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        sys.exit(1)


async def main():
    """Run both services concurrently"""
    logger.info("🚀 Starting Movie Scraper Bot System...")
    
    # Create thread pool for scraper
    executor = ThreadPoolExecutor(max_workers=1)
    loop = asyncio.get_event_loop()
    
    # Run scraper in thread and bot in async
    scraper_task = loop.run_in_executor(executor, start_scraper)
    bot_task = asyncio.create_task(start_bot())
    
    # Wait for both to complete (they won't unless error occurs)
    await asyncio.gather(scraper_task, bot_task)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⛔ Shutting down gracefully...")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)

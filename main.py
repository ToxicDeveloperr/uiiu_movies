#!/usr/bin/env python3
"""
Main runner script to run both scraper and bot together
With HTTP health check server for Koyeb
"""
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
import sys
from aiohttp import web

# Import main functions from both scripts
from scraper import run_daily_scheduler as run_scraper
from bot import main as run_bot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)


# ------------------------------------------------
# HEALTH CHECK SERVER (For Koyeb)
# ------------------------------------------------
async def health_check(request):
    """Simple health check endpoint"""
    return web.Response(text="OK", status=200)


async def start_health_server():
    """Start HTTP server for health checks"""
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Koyeb checks port 8080
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    
    logger.info("✅ Health check server started on port 8080")
    
    # Keep server running
    await asyncio.Event().wait()


# ------------------------------------------------
# MAIN SERVICES
# ------------------------------------------------
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
    """Run all services concurrently"""
    logger.info("🚀 Starting Movie Scraper Bot System...")
    
    # Create thread pool for scraper
    executor = ThreadPoolExecutor(max_workers=1)
    loop = asyncio.get_event_loop()
    
    # Run all services
    scraper_task = loop.run_in_executor(executor, start_scraper)
    bot_task = asyncio.create_task(start_bot())
    health_task = asyncio.create_task(start_health_server())
    
    # Wait for all to complete (they won't unless error occurs)
    await asyncio.gather(scraper_task, bot_task, health_task)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⛔ Shutting down gracefully...")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)

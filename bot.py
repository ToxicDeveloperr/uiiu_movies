import os
import asyncio
import logging
from datetime import datetime
from typing import Dict, List

import aiohttp
from aiohttp import ClientTimeout
from aiogram.types import BufferedInputFile
from aiogram.exceptions import TelegramRetryAfter
from aiogram.client.session.aiohttp import AiohttpSession
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.types import Message
from aiogram.filters import Command
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# -----------------------------
# CONFIG
# -----------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1002063549539"))

DB_NAME = "uiiu_scraper"
COL_DATA = "scraped_data"
COL_META = "meta_data"

TZ = "Asia/Kolkata"
RETRY_DELAY = 5
POST_DELAY = 3

# -----------------------------
# Logging
# -----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | BOT | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# -----------------------------
# Validate Environment Variables
# -----------------------------
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN not found in environment variables!")
    raise ValueError("BOT_TOKEN is required")

if not MONGO_URI:
    logger.error("❌ MONGO_URI not found in environment variables!")
    raise ValueError("MONGO_URI is required")

# -----------------------------
# MongoDB Setup
# -----------------------------
try:
    mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    mongo.admin.command('ping')
    db = mongo[DB_NAME]
    data_col = db[COL_DATA]
    meta_col = db[COL_META]
    
    # Ensure unique index on posted_uid
    meta_col.create_index([("posted_uid", 1)], unique=True)
    
    logger.info("✅ MongoDB connected successfully")
except Exception as e:
    logger.error(f"❌ MongoDB connection failed: {e}")
    raise

# -----------------------------
# Aiogram Setup with Custom Timeout
# -----------------------------
from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp import ClientTimeout

# Create session with longer timeout
session = AiohttpSession(
    timeout=ClientTimeout(
        total=60,      # Total timeout
        connect=30,    # Connection timeout
        sock_read=30,  # Socket read timeout
        sock_connect=30  # Socket connect timeout
    )
)

bot = Bot(BOT_TOKEN, session=session)
dp = Dispatcher()


# -----------------------------
# Helper Functions
# -----------------------------
def escape_html(text: str) -> str:
    """Escapes special characters for HTML parsing."""
    if not text:
        return ""
    return (text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def unique_movie_id(movie: Dict) -> str:
    """Generates a unique ID for a movie to prevent duplicate posting."""
    if movie.get("link"):
        return movie["link"]
    return f"{movie.get('title','')}||{movie.get('thumb','')}"


def fetch_latest_doc():
    """Fetches the latest document from the scraped data collection."""
    return data_col.find_one(sort=[("_id", -1)])


def gather_movies(doc) -> List[Dict]:
    """Combines latest_movies and random_movies from the document."""
    if not doc:
        return []
    return (doc.get("latest_movies", []) or []) + (doc.get("random_movies", []) or [])


def get_unposted_movies(limit=None) -> List[Dict]:
    """Retrieves movies that have not been posted yet."""
    doc = fetch_latest_doc()
    if not doc:
        logger.warning("⚠️ No documents found in database")
        return []

    movies = gather_movies(doc)
    result = []

    for m in movies:
        uid = unique_movie_id(m)
        exists = meta_col.find_one({"posted_uid": uid})
        if exists:
            continue

        result.append(m)
        if limit and len(result) >= limit:
            break

    return result


def build_caption(movie: Dict) -> str:
    """Formats the movie details into an HTML caption."""
    title = escape_html(movie.get("title", "No Title"))
    duration = movie.get("duration")
    
    lines = [f"<b>🎬 {title}</b>"]
    
    if duration:
        lines.append(f"⏱ Duration: {escape_html(duration)}")
    
    lines.extend(["", "⬇ Download Links ⬇", ""])

    for dl in movie.get("download_links", []):
        url = escape_html(dl.get("url", ""))
        quality = escape_html(dl.get("quality", "Link"))
        if url:
            lines.append(f"• <a href=\"{url}\">{quality}</a>")

    if not movie.get("download_links") and movie.get("link"):
        lines.append(f"• <a href=\"{escape_html(movie['link'])}\">🔗 Open Page</a>")

    return "\n".join(lines)


async def mark_movie_posted(movie):
    """Marks a movie as posted in the meta collection."""
    try:
        meta_col.insert_one({
            "posted_uid": unique_movie_id(movie),
            "title": movie.get("title"),
            "link": movie.get("link"),
            "thumb": movie.get("thumb"),
            "posted_at": datetime.now(pytz.utc)
        })
        logger.info(f"✅ Marked as posted: {movie.get('title')}")
        return True
    except DuplicateKeyError:
        logger.warning(f"⚠️ Duplicate key when marking {movie.get('title')} (already posted)")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to mark movie as posted {movie.get('title')}: {e}")
        return False


# -----------------------------
# Image Handling
# -----------------------------
async def fetch_image_as_inputfile(url: str) -> BufferedInputFile | None:
    """Fetches image data from URL."""
    if not url:
        return None

    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            async with session.get(url, headers=headers, timeout=15) as resp:
                if resp.status == 200 and 'image' in resp.content_type:
                    image_data = await resp.read()
                    return BufferedInputFile(image_data, filename="movie_thumb.jpg")
                else:
                    logger.warning(f"⚠️ Failed to fetch image: Status {resp.status}")
                    return None
    except Exception as e:
        logger.warning(f"⚠️ Error fetching image from {url}: {e}")
        return None


async def send_movie(movie: Dict):
    """Handles posting movie to channel."""
    caption = build_caption(movie)
    thumb_url = movie.get("thumb")
    photo_file = None

    if thumb_url:
        photo_file = await fetch_image_as_inputfile(thumb_url)

    try:
        if photo_file:
            await bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=photo_file,
                caption=caption,
                parse_mode=ParseMode.HTML
            )
            logger.info(f"📸 Posted as PHOTO: {movie.get('title')}")
        else:
            await bot.send_message(
                chat_id=CHANNEL_ID,
                text=caption,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
            logger.info(f"💬 Posted as MESSAGE: {movie.get('title')}")

        await mark_movie_posted(movie)
        await asyncio.sleep(POST_DELAY)

    except TelegramRetryAfter as e:
        retry_after = e.retry_after if e.retry_after > 0 else RETRY_DELAY
        logger.warning(f"⏳ Flood control hit. Retrying in {retry_after} seconds")
        await asyncio.sleep(retry_after + 1)
    except Exception as e:
        logger.error(f"❌ Failed posting {movie.get('title')}: {e}")
        await asyncio.sleep(RETRY_DELAY)


async def post_n_movies(n: int):
    """Posts the next N unposted movies."""
    movies = get_unposted_movies(limit=n)
    if not movies:
        logger.info("ℹ️ No movies to post right now")
        return

    logger.info(f"📤 Posting {len(movies)} movies")
    for m in movies:
        await send_movie(m)


async def post_all_remaining():
    """Posts all remaining unposted movies."""
    movies = get_unposted_movies()
    if not movies:
        logger.info("ℹ️ No movies remaining")
        return

    logger.info(f"📤 Posting ALL {len(movies)} remaining movies")
    for m in movies:
        await send_movie(m)


# -----------------------------
# Scheduler Setup
# -----------------------------
scheduler = AsyncIOScheduler(timezone=pytz.timezone(TZ))


def register_jobs():
    """Defines the cron jobs for automatic posting."""
    scheduler.add_job(post_n_movies, "cron", args=[4], hour=12, minute=0, id="post_12pm")
    scheduler.add_job(post_n_movies, "cron", args=[4], hour=15, minute=0, id="post_3pm")
    scheduler.add_job(post_n_movies, "cron", args=[4], hour=19, minute=0, id="post_7pm")
    scheduler.add_job(post_n_movies, "cron", args=[4], hour=22, minute=0, id="post_10pm")
    scheduler.add_job(post_all_remaining, "cron", hour=23, minute=55, id="post_remaining")

    logger.info("✅ Jobs scheduled successfully")
    logger.info("📅 Schedule: 12:00, 15:00, 19:00, 22:00 (4 movies each), 23:55 (all remaining)")


# -----------------------------
# Commands
# -----------------------------
@dp.message(Command("start"))
async def start_cmd(message: Message):
    text = (
        "👋 <b>Movie Auto Posting Bot</b>\n\n"
        f"📢 Channel: <code>{CHANNEL_ID}</code>\n\n"
        "⏰ <b>Posting Schedule (IST):</b>\n"
        "• 12:00 PM → 4 movies\n"
        "• 03:00 PM → 4 movies\n"
        "• 07:00 PM → 4 movies\n"
        "• 10:00 PM → 4 movies\n"
        "• 11:55 PM → all remaining\n\n"
        "📊 Commands:\n"
        "/status - Check unposted movies\n"
        "/postnow - Post next 4 movies immediately"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


@dp.message(Command("status"))
async def status_cmd(message: Message):
    movies = get_unposted_movies(limit=1000)
    count = len(movies)

    sample = "\n".join([
        f"{i+1}. {escape_html(m.get('title','No title'))}"
        for i, m in enumerate(movies[:10])
    ])

    if count > 10:
        sample += f"\n\n... and {count - 10} more"

    text = f"📊 <b>Unposted Movies: {count}</b>\n\n{sample}" if sample else "✅ All caught up!"
    await message.answer(text, parse_mode=ParseMode.HTML)


@dp.message(Command("postnow"))
async def postnow_cmd(message: Message):
    await message.answer("📤 Posting next 4 movies...")
    await post_n_movies(4)
    await message.answer("✅ Done!")


# -----------------------------
# MAIN
# -----------------------------
async def main():
    logger.info("🤖 Starting bot...")
    
    register_jobs()
    scheduler.start()
    
    logger.info("✅ Bot is ready and running!")
    
    # Retry logic for connection issues
    max_retries = 5
    retry_delay = 10
    
    for attempt in range(max_retries):
        try:
            await dp.start_polling(bot, polling_timeout=30)
            break  # Success, exit loop
        except Exception as e:
            logger.error(f"❌ Bot polling failed (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                logger.info(f"⏳ Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                logger.error("❌ Max retries reached. Bot failed to start.")
                raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⛔ Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        raise

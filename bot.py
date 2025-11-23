# bot.py — Aiogram + APScheduler | Final Version (Fixed MongoDB & Flood Control)

import os
import asyncio
import logging
from datetime import datetime
from typing import Dict, List

# Imports for Safe Image Posting
import aiohttp
from aiogram.types import BufferedInputFile
from aiogram.exceptions import TelegramRetryAfter 
from aiogram.client.bot import Bot as AiogramBot # Use alias for clarity

from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError 
from aiogram import Dispatcher
from aiogram.enums import ParseMode
from aiogram.types import Message
from aiogram.filters import Command
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# -----------------------------
# CONFIG
# -----------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN",
                          "8148829995:AAH8Org3ZQTXPqmhV0ilC5ozKSMuHC_4WPs")
MONGO_URI = os.environ.get(
    "MONGO_URI",
    "mongodb+srv://tejaschavan1110_db_user:PaR3JUapUXnFM5Ht@cluster0.o8vlhjq.mongodb.net/uiiu_scraper?retryWrites=true&w=majority&appName=Cluster0"
)
DB_NAME = "uiiu_scraper"
COL_DATA = "scraped_data"
COL_META = "meta_data"

# CHANNEL_ID must be an integer, ensure the env variable is set correctly
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1002484254899"))

TZ = "Asia/Kolkata"
RETRY_DELAY = 5 
POST_DELAY = 3 

# -----------------------------
# Logging
# -----------------------------
# Use a consistent logger name/setup across modules, but keep it in one place (main.py) if possible.
# For now, keep it here.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("aiogram_bot")


# -----------------------------
# MongoDB Setup
# -----------------------------
try:
    mongo = MongoClient(MONGO_URI)
    db = mongo[DB_NAME]
    data_col = db[COL_DATA]
    meta_col = db[COL_META]
    
    # IMPORTANT: Ensure index for unique movie ID posting check
    meta_col.create_index([("posted_uid", 1)], unique=True)
    logger.info("Bot: MongoDB connection and 'posted_uid' index ensured.")
except Exception as e:
    logger.error(f"Bot: MongoDB connection failed: {e}")
    # Consider what to do if connection fails (e.g., exit or pass)
    

# -----------------------------
# Aiogram Setup
# Global bot/dp variables
bot = AiogramBot(BOT_TOKEN)
dp = Dispatcher()


# -----------------------------
# Helper Functions (Database & Caption Building)
# -----------------------------
def escape_html(text: str) -> str:
    """Escapes special characters for HTML parsing."""
    if not text:
        return ""
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(
        ">", "&gt;").replace('"', "&quot;"))


def unique_movie_id(movie: Dict) -> str:
    """Generates a unique ID for a movie to prevent duplicate posting."""
    if movie.get("link"):
        return movie["link"]
    return f"{movie.get('title','')}||{movie.get('thumb','')}"


def fetch_latest_doc():
    """Fetches the latest document from the scraped data collection."""
    # Use the collection imported from global scope
    return data_col.find_one(sort=[("_id", -1)])


def gather_movies(doc) -> List[Dict]:
    """Combines latest_movies and random_movies from the document."""
    if not doc:
        return []
    return (doc.get("latest_movies", [])
            or []) + (doc.get("random_movies", []) or [])


def get_unposted_movies(limit=None) -> List[Dict]:
    """Retrieves movies that have not been posted yet."""
    doc = fetch_latest_doc()
    if not doc:
        return []

    movies = gather_movies(doc)
    result = []

    for m in movies:
        uid = unique_movie_id(m)
        # Check against the unique ID
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
    lines = [f"<b>{title}</b>", "", "⬇ Download✅ Stream Online✅⬇", ""]

    for dl in movie.get("download_links", []):
        url = escape_html(dl.get("url", ""))
        quality = escape_html(dl.get("quality", "Link"))
        if url:
            lines.append(f"• <a href=\"{url}\">{quality}</a>")

    if not movie.get("download_links") and movie.get("link"):
        lines.append(
            f"• <a href=\"{escape_html(movie['link'])}\">Open Page</a>")

    return "\n".join(lines)


async def mark_movie_posted(movie):
    """
    Marks a movie as posted in the meta collection.
    Handles the Duplicate Key (E11000) error gracefully.
    """
    try:
        meta_col.insert_one({
            "posted_uid": unique_movie_id(movie),
            "title": movie.get("title"),
            "link": movie.get("link"),
            "thumb": movie.get("thumb"),
            "posted_at": datetime.now(pytz.utc)
        })
        logger.info(f"Bot: Successfully marked as posted: {movie.get('title')}")
        return True
    except DuplicateKeyError:
        logger.warning(
            f"Bot: MongoDB Duplicate Key error when marking {movie.get('title')}. Assuming marked."
        )
        return True
    except Exception as e:
        logger.error(
            f"Bot: Failed to mark movie as posted {movie.get('title')}: {e}")
        return False

def delete_movie_from_db(movie):
    """
    Deletes the movie from scraped_data.latest_movies or random_movies
    after posting to avoid duplicates forever.
    """
    doc = fetch_latest_doc()
    if not doc:
        return

    # Pull from both arrays
    data_col.update_one(
        {"_id": doc["_id"]},
        {"$pull": {"latest_movies": {"title": movie.get("title")}}}
    )

    data_col.update_one(
        {"_id": doc["_id"]},
        {"$pull": {"random_movies": {"title": movie.get("title")}}}
    )

    logger.info(f"Bot: Deleted from DB -> {movie.get('title')}")


# -----------------------------
# CORE SOLUTION: Safe Image Posting & Anti-Flood
# -----------------------------
async def fetch_image_as_inputfile(url: str) -> BufferedInputFile | None:
    """
    Fetches image data from URL. It will likely fail if the server blocks bot access.
    """
    if not url:
        return None

    try:
        async with aiohttp.ClientSession() as session:
            # Set User-Agent to mimic a standard browser
            headers = {
                'User-Agent':
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36'
            }
            async with session.get(url, headers=headers, timeout=15) as resp:
                if resp.status == 200 and 'image' in resp.content_type:
                    image_data = await resp.read()
                    return BufferedInputFile(image_data,
                                             filename="movie_thumb.jpg")
                else:
                    logger.warning(
                        f"Bot: Failed to fetch image data from {url}. Status: {resp.status}, Type: {resp.content_type}"
                    )
                    return None
    except Exception as e:
        logger.error(f"Bot: Error fetching image from {url}: {e}")
        return None


async def send_movie(movie: Dict):
    """Handles fetching image and posting the movie safely to the channel."""
    caption = build_caption(movie)
    thumb_url = movie.get("thumb")
    photo_file = None

    # 1. Try to fetch the image data
    if thumb_url:
        photo_file = await fetch_image_as_inputfile(thumb_url)

    try:
        # --- Posting Attempt ---
        if photo_file:
            await bot.send_photo(chat_id=CHANNEL_ID,
                                 photo=photo_file,
                                 caption=caption,
                                 parse_mode=ParseMode.HTML)
            logger.info(f"Bot: Posted as PHOTO (Uploaded): {movie.get('title')}")

        else:
            # Fallback for failed image fetch (Bad Request issue)
            await bot.send_message(chat_id=CHANNEL_ID,
                                   text=caption,
                                   parse_mode=ParseMode.HTML,
                                   disable_web_page_preview=True)
            logger.info(f"Bot: Posted as MESSAGE (Fallback): {movie.get('title')}")

        # 2. Mark as posted only after successful send (or successful fallback)
        await delete_movie_from_db(movie)


        # 3. Anti-Flood Control: Wait for POST_DELAY seconds
        await asyncio.sleep(POST_DELAY)

    except TelegramRetryAfter as e:
        # Handle Telegram's flood control specifically
        retry_after = e.retry_after if e.retry_after > 0 else RETRY_DELAY
        logger.warning(
            f"Bot: Flood control hit. Retrying {movie.get('title')} in {retry_after} seconds."
        )
        await asyncio.sleep(retry_after + 1
                            ) 
        # Don't call mark_movie_posted, the post failed. The loop will retry on next schedule.

    except Exception as e:
        logger.error(f"Bot: Failed posting {movie.get('title')}: {e}")
        # Wait a bit on general errors to prevent hammering
        await asyncio.sleep(RETRY_DELAY)


def delete_movie_from_db(movie):
    """
    Deletes the movie from scraped_data.latest_movies or random_movies
    after posting to avoid duplicates forever.
    """
    doc = fetch_latest_doc()
    if not doc:
        return

    # Pull from both arrays
    data_col.update_one(
        {"_id": doc["_id"]},
        {"$pull": {"latest_movies": {"title": movie.get("title")}}}
    )

    data_col.update_one(
        {"_id": doc["_id"]},
        {"$pull": {"random_movies": {"title": movie.get("title")}}}
    )

    logger.info(f"Bot: Deleted from DB -> {movie.get('title')}")


async def post_n_movies(n: int):
    """Posts the next N unposted movies."""
    movies = get_unposted_movies(limit=n)
    if not movies:
        logger.info("Bot: No movies to post right now.")
        return

    logger.info(f"Bot: Posting {len(movies)} movies")
    for m in movies:
        await send_movie(m)


async def post_all_remaining():
    """Posts all remaining unposted movies."""
    movies = get_unposted_movies()
    if not movies:
        logger.info("Bot: No movies remaining.")
        return

    logger.info(f"Bot: Posting ALL {len(movies)} remaining movies")
    for m in movies:
        await send_movie(m)


# -----------------------------
# COMMANDS
# -----------------------------
@dp.message(Command("start"))
async def start_cmd(message: Message):
    text = ("👋 <b>Movie Auto Posting Bot</b>\n\n"
            f"Channel: <code>{CHANNEL_ID}</code>\n"
            "⏰ <b>Schedule:</b> (IST)\n"
            "12:00 → 4 posts\n"
            "15:00 → 4 posts\n"
            "19:00 → 4 posts\n"
            "22:00 → 4 posts\n"
            "23:55 → all remaining posts\n\n"
            "Use /status to view unposted movie count.")
    await message.answer(text, parse_mode=ParseMode.HTML)


@dp.message(Command("status"))
async def status_cmd(message: Message):
    movies = get_unposted_movies(limit=1000)
    count = len(movies)

    sample = "\n".join([
        f"{i+1}. {escape_html(m.get('title','No title'))}"
        for i, m in enumerate(movies[:10])
    ])

    await message.answer(f"Unposted Movies: <b>{count}</b>\n\n{sample}",
                         parse_mode=ParseMode.HTML)


@dp.message(Command("postnow"))
async def postnow_cmd(message: Message):
    await message.answer("Posting next 4 movies...")
    await post_n_movies(4)
    await message.answer("Done!")


# -----------------------------
# BOT SCHEDULER REGISTRATION
# -----------------------------
def register_bot_jobs(scheduler: AsyncIOScheduler):
    """Registers the bot's scheduled posting jobs."""
    # Posting 4 movies at scheduled times (IST)
    scheduler.add_job(post_n_movies, "cron", args=[4], hour=12, minute=0, timezone=TZ)
    scheduler.add_job(post_n_movies, "cron", args=[4], hour=15, minute=0, timezone=TZ)
    scheduler.add_job(post_n_movies, "cron", args=[4], hour=19, minute=50, timezone=TZ)
    scheduler.add_job(post_n_movies, "cron", args=[4], hour=21, minute=30, timezone=TZ) # Fixed hour 16:00 to 22:00
    
    # Post all remaining movies late at night (IST)
    scheduler.add_job(post_all_remaining, "cron", hour=23, minute=45, timezone=TZ) # Fixed hour 16:02 to 23:55

    logger.info("Bot: Posting jobs scheduled")


async def start_bot_polling():
    """Starts the bot's message processing."""
    if not BOT_TOKEN:
        raise Exception("BOT_TOKEN missing!")
    logger.info("Bot: Starting polling...")
    await dp.start_polling(bot)


# End of bot.py

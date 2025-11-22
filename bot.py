# bot.py — Aiogram + APScheduler | FINAL PRODUCTION VERSION

import os
import asyncio
import logging
from datetime import datetime
from typing import Dict, List

import aiohttp
from aiogram.types import BufferedInputFile
from aiogram.exceptions import TelegramRetryAfter
from aiogram.client.bot import Bot as AiogramBot
from aiogram import Dispatcher
from aiogram.enums import ParseMode
from aiogram.types import Message
from aiogram.filters import Command

from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz

# --------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8148829995:AAH8Org3ZQTXPqmhV0ilC5ozKSMuHC_4WPs")
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://tejaschavan1110:15HNqpSmaq40eQzX@cluster0.aoldz.mongodb.net/?retryWrites=true&w=majority")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1002063549539"))

DB_NAME = "uiiu_scraper"
COL_DATA = "scraped_data"
COL_META = "meta_data"

TZ = "Asia/Kolkata"
POST_DELAY = 3
RETRY_DELAY = 5

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("movie_bot")

# --------------------------------------------------------------------
# MongoDB CONNECTION
# --------------------------------------------------------------------
mongo = MongoClient(MONGO_URI)
db = mongo[DB_NAME]
data_col = db[COL_DATA]
meta_col = db[COL_META]

meta_col.create_index([("posted_uid", 1)], unique=True)
logger.info("MongoDB connected & unique index ready.")

# --------------------------------------------------------------------
# Aiogram Setup
# --------------------------------------------------------------------
bot = AiogramBot(BOT_TOKEN)
dp = Dispatcher()

# --------------------------------------------------------------------
# HELPERS
# --------------------------------------------------------------------
def escape_html(text: str):
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def unique_movie_id(movie: Dict):
    return movie.get("link") or movie.get("title")

def fetch_latest():
    return data_col.find_one(sort=[("_id", -1)])

def gather_movies(doc):
    return (doc.get("latest_movies") or []) + (doc.get("random_movies") or [])

def get_unposted_movies(limit=None):
    doc = fetch_latest()
    if not doc:
        return []

    movies = gather_movies(doc)
    result = []

    for m in movies:
        uid = unique_movie_id(m)
        if not meta_col.find_one({"posted_uid": uid}):
            result.append(m)
            if limit and len(result) == limit:
                break

    return result

def build_caption(movie: Dict) -> str:
    title = escape_html(movie.get("title", "No Title"))
    caption = [f"<b>{title}</b>", "", "⬇ Download Links ⬇", ""]

    for dl in movie.get("download_links", []):
        url = escape_html(dl.get("url", ""))
        quality = escape_html(dl.get("quality", "Link"))
        if url:
            caption.append(f"• <a href=\"{url}\">{quality}</a>")

    if not movie.get("download_links") and movie.get("link"):
        caption.append(f"• <a href=\"{escape_html(movie['link'])}\">Open Page</a>")

    return "\n".join(caption)


async def fetch_image(url: str):
    if not url:
        return None

    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=15) as r:
                if r.status == 200 and "image" in r.content_type:
                    data = await r.read()
                    return BufferedInputFile(data, filename="thumb.jpg")
    except Exception as e:
        logger.warning(f"Image fetch failed: {e}")

    return None


async def mark_posted(movie: Dict):
    try:
        meta_col.insert_one({
            "posted_uid": unique_movie_id(movie),
            "title": movie.get("title"),
            "link": movie.get("link"),
            "thumb": movie.get("thumb"),
            "posted_at": datetime.now(pytz.utc)
        })
        return True
    except DuplicateKeyError:
        return True
    except Exception as e:
        logger.error(f"Mark posted failed: {e}")
        return False


def delete_from_db(movie):
    doc = fetch_latest()
    if not doc:
        return

    data_col.update_one({"_id": doc["_id"]},
                        {"$pull": {"latest_movies": {"title": movie.get("title")}}})

    data_col.update_one({"_id": doc["_id"]},
                        {"$pull": {"random_movies": {"title": movie.get("title")}}})

    logger.info(f"Deleted from DB: {movie.get('title')}")


# --------------------------------------------------------------------
# SEND MOVIE
# --------------------------------------------------------------------
async def send_movie(movie: Dict):
    caption = build_caption(movie)
    thumb = await fetch_image(movie.get("thumb"))

    try:
        if thumb:
            await bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=thumb,
                caption=caption,
                parse_mode=ParseMode.HTML
            )
        else:
            await bot.send_message(
                chat_id=CHANNEL_ID,
                text=caption,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )

        await mark_posted(movie)
        delete_from_db(movie)
        await asyncio.sleep(POST_DELAY)

    except TelegramRetryAfter as e:
        logger.warning(f"Flood control hit! Retry after {e.retry_after} sec")
        await asyncio.sleep(e.retry_after + 1)

    except Exception as e:
        logger.error(f"Post failed: {e}")
        await asyncio.sleep(RETRY_DELAY)


async def post_n(n: int):
    movies = get_unposted_movies(limit=n)
    if not movies:
        logger.info("No movies to post")
        return

    for m in movies:
        await send_movie(m)


async def post_all():
    movies = get_unposted_movies()
    if not movies:
        return

    for m in movies:
        await send_movie(m)

# --------------------------------------------------------------------
# COMMANDS
# --------------------------------------------------------------------
@dp.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer(
        "<b>Movie Auto Posting Bot</b>\n\n"
        "⏰ Schedule (IST):\n"
        "12:00 → 4 posts\n"
        "15:00 → 4 posts\n"
        "19:00 → 4 posts\n"
        "22:00 → 4 posts\n"
        "23:55 → All remaining",
        parse_mode=ParseMode.HTML
    )

@dp.message(Command("status"))
async def status_cmd(message: Message):
    movies = get_unposted_movies(limit=1000)
    text = "<b>Unposted Movies:</b> {}\n\n".format(len(movies))
    for i, m in enumerate(movies[:10]):
        text += f"{i+1}. {escape_html(m.get('title'))}\n"
    await message.answer(text, parse_mode=ParseMode.HTML)

@dp.message(Command("postnow"))
async def postnow(message: Message):
    await message.answer("Posting next 4 movies...")
    await post_n(4)
    await message.answer("Done!")

# --------------------------------------------------------------------
# SCHEDULER
# --------------------------------------------------------------------
def register_jobs(scheduler):
    scheduler.add_job(post_n, "cron", args=[4], hour=21, minute=39, timezone=TZ)
    scheduler.add_job(post_n, "cron", args=[4], hour=21, minute=41, timezone=TZ)
    scheduler.add_job(post_n, "cron", args=[4], hour=19, minute=0, timezone=TZ)
    scheduler.add_job(post_n, "cron", args=[4], hour=22, minute=0, timezone=TZ)

    scheduler.add_job(post_all, "cron", hour=23, minute=55, timezone=TZ)

    logger.info("Scheduler jobs registered.")

# --------------------------------------------------------------------
# START BOT
# --------------------------------------------------------------------
async def start_bot():
    scheduler = AsyncIOScheduler()
    register_jobs(scheduler)
    scheduler.start()

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(start_bot())

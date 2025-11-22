import os
import requests
from bs4 import BeautifulSoup
from pymongo import MongoClient
from datetime import datetime, time
import asyncio
import re
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | SCRAPER | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

# ------------------------------------------------
# CONFIG (Environment Variables)
# ------------------------------------------------
BASE_URL = "https://uiiumovie.fun/page/{}/"
SCRAPE_TIME = time(11, 30)  # Changed to 11:30 AM (before first bot post at 12 PM)

MONGO_URI = os.environ.get(
    "MONGO_URI",
    "mongodb+srv://tejaschavan1110:15HNqpSmaq40eQzX@cluster0.aoldz.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
)
DB_NAME = "uiiu_scraper"
COL_DATA = "scraped_data"
COL_META = "meta_data"

# ------------------------------------------------
# MongoDB Connection with Error Handling
# ------------------------------------------------
try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    # Test connection
    client.admin.command('ping')
    db = client[DB_NAME]
    data_col = db[COL_DATA]
    meta_col = db[COL_META]
    
    # Create indexes
    data_col.create_index("created_at", expireAfterSeconds=86400)
    meta_col.create_index("name", unique=True)
    
    logger.info("✅ MongoDB connected successfully")
except Exception as e:
    logger.error(f"❌ MongoDB connection failed: {e}")
    raise


# ------------------------------------------------
# 🎯 MOVIE INNER PAGE SCRAPER
# ------------------------------------------------
def scrape_movie_details(url):
    """Extract all download links + duration safely."""
    logger.debug(f"Fetching inner page: {url}")

    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return {"download_links": [], "duration": None}

    soup = BeautifulSoup(r.text, "html.parser")

    movie_info = {
        "download_links": [],
        "duration": None
    }

    # Download Links
    try:
        dl_section = soup.find("div", id="download")
        if dl_section:
            for a in dl_section.find_all("a", href=True):
                movie_info["download_links"].append({
                    "quality": a.get_text(strip=True),
                    "url": a["href"]
                })
    except Exception as e:
        logger.warning(f"Error extracting download links: {e}")

    # Duration
    try:
        dur = soup.find("span", class_="runtime")
        if dur:
            movie_info["duration"] = dur.get_text(strip=True)
    except Exception as e:
        logger.warning(f"Error extracting duration: {e}")

    return movie_info


# ------------------------------------------------
# 🔥 SCRAPE 1 PAGE
# ------------------------------------------------
def scrape_page(page_number):
    url = BASE_URL.format(page_number)
    logger.info(f"🔍 Scraping Page: {url}")

    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
    except Exception as e:
        logger.error(f"❌ Request failed for page {page_number}: {e}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    final_data = {
        "page": page_number,
        "random_movies": [],
        "latest_movies": [],
        "created_at": datetime.utcnow()
    }

    # Random Movies
    random_section = soup.find("h3", text="Random Movie")
    if random_section:
        grid = random_section.find_next("div", class_="grid-container")
        if grid:
            for item in grid.find_all("div", class_="gmr-item-modulepost"):
                a_tag = item.find("a")
                img = item.find("img")

                if a_tag and img:
                    link = a_tag.get("href")
                    details = scrape_movie_details(link)

                    thumb_original = img.get("src")
                    thumb_no_size = re.sub(r'-\d+x\d+', '', thumb_original)

                    final_data["random_movies"].append({
                        "title": img.get("alt"),
                        "thumb": thumb_original,
                        "thumb_no_size": thumb_no_size,
                        "link": link,
                        "download_links": details["download_links"],
                        "duration": details["duration"]
                    })

    # Latest Movies
    latest_section = soup.find("h3", text="Latest Movie")
    if latest_section:
        main_section = latest_section.find_next("div", id="gmr-main-load")
        if main_section:
            for post in main_section.find_all("article"):
                a_tag = post.find("a", itemprop="url")
                img = post.find("img")

                if a_tag and img:
                    link = a_tag.get("href")
                    details = scrape_movie_details(link)

                    thumb_original = img.get("src")
                    thumb_no_size = re.sub(r'-\d+x\d+', '', thumb_original)

                    final_data["latest_movies"].append({
                        "title": img.get("alt"),
                        "thumb": thumb_original,
                        "thumb_no_size": thumb_no_size,
                        "link": link,
                        "download_links": details["download_links"],
                        "duration": details["duration"]
                    })

    if not final_data["random_movies"] and not final_data["latest_movies"]:
        logger.warning(f"⚠️ No movies found on page {page_number}")
        return None

    logger.info(f"✅ Found {len(final_data['random_movies'])} random + {len(final_data['latest_movies'])} latest movies")
    return final_data


# ------------------------------------------------
# 🚀 DAILY SINGLE-PAGE SCRAPE
# ------------------------------------------------
def scrape_one_page_for_today():
    logger.info("🔥 Running Daily One-Page Scraper...")

    try:
        meta = meta_col.find_one({"name": "last_page"})
        last_page = meta["page"] if meta else 0
        next_page = last_page + 1

        result = scrape_page(next_page)

        if not result:
            logger.error(f"❌ Page {next_page} returned no data")
            return

        data_col.insert_one(result)

        meta_col.update_one(
            {"name": "last_page"},
            {"$set": {"page": next_page, "updated_at": datetime.utcnow()}},
            upsert=True
        )

        logger.info(f"✅ Successfully saved Page {next_page} to database!")
        
    except Exception as e:
        logger.error(f"❌ Error in scrape_one_page_for_today: {e}")


# ------------------------------------------------
# 🕒 FIXED TIME SCHEDULER
# ------------------------------------------------
async def run_daily_scheduler():
    logger.info("⏳ Scraper scheduler started...")
    logger.info(f"📅 Scrape time set to: {SCRAPE_TIME} (IST)")

    while True:
        try:
            now = datetime.now()
            target = datetime.combine(now.date(), SCRAPE_TIME)

            if now > target:
                from datetime import timedelta
                target = target + timedelta(days=1)

            wait_seconds = (target - now).total_seconds()
            logger.info(f"⏰ Next scrape at: {target.strftime('%Y-%m-%d %H:%M:%S')} (in {wait_seconds:.0f} seconds)")
            
            await asyncio.sleep(wait_seconds)
            scrape_one_page_for_today()
            
        except Exception as e:
            logger.error(f"❌ Scheduler error: {e}")
            # Wait 5 minutes before retrying
            await asyncio.sleep(300)


# ------------------------------------------------
# MAIN
# ------------------------------------------------
if __name__ == "__main__":
    try:
        logger.info("🚀 Starting scraper as standalone...")
        asyncio.run(run_daily_scheduler())
    except KeyboardInterrupt:
        logger.info("⛔ Scraper stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        raise

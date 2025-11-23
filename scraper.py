import requests
from bs4 import BeautifulSoup
from pymongo import MongoClient
from datetime import datetime, time
import re

# ------------------------------------------------
# CONFIG (Must be the same as in bot.py, or better: use a config file/env)
# ------------------------------------------------
BASE_URL = "https://uiiumovie.fun/page/{}/"
# SCRAPE_TIME is not needed here anymore, the scheduler in main.py will handle it.

# CONFIG: Use a separate, consistent way for env variables if possible
MONGO_URI = "mongodb+srv://tejaschavan1110:15HNqpSmaq40eQzX@cluster0.aoldz.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
DB_NAME = "uiiu_scraper"
COL_DATA = "scraped_data"
COL_META = "meta_data"

try:
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    data_col = db[COL_DATA]
    meta_col = db[COL_META]

    # Ensure indexes are created/updated
    data_col.create_index([("created_at", 1)], expireAfterSeconds=86400)
    meta_col.create_index([("name", 1)], unique=True)
    print("Scraper: MongoDB connection and index setup successful.")
except Exception as e:
    print(f"Scraper: MongoDB connection/setup failed: {e}")


# ------------------------------------------------
# 🎯 MOVIE INNER PAGE SCRAPER
# ------------------------------------------------
def scrape_movie_details(url):
    """Extract all download links + duration safely."""
    # print(f"    ↳ Fetching inner page: {url}") # Reduced logging

    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
    except:
        return {"download_links": [], "duration": None}

    soup = BeautifulSoup(r.text, "html.parser")

    movie_info = {
        "download_links": [],
        "duration": None
    }

    # ⭐ DOWNLOAD LINKS
    try:
        dl_section = soup.find("div", id="download")
        if dl_section:
            for a in dl_section.find_all("a", href=True):
                original = a["href"]
                short = shorten_url(original)
    
                movie_info["download_links"].append({
                    "quality": a.get_text(strip=True),
                    "url": short
                })
    except:
        pass


    # ⭐ DURATION
    try:
        dur = soup.find("span", class_="runtime")
        if dur:
            movie_info["duration"] = dur.get_text(strip=True)
    except:
        pass

    return movie_info


# ------------------------------------------------
# 🔥 SCRAPE 1 PAGE
# ------------------------------------------------
def scrape_page(page_number):
    url = BASE_URL.format(page_number)
    print(f"\nScraper: Scraping Page: {url}")

    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
    except:
        print("Scraper: Request failed...")
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    final_data = {
        "page": page_number,
        "random_movies": [],
        "latest_movies": [],
        "created_at": datetime.utcnow()
    }

    # RANDOM MOVIES
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
                    # thumb_no_size = re.sub(r'-\d+x\d+', '', thumb_original) # Not needed to store

                    final_data["random_movies"].append({
                        "title": img.get("alt"),
                        "thumb": thumb_original,
                        "link": link,
                        "download_links": details["download_links"],
                        "duration": details["duration"]
                    })

    # LATEST MOVIES
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
                    # thumb_no_size = re.sub(r'-\d+x\d+', '', thumb_original) # Not needed to store

                    final_data["latest_movies"].append({
                        "title": img.get("alt"),
                        "thumb": thumb_original,
                        "link": link,
                        "download_links": details["download_links"],
                        "duration": details["duration"]
                    })

    if not final_data["random_movies"] and not final_data["latest_movies"]:
        return None

    return final_data

def shorten_url(long_url):
    try:
        api_key = "180027087e13f4a147d7615e8ac5a8d93240050c"

        # URL ENCODE REQUIRED
        encoded = requests.utils.quote(long_url, safe='')

        api_url = (
            f"https://arolinks.com/api?"
            f"api={api_key}&url={encoded}&format=json"
        )

        r = requests.get(api_url, timeout=10)
        data = r.json()

        # Expected format:
        # {"status":"success","shortenedUrl":"https:\/\/arolinks.com\/xxxxx"}

        if data.get("status") == "success":
            return data.get("shortenedUrl", long_url)

        return long_url

    except Exception as e:
        print("Shortener Error:", e)
        return long_url


# ------------------------------------------------
# 🚀 JOB FUNCTION FOR SCHEDULER
# ------------------------------------------------
def scrape_one_page_for_today():
    """Function to be called by APScheduler."""
    print("🔥 Scraper: Running Daily One-Page Scraper...")

    meta = meta_col.find_one({"name": "last_page"})
    last_page = meta["page"] if meta else 0
    next_page = last_page + 1

    result = scrape_page(next_page)

    if not result:
        print(f"❌ Scraper: Page {next_page} empty. Not updating meta.")
        return

    # Check if we got any movies before saving
    if result.get("latest_movies") or result.get("random_movies"):
        data_col.insert_one(result)
        
        meta_col.update_one(
            {"name": "last_page"},
            {"$set": {"page": next_page, "updated_at": datetime.utcnow()}},
            upsert=True
        )
        print(f"✔ Scraper: Saved Page {next_page} successfully! ({len(result.get('latest_movies', [])) + len(result.get('random_movies', []))} movies)")
    else:
        print(f"❌ Scraper: Page {next_page} contained no valid movies. Not saving/updating meta.")


# Remove the old main block
# if __name__ == "__main__":
#     asyncio.run(run_daily_scheduler())

import os
import json
import asyncio
from datetime import datetime, time
from typing import List, Dict
import requests
from bs4 import BeautifulSoup
from pymongo import MongoClient
from telegram import Bot
from telegram.error import TelegramError
import logging

# ================================================
# 📌 CONFIGURATION - CUSTOMIZE YE SAB
# ================================================

# Telegram Settings
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
TELEGRAM_CHANNEL_ID = "@your_channel_username"  # ya -100xxxxx channel ID

# MongoDB Settings
MONGO_URI = "mongodb://localhost:27017/"
DATABASE_NAME = "movie_scraper_db"
COLLECTION_NAME = "scraped_movies"

# Scraping Settings
BASE_URL = "https://uiiumovie.fun/page/{}/"
SCRAPE_TIME = time(11, 0)  # 11:00 AM

# Posting Schedule (24-hour format)
POSTING_SCHEDULE = [
    {"time": time(12, 0), "posts": 4},   # 12:00 PM - 4 posts
    {"time": time(15, 0), "posts": 4},   # 3:00 PM - 4 posts
    {"time": time(19, 0), "posts": 4},   # 7:00 PM - 4 posts
    {"time": time(22, 0), "posts": -1},  # 10:00 PM - remaining posts (-1 means all remaining)
]

# ================================================
# 📌 LOGGING SETUP
# ================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ================================================
# 📌 MONGODB CONNECTION
# ================================================
class MongoDB:
    def __init__(self):
        self.client = MongoClient(MONGO_URI)
        self.db = self.client[DATABASE_NAME]
        self.collection = self.db[COLLECTION_NAME]
    
    def save_scraped_data(self, data: Dict):
        """Save scraped data to MongoDB"""
        data['scraped_at'] = datetime.now()
        data['posted_count'] = 0
        data['all_posted'] = False
        result = self.collection.insert_one(data)
        logger.info(f"✅ Data saved to MongoDB with ID: {result.inserted_id}")
        return result.inserted_id
    
    def get_current_page_data(self):
        """Get today's scraped data that hasn't been fully posted"""
        today = datetime.now().date()
        data = self.collection.find_one({
            'scraped_at': {
                '$gte': datetime.combine(today, time.min),
                '$lt': datetime.combine(today, time.max)
            },
            'all_posted': False
        })
        return data
    
    def update_posted_count(self, doc_id, count: int):
        """Update the number of posts sent"""
        self.collection.update_one(
            {'_id': doc_id},
            {'$set': {'posted_count': count}}
        )
    
    def mark_all_posted(self, doc_id):
        """Mark all posts as sent"""
        self.collection.update_one(
            {'_id': doc_id},
            {'$set': {'all_posted': True}}
        )
    
    def get_current_page_number(self):
        """Get the next page number to scrape"""
        last_doc = self.collection.find_one(
            sort=[('page', -1)]
        )
        if last_doc:
            return last_doc.get('page', 0) + 1
        return 1


# ================================================
# 📌 SCRAPER CLASS
# ================================================
class MovieScraper:
    def __init__(self):
        self.base_url = BASE_URL
    
    def scrape_page(self, page_number: int) -> Dict:
        """Scrape a single page"""
        url = self.base_url.format(page_number)
        logger.info(f"🔍 Scraping Page: {url}")
        
        try:
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                logger.warning(f"❌ Invalid page {page_number}, status: {r.status_code}")
                return None
        except Exception as e:
            logger.error(f"❌ Page request failed: {e}")
            return None
        
        soup = BeautifulSoup(r.text, "html.parser")
        
        final_data = {
            "page": page_number,
            "random_movies": [],
            "latest_movies": []
        }
        
        # Scrape Random Movies
        random_section = soup.find("h3", text="Random Movie")
        if random_section:
            grid = random_section.find_next("div", class_="grid-container")
            if grid:
                items = grid.find_all("div", class_="gmr-item-modulepost")
                for item in items:
                    a_tag = item.find("a")
                    img = item.find("img")
                    if a_tag and img:
                        final_data["random_movies"].append({
                            "title": img.get("alt"),
                            "thumb": img.get("src"),
                            "link": a_tag.get("href")
                        })
        
        # Scrape Latest Movies
        latest_section = soup.find("h3", text="Latest Movie")
        if latest_section:
            main_section = latest_section.find_next("div", id="gmr-main-load")
            if main_section:
                posts = main_section.find_all("article")
                for post in posts:
                    a_tag = post.find("a", itemprop="url")
                    img = post.find("img")
                    if a_tag and img:
                        final_data["latest_movies"].append({
                            "title": img.get("alt"),
                            "thumb": img.get("src"),
                            "link": a_tag.get("href")
                        })
        
        # Check if data exists
        if not final_data["random_movies"] and not final_data["latest_movies"]:
            logger.warning(f"⚠️ No data found on page {page_number}")
            return None
        
        logger.info(f"✅ Page {page_number} scraped successfully")
        logger.info(f"   Random Movies: {len(final_data['random_movies'])}")
        logger.info(f"   Latest Movies: {len(final_data['latest_movies'])}")
        
        return final_data


# ================================================
# 📌 TELEGRAM BOT CLASS
# ================================================
class TelegramMovieBot:
    def __init__(self):
        self.bot = Bot(token=TELEGRAM_BOT_TOKEN)
        self.channel_id = TELEGRAM_CHANNEL_ID
    
    async def send_movie_post(self, movie: Dict):
        """Send a single movie post to channel"""
        try:
            message = f"🎬 {movie['title']}\n\n🔗 {movie['link']}"
            
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=message
            )
            logger.info(f"✅ Posted: {movie['title']}")
            return True
        except TelegramError as e:
            logger.error(f"❌ Failed to post {movie['title']}: {e}")
            return False
    
    async def send_multiple_posts(self, movies: List[Dict], count: int = -1):
        """Send multiple movie posts"""
        if count == -1:
            count = len(movies)
        
        movies_to_send = movies[:count]
        success_count = 0
        
        for movie in movies_to_send:
            if await self.send_movie_post(movie):
                success_count += 1
            await asyncio.sleep(2)  # 2 second delay between posts
        
        logger.info(f"📤 Sent {success_count}/{len(movies_to_send)} posts")
        return success_count


# ================================================
# 📌 SCHEDULER CLASS
# ================================================
class BotScheduler:
    def __init__(self):
        self.db = MongoDB()
        self.scraper = MovieScraper()
        self.bot = TelegramMovieBot()
    
    async def scrape_daily_page(self):
        """Scrape one page daily"""
        logger.info("🚀 Starting daily scraping task...")
        
        page_number = self.db.get_current_page_number()
        data = self.scraper.scrape_page(page_number)
        
        if data:
            self.db.save_scraped_data(data)
            logger.info(f"✅ Page {page_number} scraped and saved")
        else:
            logger.error(f"❌ Failed to scrape page {page_number}")
    
    async def post_scheduled_movies(self, post_count: int):
        """Post movies according to schedule"""
        logger.info(f"📤 Starting posting task (count: {post_count})...")
        
        data = self.db.get_current_page_data()
        
        if not data:
            logger.warning("⚠️ No data available to post")
            return
        
        # Combine all movies
        all_movies = data.get('random_movies', []) + data.get('latest_movies', [])
        posted_count = data.get('posted_count', 0)
        
        # Get remaining movies
        remaining_movies = all_movies[posted_count:]
        
        if not remaining_movies:
            logger.info("✅ All movies already posted")
            return
        
        # Determine how many to post
        if post_count == -1:
            movies_to_post = remaining_movies
        else:
            movies_to_post = remaining_movies[:post_count]
        
        # Send posts
        sent_count = await self.bot.send_multiple_posts(movies_to_post, len(movies_to_post))
        
        # Update database
        new_posted_count = posted_count + sent_count
        self.db.update_posted_count(data['_id'], new_posted_count)
        
        # Check if all posted
        if new_posted_count >= len(all_movies):
            self.db.mark_all_posted(data['_id'])
            logger.info("🎉 All movies posted for today!")
    
    async def run_scheduler(self):
        """Main scheduler loop"""
        logger.info("🤖 Bot Scheduler Started!")
        
        while True:
            now = datetime.now().time()
            
            # Check scraping time
            if now.hour == SCRAPE_TIME.hour and now.minute == SCRAPE_TIME.minute:
                await self.scrape_daily_page()
                await asyncio.sleep(60)  # Wait 1 minute to avoid duplicate
            
            # Check posting times
            for schedule in POSTING_SCHEDULE:
                sched_time = schedule['time']
                if now.hour == sched_time.hour and now.minute == sched_time.minute:
                    await self.post_scheduled_movies(schedule['posts'])
                    await asyncio.sleep(60)  # Wait 1 minute
            
            await asyncio.sleep(30)  # Check every 30 seconds


# ================================================
# 📌 MAIN FUNCTION
# ================================================
async def main():
    """Main entry point"""
    logger.info("=" * 50)
    logger.info("🎬 TELEGRAM MOVIE BOT STARTING")
    logger.info("=" * 50)
    
    scheduler = BotScheduler()
    await scheduler.run_scheduler()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")

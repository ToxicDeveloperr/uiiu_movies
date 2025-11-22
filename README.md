# 🎬 Movie Scraper & Telegram Bot

Automated movie scraper that fetches movie data from websites and posts to Telegram channel at scheduled times.

## ✨ Features

- 🔄 **Auto Scraping** - Daily scraping at 11:30 AM IST
- 📤 **Scheduled Posting** - Posts movies at 12 PM, 3 PM, 7 PM, 10 PM
- 💾 **MongoDB Storage** - Persistent data storage
- 🐳 **Docker Support** - Easy deployment
- 🔒 **Secure** - Environment variables for sensitive data
- 📊 **Status Commands** - Check bot status via Telegram

## 📋 Requirements

- Python 3.11+
- MongoDB Atlas account (free)
- Telegram Bot Token
- Docker (for containerized deployment)

## 🚀 Quick Start

### 1️⃣ Clone Repository

```bash
git clone https://github.com/yourusername/movie-scraper-bot.git
cd movie-scraper-bot
```

### 2️⃣ Configure Environment

Create `.env` file:

```env
BOT_TOKEN=your_telegram_bot_token
MONGO_URI=your_mongodb_connection_string
CHANNEL_ID=your_telegram_channel_id
```

### 3️⃣ Run with Docker

```bash
# Build image
docker build -t movie-bot .

# Run container
docker run --env-file .env movie-bot
```

### 4️⃣ Or Run Locally

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run
python main.py
```

## 📅 Schedule

| Time | Action |
|------|--------|
| 11:30 AM | Scrape new page |
| 12:00 PM | Post 4 movies |
| 03:00 PM | Post 4 movies |
| 07:00 PM | Post 4 movies |
| 10:00 PM | Post 4 movies |
| 11:55 PM | Post remaining |

## 🤖 Telegram Commands

- `/start` - Show bot info and schedule
- `/status` - Check unposted movies count
- `/postnow` - Post next 4 movies immediately

## 🌐 Deployment

### Render.com (Recommended)

1. Fork this repository
2. Create new Worker service on Render
3. Connect GitHub repository
4. Add environment variables
5. Deploy!

See [Deployment Guide](render-deployment-guide.md) for detailed steps.

### Railway.app

```bash
# Install Railway CLI
npm i -g @railway/cli

# Login
railway login

# Deploy
railway up
```

## 📂 Project Structure

```
movie-scraper-bot/
├── scraper.py          # Web scraper
├── bot.py              # Telegram bot
├── main.py             # Combined runner
├── requirements.txt    # Dependencies
├── Dockerfile          # Docker config
├── .dockerignore       # Docker ignore rules
├── render.yaml         # Render config
└── README.md           # This file
```

## 🔧 Configuration

### Scraper Settings

Edit `scraper.py`:

```python
BASE_URL = "https://your-movie-site.com/page/{}/"
SCRAPE_TIME = time(11, 30)  # HH, MM
```

### Bot Settings

Edit `bot.py`:

```python
TZ = "Asia/Kolkata"
POST_DELAY = 3  # Seconds between posts
```

## 📊 Monitoring

### View Logs

```bash
# Docker
docker logs -f <container_id>

# Local
tail -f bot.log
```

### Check Status

Send `/status` command to bot in Telegram

## 🛠️ Troubleshooting

### Bot Not Posting

1. Check MongoDB connection
2. Verify bot is admin in channel
3. Check channel ID format (should be negative)
4. View logs for errors

### Scraper Not Working

1. Test website accessibility
2. Check if website structure changed
3. Verify MongoDB write permissions
4. Check scrape time configuration

### Docker Issues

```bash
# Rebuild image
docker build --no-cache -t movie-bot .

# Check container logs
docker logs <container_id>

# Restart container
docker restart <container_id>
```

## 📝 Development

### Run Tests

```bash
python -m pytest tests/
```

### Code Formatting

```bash
black *.py
```

### Type Checking

```bash
mypy *.py
```

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## 📄 License

MIT License - See [LICENSE](LICENSE) file for details

## ⚠️ Disclaimer

This bot is for educational purposes. Ensure you have permission to scrape websites and comply with their terms of service.

## 🙏 Acknowledgments

- [Aiogram](https://aiogram.dev/) - Telegram Bot framework
- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/) - Web scraping
- [MongoDB](https://www.mongodb.com/) - Database

## 📞 Support

For issues and questions:
- Open an [Issue](https://github.com/yourusername/movie-scraper-bot/issues)
- Contact: your.email@example.com

---

Made with ❤️ for movie lovers

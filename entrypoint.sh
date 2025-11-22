#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status

# Use PORT from environment, fallback to 8080
PORT=${PORT:-8080}

# Start Flask app in background
gunicorn --bind 0.0.0.0:$PORT app:app &

# Start Telegram bot & scraper
python main.py

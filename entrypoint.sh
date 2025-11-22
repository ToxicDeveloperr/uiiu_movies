#!/bin/bash
# Start Flask app with Gunicorn on required $PORT
gunicorn --bind 0.0.0.0:8080 app:app &

# Start Telegram bot
python main.py

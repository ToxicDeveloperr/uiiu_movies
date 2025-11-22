#!/bin/bash

# Movie Scraper Bot - Setup Script
echo "🚀 Setting up Movie Scraper Bot..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found. Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
fi

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found!"
    echo "Creating .env from template..."
    cat > .env << EOF
BOT_TOKEN=your_bot_token_here
MONGO_URI=your_mongodb_uri_here
CHANNEL_ID=your_channel_id_here
EOF
    echo "📝 Please edit .env file with your credentials"
    exit 1
fi

# Build Docker image
echo "🐳 Building Docker image..."
docker build -t movie-scraper-bot .

if [ $? -eq 0 ]; then
    echo "✅ Docker image built successfully!"
    echo ""
    echo "🎯 To run the bot:"
    echo "   docker run --env-file .env movie-scraper-bot"
    echo ""
    echo "🔍 To view logs:"
    echo "   docker logs -f <container_id>"
    echo ""
    echo "⛔ To stop:"
    echo "   docker stop <container_id>"
else
    echo "❌ Build failed. Check errors above."
    exit 1
fi

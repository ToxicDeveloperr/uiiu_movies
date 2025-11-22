# Use a slim Python image for smaller size
FROM python:3.11-slim

WORKDIR /usr/src/app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all app files
COPY . .

# Make entrypoint executable
RUN chmod +x entrypoint.sh

# Expose port (Koyeb sets $PORT automatically)
EXPOSE 8080

# Start the container
CMD ["./entrypoint.sh"]

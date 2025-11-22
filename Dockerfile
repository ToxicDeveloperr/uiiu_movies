# Use a slim Python image for a smaller container size
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /usr/src/app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application files
COPY . .

# Expose the port that Flask will listen on (usually handled by the platform)
EXPOSE 8000 

# Define the command to run the main worker process
# Note: For Koyeb, you will typically use the "Docker Command" setting 
# in the UI as 'python main.py' and the Web App as 'gunicorn app:app'
CMD ["./entrypoint.sh"]

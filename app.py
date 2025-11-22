from flask import Flask
import os

# Create a minimal Flask app instance
app = Flask(__name__)

# A simple health check route
@app.route('/')
def home():
    return "Bot Worker is running on the 'worker' process."

if __name__ == '__main__':
    # Render/Koyeb provides the port via an environment variable
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

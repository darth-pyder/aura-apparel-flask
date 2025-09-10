# In wsgi.py
import sys
import os

# Add your project's directory to the Python path
path = os.path.dirname(os.path.abspath(__file__))
if path not in sys.path:
    sys.path.insert(0, path)

# Import the app and socketio instance from your main application file
from app import socketio, app

# The application to run is the socketio instance, which wraps the Flask app
application = socketio
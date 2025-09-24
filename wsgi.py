# In wsgi.py
import eventlet

# THE DEFINITIVE FIX:
# This patches the standard Python libraries to make them compatible with
# the eventlet asynchronous model used by SocketIO. This allows psycopg2
# to work correctly from within a Socket.IO event handler.
eventlet.monkey_patch()

from app import app, socketio

if __name__ == "__main__":
    socketio.run(app)
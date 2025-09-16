#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

echo "--- RUNNING DATABASE SETUP ---"
python setup_database.py
echo "--- DATABASE SETUP COMPLETE ---"

echo "--- STARTING GUNICORN SERVER ---"
gunicorn -w 1 -k eventlet app:app
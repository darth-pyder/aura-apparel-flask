# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends gcc

# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Download the spaCy model
RUN python -m spacy download en_core_web_sm

# Copy the rest of your application code into the container
COPY . .

# Generate the database when the container builds
RUN python setup_database.py

# Command to run your app
# We use gunicorn, a production-ready server, with a specific worker class for SocketIO
CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "wsgi:app"]
# Use an official, slim Python runtime
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# --- THIS IS THE MODIFIED LINE ---
# First, update all system package lists, then upgrade them, then install gcc.
# This makes the build process more reliable.
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends gcc

# Install the Python dependencies from your new, clean requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Download the spaCy model if you are using it
# If you are using the AI-Router version, you can comment out or delete the next line
# RUN python -m spacy download en_core_web_sm

# Copy the rest of your application code into the container
COPY . .


# Command to run your app using a production server
CMD ["./start.sh"]
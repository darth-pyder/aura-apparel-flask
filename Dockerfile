# Use an official, slim Python runtime
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code into the container
COPY . .

# --- THIS IS THE CRITICAL NEW STEP ---
# Run the database setup script. Render will cache this layer, 
# so it will only run once on the very first deploy.
RUN python first_run.py

# Command to run your app
CMD ["gunicorn", "-w", "1", "-k", "eventlet", "app:app"]
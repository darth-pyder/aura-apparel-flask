# Use an official, slim Python runtime
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code into the container
COPY . .

# This command tells Render how to start your web server
# It uses gunicorn, a production-ready server, with a special worker for SocketIO
CMD ["gunicorn", "-w", "1", "-k", "eventlet", "app:app"]
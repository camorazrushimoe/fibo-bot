# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
# (We'll create a requirements.txt file next)
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# Using --no-cache-dir reduces image size
RUN pip install --no-cache-dir -r requirements.txt

# Copy the current directory contents into the container at /app
COPY . .

# Make port 80 available to the world outside this container (if needed for webhooks, not needed for polling)
# EXPOSE 80

# Define environment variables (optional, if you switch token to env var)
# ENV TELEGRAM_BOT_TOKEN=your_token_here

# Run tele-bot.py when the container launches
CMD ["python", "./tele-bot.py"]

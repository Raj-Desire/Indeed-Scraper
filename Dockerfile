# Official Microsoft Playwright image with Python and all browser system dependencies pre-installed
FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

# Prevent Python from writing .pyc files and enable unbuffered output for real-time Azure logs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Install Playwright Chromium browser and verify system dependencies
RUN playwright install chromium

# Copy application source code
COPY . .

# Create outputs, sessions, and logs directories
RUN mkdir -p outputs sessions logs

# Expose default application port
EXPOSE 8000

# Set environment defaults for Azure
ENV DASHBOARD_HOST=0.0.0.0
ENV PORT=8000
ENV SCRAPER_HEADLESS=true

# Run the FastAPI server via uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

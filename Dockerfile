# Playwright Official Python Image with pre-installed Chromium system dependencies
FROM mcr.microsoft.com/playwright/python:v1.48.0-noble

WORKDIR /app

# Upgrade pip and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install Playwright browser binary
RUN playwright install chromium

# Copy application files
COPY . .

# Environment Defaults
ENV HOST=0.0.0.0
ENV PORT=8000
ENV SCRAPER_HEADLESS=true

EXPOSE 8000

CMD ["python", "main.py"]

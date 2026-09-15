#!/usr/bin/env bash
# Exit immediately if a command exits with a non-zero status
set -o errexit

echo "==> Upgrading pip..."
pip install --upgrade pip

echo "==> Installing Python dependencies..."
pip install -r requirements.txt

echo "==> Installing Playwright Chromium browser & system dependencies..."
playwright install --with-deps chromium

echo "==> Build complete!"

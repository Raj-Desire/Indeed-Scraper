"""
DIW Indeed Job Scraper — Main Application
=========================================
Starts the FastAPI web application server.
Run with:
    python main.py
"""

from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config.settings import get_settings
from app.dashboard.router import router
from app.utils.logger import setup_logging, logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(log_dir=settings.log_dir, level="INFO")
    logger.info("=" * 60)
    logger.info("Indeed Job Scraper Application Started")
    logger.info("Open Browser: http://{}:{}", settings.dashboard_host, settings.dashboard_port)
    logger.info("=" * 60)
    yield
    logger.info("Indeed Job Scraper Stopped")


app = FastAPI(
    title="Indeed Job Scraper",
    description="Simple Indeed Job Sourcing Application",
    version="2.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

# Static files
static_dir = Path("static")
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Routes
app.include_router(router)

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "main:app",
        host=settings.dashboard_host,
        port=settings.dashboard_port,
        reload=False,
        log_level="info",
        workers=1,
    )

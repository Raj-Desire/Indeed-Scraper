import asyncio
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config.settings import get_settings
from app.dashboard.router import router
from app.utils.logger import setup_logging, logger


async def _open_browser_later(url: str):
    await asyncio.sleep(1.2)
    webbrowser.open(url)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(log_dir=settings.log_dir, level="INFO")
    host_for_browser = "127.0.0.1" if settings.dashboard_host in ("0.0.0.0", "0") else settings.dashboard_host
    url = f"http://{host_for_browser}:{settings.dashboard_port}"
    
    logger.info("=" * 60)
    logger.info("Indeed Job Scraper Application Started")
    logger.info("Open Browser: {}", url)
    logger.info("=" * 60)

    # Automatically open default browser in desktop environment
    asyncio.create_task(_open_browser_later(url))

    yield
    logger.info("Indeed Job Scraper Stopped")


app = FastAPI(
    title="Indeed Job Scraper",
    description="Simple Indeed Job Sourcing Application",
    version="2.0.0",
    lifespan=lifespan, # Run this function when the application starts and when it shuts down
    docs_url=None, # disable swagger ui bcz we use custom ui
    redoc_url=None, # disable redoc ui bcz we use custom ui
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

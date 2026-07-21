# Simple Indeed Job Scraper — Developer Guide

Welcome to the **Indeed Job Scraper** project! This lightweight single-page application allows users to enter any custom **Country**, **Job Role / Keyword** (e.g., *AI Developer*, *React Developer*, *Data Engineer*), and **Pages to Scrape** to fetch remote job leads and export clean Excel files.

---

## 📁 Clean Directory Map

```
c:\Projects\Indeed Scraper\
├── main.py                         # Application Entry Point (FastAPI + Uvicorn)
├── .env.example                    # Configuration Template
├── .env                            # Active Environment Configuration
├── requirements.txt                # Lightweight Python Dependencies
├── README.md                       # Project Setup & Overview
├── DEVELOPER_GUIDE.md              # THIS FILE — Developer Architecture Guide
│
├── app/                            # Application Source Code
│   ├── config/                     # Settings & Country Mappings
│   │   ├── constants.py            # Country list & domain resolver
│   │   └── settings.py             # Pydantic BaseSettings (reads from .env)
│   │
│   ├── models/                     # Data Models
│   │   ├── job.py                  # JobPosting data schema
│   │   └── scraper.py              # ScraperProgress & RunConfig models
│   │
│   ├── scraper/                    # Scraping Engine
│   │   └── indeed_scraper.py       # Playwright Chromium scraper (stealth, retries, pause/stop)
│   │
│   ├── parser/                     # HTML Parser
│   │   └── job_parser.py           # BeautifulSoup4 extractor (multi-selector fallback)
│   │
│   ├── filters/                    # Pipeline Filters
│   │   ├── date_filter.py          # Date age window filter (30 days default)
│   │   └── dedup_filter.py         # Job ID & text fingerprint deduplication
│   │
│   ├── excel/                      # Report Generator
│   │   └── exporter.py             # Openpyxl Excel builder with auto-width & hyperlinks
│   │
│   ├── services/                   # Pipeline Service
│   │   └── scraper_service.py      # Orchestrator (Scraper -> Filter -> Excel)
│   │
│   ├── dashboard/                  # Web Backend
│   │   ├── router.py               # Single-page HTML router & REST API endpoints
│   │   └── websocket.py            # Real-time WebSocket connection manager
│   │
│   └── utils/                      # Utilities
│       ├── helpers.py              # URL builder & date parsers
│       └── logger.py               # Loguru logging configuration
│
├── templates/                      # HTML Interfaces
│   ├── base.html                   # Master layout
│   └── index.html                  # Single-page application interface
│
└── static/                         # Frontend Assets
    ├── css/custom.css              # Custom styling
    └── js/app.js                   # Single-page application JavaScript
```

---

## 🔄 Simple Data Flow

```
1. User enters Country, Role ("AI Developer"), and Pages
2. Click "Search Jobs" ──▶ POST /api/scraper/start
3. ScraperService starts IndeedScraper using Playwright Chromium
4. JobParser extracts raw JobPosting objects using BeautifulSoup
5. DateFilter & DedupFilter clean the results
6. Results rendered live on screen in HTML table & exported to outputs/Indeed_Job_Leads_YYYY-MM-DD.xlsx
```

# DIW Job Intelligence Scraper

> **Desire Infoweb Pvt. Ltd.** — Automated Microsoft-stack job lead generation
>
> Scrapes Indeed across 21 countries × 9 keyword clusters, scores leads with AI,
> and exports professional Excel reports — all controlled from a modern web dashboard.

> 📖 **New Developers & Employees:** Read [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) for a complete step-by-step code architecture walkthrough, file directory map, and extension instructions.

---

## Quick Start (5 Minutes)

### 1. Install Dependencies

```powershell
python -m pip install -r requirements.txt
playwright install chromium
```

### 2. Configure Environment

```powershell
copy .env.example .env
```

Edit `.env` and set your OpenAI API key:

```env
OPENAI_API_KEY=sk-your-key-here
```

### 3. Run the Application

```powershell
python main.py
```

Open your browser: **http://localhost:8000**

---

## Dashboard Pages

| Page | URL | Description |
|---|---|---|
| Dashboard | `/` | KPIs, charts, live status |
| Scraper | `/scraper` | Start/pause/stop with live log |
| Leads | `/leads` | Table with search/filter/sort |
| Configuration | `/configuration` | View all settings |
| Export | `/export` | One-click Excel download |

---

## How It Works

```
Indeed (Playwright + stealth)
    ↓
JobParser (BeautifulSoup4)
    ↓
DateFilter (last 24 hours only)
    ↓
DedupFilter (Indeed job ID + fingerprint)
    ↓
RelevanceFilter (DIW service keywords)
    ↓
AI Analyzer (OpenAI GPT-4o-mini)
    ↓ lead score + outreach email + reasoning
In-Memory State
    ├── Excel Export (outputs/DIW_Job_Leads_YYYY-MM-DD.xlsx)
    ├── Dashboard Display
    └── SharePoint (future — stub ready)
```

---

## Search Coverage

| Dimension | Count |
|---|---|
| Target Countries | 21 |
| Keyword Clusters | 9 |
| Max Combinations | 180 |
| Max Pages per Search | 3 (configurable) |
| Age Filter | Last 24 hours |

**Priority Countries** (searched first): US, GB, CA, AU, AE, DE, NL, ZA

**Keyword Clusters:**
1. SharePoint developer
2. Power Platform / Power Apps developer
3. Power BI developer
4. Dynamics 365 consultant
5. Microsoft 365 administrator
6. SPFx developer
7. Azure AI / Copilot Studio developer
8. RAG / AI chatbot developer
9. .NET developer Azure

---

## AI Analysis (Per Job)

Each qualified job receives:
- **Lead Score** (0–100) with dimensional breakdown
- **Matched DIW Services** from 12 service lines
- **AI Reasoning** — 2-3 sentence explanation
- **Outsourcing Opportunity** flag
- **Priority** (High/Medium/Low)
- **Personalized Outreach Email** from Yash Shah, DIW

---

## Excel Output

File: `outputs/DIW_Job_Leads_YYYY-MM-DD.xlsx`

**Sheet 1: DIW Leads**
- 23 columns including Job URL (hyperlinks), LinkedIn URL, AI Reasoning, Email
- Color-coded by priority (green=High, yellow=Medium, orange=Low)
- Frozen header, auto-filter, auto-width columns

**Sheet 2: Summary**
- Total leads, avg score, priority breakdown
- Leads by country + avg score
- Leads by DIW service

---

## Configuration

All settings live in `.env` — no code changes needed:

| Setting | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | — | **Required** |
| `AI_PROVIDER` | `openai` | `openai`, `groq` |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model name |
| `SCRAPER_HEADLESS` | `true` | Hidden browser |
| `SCRAPER_DELAY_MIN` | `2.0` | Min delay (s) |
| `SCRAPER_DELAY_MAX` | `5.0` | Max delay (s) |
| `SCRAPER_MAX_PAGES` | `3` | Pages per search |
| `FILTER_MAX_AGE_HOURS` | `24` | Job age window |
| `FILTER_MIN_LEAD_SCORE` | `20` | Score threshold |
| `DASHBOARD_PORT` | `8000` | Web UI port |
| `SCHEDULER_DAILY_TIME` | `08:00` | Daily auto-run |
| `SCHEDULER_TIMEZONE` | `Asia/Kolkata` | Timezone |

---

## SharePoint (Future)

The architecture is SharePoint-ready:

1. **Current**: `app/sharepoint/placeholder.py` — logs calls, no-op
2. **Future**: Implement `app/sharepoint/base.AbstractSharePointService`
3. **Data**: `AnalyzedJob.to_sharepoint_dict()` provides the flat field mapping
4. **Guide**: Full column schema and Graph API endpoints documented in `app/sharepoint/base.py`

No application redesign needed — just swap `NoOpSharePointService` for the real implementation.

---

## Project Structure

```
project/
├── app/
│   ├── config/          # Settings + business constants
│   ├── models/          # Pydantic data models
│   ├── scraper/         # Playwright Indeed scraper
│   ├── parser/          # BeautifulSoup4 HTML parser
│   ├── filters/         # Date, relevance, dedup filters
│   ├── ai/              # LLM analysis pipeline
│   ├── excel/           # openpyxl export
│   ├── sharepoint/      # Future SharePoint stub
│   ├── services/        # Orchestration + scheduler
│   ├── dashboard/       # FastAPI routes + WebSocket
│   └── utils/           # Logger + helpers
├── templates/           # Jinja2 HTML (dark theme)
├── static/              # CSS + JS
├── logs/                # Rotating log files
├── outputs/             # Generated Excel files
├── main.py              # Entry point
├── requirements.txt
└── .env.example
```

---

## Troubleshooting

| Issue | Fix |
|---|---|
| `playwright not found` | `playwright install chromium` |
| CAPTCHA / blocked | Set `SCRAPER_HEADLESS=false` to inspect, increase `SCRAPER_DELAY_MIN` |
| `OPENAI_API_KEY not configured` | Set key in `.env` |
| Port already in use | Change `DASHBOARD_PORT` in `.env` |
| Empty results | Indeed may have changed HTML — check `app/parser/job_parser.py` selectors |
| Rate limit error | Reduce `SCRAPER_MAX_PAGES` or increase delays |

---

## Technology Stack

| Component | Technology |
|---|---|
| Web Framework | FastAPI + Uvicorn |
| Frontend | Jinja2 + TailwindCSS + Chart.js |
| Scraping | Playwright (Chromium, headless) |
| Parsing | BeautifulSoup4 + lxml |
| AI Analysis | OpenAI GPT-4o-mini (configurable) |
| Excel | openpyxl |
| Scheduling | APScheduler |
| Logging | loguru |
| Config | pydantic-settings |
| Retry | tenacity |

---

*Built for Yash Shah · Desire Infoweb Pvt. Ltd. · Microsoft Partner since 2023*

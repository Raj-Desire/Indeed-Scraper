# Dice.com Lead Source Integration — Design

**Date:** 2026-09-21
**Status:** Approved for planning

## 1. Problem

The dashboard currently sources job leads only from Indeed (automated Playwright
scraper) or manual paste. The user wants a third source, Dice.com, that feeds
the same downstream pipeline: Azure AI Search knowledge-base retrieval → Azure
OpenAI LLM match scoring → SharePoint "Opportunity Tracker" export.

## 2. Research finding: no scraping needed

Dice operates an **official, public Model Context Protocol (MCP) server** at
`https://mcp.dice.com/mcp` (verified live via a raw JSON-RPC `initialize` and
`tools/list` call — see below). It requires **no authentication** and exposes:

- `search_jobs(keyword, location?, radius?, radius_unit?, jobs_per_page?, page_number?, sort?, posted_date?, workplace_types?, employment_types?, employer_types?, willing_to_sponsor?, easy_apply?, company_name?, fields?, facets?)` → paginated job list (title, company, location, salary, workplace type, `guid`, `detailsPageUrl`, `companyPageUrl`, ...)
- `get_job_details(job_id)` → full description + skills list, keyed by the result's `guid`
- `get_company(job_id)` → company name/description, keyed by the result's `guid`

Dice's own Terms of Service prohibit automated crawling/scraping of the site,
so this MCP server — not a Playwright scraper — is the only compliant way to
source Dice leads. It is also simpler to build: no browser automation,
selector maintenance, or anti-bot handling.

Verified server response (`tools/list` excerpt):
```
serverInfo: {"name": "Job Search MCP Server", "version": "1.0.0"}
tools: [search_jobs, get_job_details, get_company]
```

One functional requirement from Dice's tool spec: any UI presenting these
results must show an AI-search disclosure line to end users.

## 3. Scope decisions (confirmed with user)

- **Trigger:** manual search form only (keyword + filters, user clicks
  Search) — no automatic/scheduled Dice searches in this phase.
- **Scoring:** every search result is automatically run through KB matching +
  LLM scoring, same as the existing automated Indeed flow (no per-job opt-in).

## 4. Architecture

### 4.1 `app/scraper/dice_mcp_client.py` (new)
Async MCP JSON-RPC client over `httpx` (already a project dependency, used by
`graph_exporter.py`). No new heavy dependency (no browser, no `mcp` SDK
required — the protocol is plain JSON-RPC 2.0 over HTTP/SSE and small enough
to hand-roll with two methods).

- `DiceMCPClient.search_jobs(keyword, **filters) -> list[dict]` — calls the
  `search_jobs` tool, returns raw `JobDisplayFields` dicts.
- `DiceMCPClient.get_job_details(guid) -> dict` — calls `get_job_details` for
  full description + skills.
- Handles the JSON-RPC envelope (`initialize` handshake once per client
  lifetime, then `tools/call`), SSE response parsing, and basic error
  surfacing (network failure, malformed response, empty result).

### 4.2 Mapping into `JobPosting`
`app/scraper/dice_mcp_client.py` also exposes
`map_to_job_posting(raw: dict, details: dict, search_query: str) -> JobPosting`:

| Dice field | JobPosting field |
|---|---|
| `title` | `job_title` |
| `companyName` | `company` |
| `jobLocation.displayName` | `location` |
| `salary` | `salary_range` |
| `detailsPageUrl` | `job_url`, `apply_url` |
| `postedDate` | `posted_date_raw`, `posted_date` |
| `workplaceTypes` / `isRemote` | `remote_type` |
| `details.description` | `job_description` |
| `details.skills[].name` | folded into `job_description` context for the matcher (not a distinct model field) |
| (constant) | `search_query` = the keyword searched |
| (constant) | `lead_source` = `"Dice"` |

**Model change:** `app/models/job.py` gains
`lead_source: str = Field(default="Indeed", ...)` on `JobPosting`. This is new
— today lead source is implicit (always Indeed for scraped jobs; chosen
explicitly only in the manual-JD-paste flow's separate `Opportunity` mapping).
Adding it to `JobPosting` lets `DiceService` tag its results without touching
`RemoteType`-style enums.

**Export change:** `app/sharepoint/graph_exporter.py::export_jobs` currently
hardcodes `"LeadSource": "Indeed"` (line ~551). Change to read
`job.lead_source` per job, defaulting to `"Indeed"` — preserves current
behavior for the Indeed flow while letting Dice jobs export with the correct
value.

### 4.3 `app/services/dice_service.py` (new)
Bounded request/response service — deliberately simpler than
`ScraperService`, which manages a long-running cancellable Playwright session
(pause/resume/progress broadcast). A Dice search is one call/response cycle:

```python
class DiceService:
    async def search(self, keyword: str, filters: DiceSearchFilters) -> list[JobPosting]:
        # 1. DiceMCPClient.search_jobs(keyword, **filters)
        # 2. for each result: get_job_details(guid) -> map_to_job_posting(...)
        # 3. DedupFilter.filter(...)  (reuse existing filter, separate instance from Indeed's)
        # 4. for each job: MatchService.evaluate_job(job)  (reuse existing KB+LLM pipeline)
        # 5. store in self._results; return them
    def get_results(self) -> list[JobPosting]: ...
    def clear_results(self) -> None: ...
    async def export_sharepoint(self, selected_ids=None) -> int:
        # reuse GraphSharePointExporter.export_jobs unchanged
```

No Excel export requirement was stated for Dice; SharePoint export is the
target per the user's request, so `DiceService` will support SharePoint
export the same way `ScraperService.export_sharepoint` does. Excel export can
reuse `ExcelExporter` too if wanted later — not required for v1.

### 4.4 API routes (add to `app/dashboard/router.py`)
- `POST /api/dice/search` — body: keyword + filter fields → runs
  `DiceService.search`, returns matched/scored jobs (mirrors the manual-eval
  endpoint's response shape so the frontend can reuse rendering code).
- `GET /api/dice/results` — current in-memory results.
- `POST /api/dice/export/sharepoint` — export current/selected Dice results.
- `POST /api/dice/clear` — clear results.

### 4.5 Dashboard UI (`templates/index.html`)
Third tab button (`tab-btn-dice`) alongside `tab-btn-scraper` /
`tab-btn-manual`, wired through the existing `switchMode()` JS function. New
panel `panel-dice` (hidden by default, same pattern as `panel-manual`):

- Form: keyword (required), location, workplace type checkboxes (Remote/
  On-Site/Hybrid), employment type, posted-date recency, easy-apply and
  willing-to-sponsor toggles, "Search Dice" button.
- Results rendered with the same job-card component already used for
  Indeed/manual results (score badge, matched/missing skills, job summary,
  "Save to SharePoint" action) — reused, not rebuilt, by generalizing the
  existing render function to accept a source-agnostic job list.
- One-line AI-search disclosure shown above Dice results per Dice's MCP tool
  usage terms.

## 5. Error handling

- MCP server unreachable / non-200 / malformed JSON-RPC envelope → surfaced
  as a user-visible error banner in `panel-dice`, same toast/log mechanism
  `panel-scraper` already uses for scrape errors. No retry loop in v1 — a
  failed search is just re-triggerable by clicking Search again.
- `get_job_details` failing for an individual result → log and continue with
  the summary-only description already returned by `search_jobs`, rather than
  failing the whole search.
- Empty `search_jobs` result → render "No jobs found" in the panel, same as
  an empty Indeed run.

## 6. Testing

- Unit tests for `DiceMCPClient` (mock the HTTP layer) covering: successful
  `search_jobs` parse, `get_job_details` parse, network error, malformed
  response, empty results.
- Unit tests for `map_to_job_posting` covering field mapping and
  `remote_type`/`lead_source` derivation.
- Unit test for `DiceService.search` covering the full pipeline with
  `MatchService` mocked (assert dedup + scoring called per job).
- Existing `graph_exporter` tests extended to assert `lead_source` is read
  from the job rather than hardcoded.
- Manual/browser verification of the new dashboard tab (search → results →
  save to SharePoint) as part of implementation sign-off.

## 7. Out of scope (this phase)

- Scheduled/automatic Dice searches (may reuse `config/schedule.json`
  scheduler later if requested).
- Per-job opt-in scoring (cost control) — all results are scored
  automatically per the confirmed decision.
- `get_company` tool usage (company enrichment) — not required for the
  matching/scoring/export pipeline; can be added later if useful for
  outreach generation.

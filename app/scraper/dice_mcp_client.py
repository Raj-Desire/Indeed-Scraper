"""
Dice.com MCP Client
====================
Minimal JSON-RPC 2.0 client for Dice's official public Model Context Protocol
server (https://mcp.dice.com/mcp). No authentication is required. The server
uses the "streamable HTTP" MCP transport: each POST returns a single
Server-Sent-Events chunk containing one JSON-RPC response.

This hand-rolls the two calls this project needs (initialize handshake +
tools/call) instead of taking a dependency on a general-purpose MCP SDK,
since the protocol surface used here is small and static.
"""

from __future__ import annotations

import itertools
import json
from typing import Any, Optional

import httpx

from app.utils.logger import logger

DICE_MCP_URL = "https://mcp.dice.com/mcp"


class DiceMCPError(Exception):
    """Raised when the Dice MCP server is unreachable or returns an error."""


class DiceMCPClient:
    """Thin async client for Dice's public MCP server."""

    def __init__(self, base_url: str = DICE_MCP_URL, timeout: float = 30.0) -> None:
        self._base_url = base_url
        self._timeout = timeout
        self._id_counter = itertools.count(1)
        self._initialized = False

    async def _post(self, payload: dict) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(self._base_url, headers=headers, json=payload)

        if resp.status_code != 200:
            raise DiceMCPError(f"Dice MCP server returned HTTP {resp.status_code}: {resp.text[:300]}")

        return self._parse_sse(resp.text)

    @staticmethod
    def _parse_sse(text: str) -> dict:
        """Extract the JSON-RPC payload from an SSE-formatted response body."""
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                raw = line[len("data:"):].strip()
                try:
                    return json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise DiceMCPError(f"Malformed JSON-RPC payload from Dice MCP server: {exc}") from exc
        raise DiceMCPError("No 'data:' line found in Dice MCP server response")

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        payload = {
            "jsonrpc": "2.0",
            "id": next(self._id_counter),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "indeed-scraper-dashboard", "version": "1.0"},
            },
        }
        response = await self._post(payload)
        if "error" in response:
            raise DiceMCPError(f"Dice MCP initialize failed: {response['error']}")
        self._initialized = True

    async def _call_tool(self, tool_name: str, arguments: dict) -> dict:
        await self._ensure_initialized()
        payload = {
            "jsonrpc": "2.0",
            "id": next(self._id_counter),
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        response = await self._post(payload)
        if "error" in response:
            raise DiceMCPError(f"Dice MCP tool '{tool_name}' failed: {response['error']}")

        result = response.get("result", {})
        structured = result.get("structuredContent")
        if structured is None:
            raise DiceMCPError(f"Dice MCP tool '{tool_name}' returned no structuredContent")
        return structured

    async def search_jobs(self, *, keyword: str, **filters: Any) -> list[dict]:
        """Call the `search_jobs` tool. `filters` may include location, radius,
        radius_unit, jobs_per_page, page_number, sort, posted_date,
        workplace_types, employment_types, employer_types, willing_to_sponsor,
        easy_apply, company_name, fields, facets - any unset ones are omitted."""
        arguments = {"keyword": keyword, **{k: v for k, v in filters.items() if v is not None}}
        try:
            structured = await self._call_tool("search_jobs", arguments)
        except DiceMCPError:
            raise
        except Exception as exc:
            logger.error("Dice search_jobs failed for keyword '{}': {}", keyword, exc)
            raise DiceMCPError(str(exc)) from exc
        return structured.get("data") or []

    async def get_job_details(self, job_id: str) -> dict:
        """Call the `get_job_details` tool. Returns {"description": str, "skills": [...]}"""
        try:
            structured = await self._call_tool("get_job_details", {"job_id": job_id})
        except DiceMCPError:
            raise
        except Exception as exc:
            logger.error("Dice get_job_details failed for job_id '{}': {}", job_id, exc)
            raise DiceMCPError(str(exc)) from exc
        return {
            "description": structured.get("description") or "",
            "skills": structured.get("skills") or [],
        }

    async def close(self) -> None:
        """No persistent connection is held (a fresh httpx.AsyncClient is used per
        call), so this is a no-op kept for interface symmetry with other clients
        in this codebase (e.g. AzureSearchKnowledgeBase.close())."""
        return None


from app.config.constants import COMMON_COUNTRIES
from app.models.job import JobPosting, RemoteType
from datetime import datetime

_COUNTRY_NAME_TO_CODE: dict[str, str] = {c.name.upper(): c.code for c in COMMON_COUNTRIES}
_COUNTRY_NAME_TO_CODE.update({"USA": "US", "U.S.A.": "US", "U.S.": "US", "UK": "GB"})


def _parse_country(raw: dict) -> str:
    """Best-effort country code from Dice's `jobLocation.displayName` (typically
    "City, State/Region, Country"). Falls back to the model default "US" when
    the trailing segment isn't a recognized country name (e.g. "Remote", or no
    location at all) rather than guessing."""
    display_name = ((raw.get("jobLocation") or {}).get("displayName")) or ""
    if not display_name:
        return "US"
    last_segment = display_name.split(",")[-1].strip().upper()
    return _COUNTRY_NAME_TO_CODE.get(last_segment, "US")


def _parse_workplace_type(raw: dict) -> RemoteType:
    workplace_types = raw.get("workplaceTypes") or []
    lowered = [str(w).lower() for w in workplace_types]
    if any("remote" in w for w in lowered) or raw.get("isRemote") is True:
        return RemoteType.FULLY_REMOTE
    if any("hybrid" in w for w in lowered):
        return RemoteType.HYBRID
    if any("site" in w for w in lowered):
        return RemoteType.ON_SITE
    return RemoteType.UNKNOWN


def _parse_posted_date(raw_value: Optional[str]) -> Optional[datetime]:
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def map_to_job_posting(raw: dict, details: Optional[dict], search_query: str) -> JobPosting:
    """Map a raw Dice `search_jobs` result (+ optional `get_job_details` result)
    into a JobPosting tagged lead_source="Dice"."""
    location = ((raw.get("jobLocation") or {}).get("displayName")) or ""
    details = details or {}
    posted_raw = raw.get("postedDate") or ""

    return JobPosting(
        job_title=raw.get("title") or "Untitled Role",
        company=raw.get("companyName") or "",
        location=location,
        country=_parse_country(raw),
        search_query=search_query,
        remote_type=_parse_workplace_type(raw),
        salary_range=raw.get("salary") or "Not listed",
        posted_date_raw=posted_raw,
        posted_date=_parse_posted_date(posted_raw),
        job_url=raw.get("detailsPageUrl") or "",
        apply_url=raw.get("detailsPageUrl") or "",
        job_description=details.get("description") or "",
        has_full_description=bool(details.get("description")),
        lead_source="Dice",
    )

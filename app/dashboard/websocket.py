"""
WebSocket Manager
=================
Manages WebSocket connections for live scraper progress broadcasting.
Supports multiple simultaneous connected clients (e.g., multiple browser tabs).
"""

import asyncio
import json
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from app.utils.logger import logger


class WebSocketManager:
    """
    Manages a pool of active WebSocket connections.

    Broadcasts JSON messages to all connected clients simultaneously.
    Clients connect to /ws/progress and receive ScraperProgress updates.
    """

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self._connections.append(websocket)
        logger.debug("WebSocket connected. Active connections: {}", len(self._connections))

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a disconnected WebSocket from the pool."""
        if websocket in self._connections:
            self._connections.remove(websocket)
        logger.debug("WebSocket disconnected. Active connections: {}", len(self._connections))

    async def broadcast(self, data: dict[str, Any]) -> None:
        """
        Send a JSON message to all connected clients.
        Disconnected clients are silently removed from the pool.

        Args:
            data: Dictionary to serialize as JSON and send.
        """
        if not self._connections:
            return

        message = json.dumps(data, default=str)
        dead: list[WebSocket] = []

        for ws in self._connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self.disconnect(ws)

    async def send_progress(self, progress) -> None:
        """
        Broadcast a ScraperProgress object to all clients.

        Args:
            progress: ScraperProgress Pydantic model.
        """
        await self.broadcast(progress.model_dump())

    @property
    def connection_count(self) -> int:
        """Number of currently active WebSocket connections."""
        return len(self._connections)


# Singleton WebSocket manager
ws_manager = WebSocketManager()

"""WebSocket routes for real-time policy update notifications."""
import asyncio
from collections import deque
from datetime import datetime, timezone
from typing import List, Set, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from backend.config.settings import get_settings
from backend.config.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["WebSocket"])


class NotificationManager:
    """Manages system-wide notification WebSocket connections."""

    def __init__(self):
        self._connections: Set[WebSocket] = set()
        self._recent: deque = deque(maxlen=10)

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self._connections.add(websocket)
        logger.info("Notification client connected", total=len(self._connections))

    def disconnect(self, websocket: WebSocket):
        self._connections.discard(websocket)
        logger.info("Notification client disconnected", total=len(self._connections))

    async def broadcast_notification(self, notification: dict):
        """Broadcast a notification to all connected clients."""
        message = {
            **notification,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._recent.append(message)

        disconnected: Set[WebSocket] = set()
        for ws in self._connections:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.add(ws)

        for ws in disconnected:
            self._connections.discard(ws)

    @property
    def recent_notifications(self) -> List[dict]:
        return list(self._recent)


_notification_manager: Optional[NotificationManager] = None


def get_notification_manager() -> NotificationManager:
    """Get or create the global NotificationManager."""
    global _notification_manager
    if _notification_manager is None:
        _notification_manager = NotificationManager()
    return _notification_manager


@router.websocket("/ws/notifications")
async def websocket_notifications(
    websocket: WebSocket,
    token: Optional[str] = Query(default=None),
):
    """WebSocket endpoint for system-wide policy update notifications."""
    settings = get_settings()

    # In production, validate token
    if settings.app_env != "development" and not token:
        await websocket.close(code=4001, reason="Authentication required")
        return

    notif_mgr = get_notification_manager()
    await notif_mgr.connect(websocket)

    try:
        await websocket.send_json({
            "event": "connected",
            "scope": "notifications",
            "recent": notif_mgr.recent_notifications,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        while True:
            try:
                await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0,
                )
            except asyncio.TimeoutError:
                await websocket.send_json({
                    "event": "heartbeat",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

    except WebSocketDisconnect:
        notif_mgr.disconnect(websocket)
    except Exception as e:
        logger.error("Notifications WebSocket error", error=str(e))
        notif_mgr.disconnect(websocket)

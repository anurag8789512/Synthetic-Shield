"""
WebSocket connection manager for real-time updates.
- /ws/claims/{claim_id}: customer-side live status for one claim
- /ws/officer-feed: dashboard-wide broadcasts on every new claim/status change
"""
import json
from typing import Dict, Set
from fastapi import WebSocket


class WSManager:
    def __init__(self):
        # claim_id -> set of connected websockets
        self.claim_connections: Dict[int, Set[WebSocket]] = {}
        # All officer feed connections
        self.officer_connections: Set[WebSocket] = set()

    async def connect_claim(self, websocket: WebSocket, claim_id: int):
        await websocket.accept()
        if claim_id not in self.claim_connections:
            self.claim_connections[claim_id] = set()
        self.claim_connections[claim_id].add(websocket)

    def disconnect_claim(self, websocket: WebSocket, claim_id: int):
        if claim_id in self.claim_connections:
            self.claim_connections[claim_id].discard(websocket)

    async def connect_officer(self, websocket: WebSocket):
        await websocket.accept()
        self.officer_connections.add(websocket)

    def disconnect_officer(self, websocket: WebSocket):
        self.officer_connections.discard(websocket)

    async def broadcast_claim_update(self, claim_id: int, data: dict):
        """Notify all subscribers watching a specific claim."""
        msg = json.dumps(data)
        if claim_id in self.claim_connections:
            dead = set()
            for ws in self.claim_connections[claim_id]:
                try:
                    await ws.send_text(msg)
                except Exception:
                    dead.add(ws)
            for ws in dead:
                self.claim_connections[claim_id].discard(ws)

    async def broadcast_officer_feed(self, data: dict):
        """Notify all officer dashboard connections."""
        msg = json.dumps(data)
        dead = set()
        for ws in self.officer_connections:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.officer_connections.discard(ws)


ws_manager = WSManager()

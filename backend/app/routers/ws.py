"""WebSocket routes for real-time claim and officer feed updates."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.ws_manager import ws_manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/claims/{claim_id}")
async def ws_claim_status(websocket: WebSocket, claim_id: int):
    await ws_manager.connect_claim(websocket, claim_id)
    try:
        while True:
            await websocket.receive_text()  # Keep alive
    except WebSocketDisconnect:
        ws_manager.disconnect_claim(websocket, claim_id)


@router.websocket("/ws/officer-feed")
async def ws_officer_feed(websocket: WebSocket):
    await ws_manager.connect_officer(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect_officer(websocket)

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.logging_setup import logger
from app.services.session import session
from app.services.transcription import transcription

router = APIRouter()

# Track connected clients for broadcast
_clients: set[WebSocket] = set()


async def broadcast(msg: dict):
    dead = set()
    payload = json.dumps(msg)
    for ws in _clients:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.add(ws)
    _clients.difference_update(dead)


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _clients.add(ws)
    logger.info("WebSocket client connected (%d total)", len(_clients))

    try:
        while True:
            # Keep connection alive; client sends pings or commands
            data = await ws.receive_text()
            msg = json.loads(data)
            cmd = msg.get("cmd")

            if cmd == "start_listening":
                if transcription.is_running:
                    await ws.send_text(json.dumps({"type": "status", "text": "Already listening"}))
                    continue
                try:
                    loop = asyncio.get_running_loop()
                    queue = await transcription.start(loop)
                    await ws.send_text(json.dumps({"type": "status", "text": "Listening started"}))
                    # Spawn a task to drain the queue and broadcast
                    asyncio.create_task(_drain_queue(queue))
                except Exception as exc:
                    logger.error("Failed to start transcription: %s", exc)
                    await ws.send_text(json.dumps({
                        "type": "error",
                        "text": f"Could not start listening: {exc}",
                    }))

            elif cmd == "stop_listening":
                await transcription.stop()
                await ws.send_text(json.dumps({"type": "status", "text": "Listening stopped"}))

            elif cmd == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as exc:
        logger.error("WebSocket error: %s", exc)
    finally:
        _clients.discard(ws)


async def _drain_queue(queue: asyncio.Queue):
    """Read from the transcription queue and broadcast to all clients."""
    while transcription.is_running:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=0.5)
        except asyncio.TimeoutError:
            continue

        etype = event["type"]
        payload = event.get("payload")

        if etype == "partial":
            session.set_partial(payload)
            await broadcast({"type": "partial", "text": payload})

        elif etype == "final":
            session.set_partial("")
            session.add_utterance(payload)
            await broadcast({"type": "final", "text": payload})

        elif etype == "usage":
            await broadcast({"type": "usage", "usage": payload})

        elif etype == "error":
            await broadcast({"type": "error", "text": payload})

        elif etype == "stopped":
            await broadcast({"type": "status", "text": "Recognition stopped"})
            break

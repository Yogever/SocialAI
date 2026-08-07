"""The server: a socket, two read-only debug routes, and the browser's files.

This is the outermost layer, and it does as little as an outermost layer can. It
opens the party's doors, hands each arriving browser the truth so far, and passes
what they ask for down to the hub. Nothing here knows what a guest is.

Which mind the guests think with is a startup choice, not a code change:

    uvicorn backend.main:app --reload                    the real thing
    PARTY_MIND=scripted uvicorn backend.main:app         no model, no tokens

The real thing reads GOOGLE_API_KEY (see backend/mind/mind.py).
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from backend.hub import Hub
from backend.mind import Mind, ScriptedMind
from backend.party import Party

BROWSER_FILES = Path(__file__).resolve().parent.parent / "frontend"


def chosen_mind():
    return ScriptedMind(seed=42) if os.environ.get("PARTY_MIND") == "scripted" else Mind()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    hub.start()
    yield
    await hub.stop()


app = FastAPI(lifespan=lifespan)
hub = Hub(Party(mind=chosen_mind(), seed=42))


@app.websocket("/ws")
async def watch(socket: WebSocket) -> None:
    await socket.accept()
    hub.watchers.add(socket)
    # A snapshot straight away, so a fresh or reconnecting browser is completely
    # correct before the next frame rather than after it.
    await socket.send_json(hub.party.snapshot())
    try:
        while True:
            await hub.obey(await socket.receive_json())
    except WebSocketDisconnect:
        pass
    finally:
        hub.watchers.discard(socket)


# ---- looking inside --------------------------------------------------------
# Over HTTP rather than the socket on purpose. The socket carries world truth at
# thirty frames a second to everybody; this is introspection wanted twice a
# second by one person. Off the socket it costs the fast path nothing, and it can
# be read with curl and no browser at all.


@app.get("/debug/state")
async def internals(limit: int = 60, agent: str | None = None) -> dict:
    """Everything the panel needs in one document: the party's internals, plus a
    page of recent thoughts. Prompts and tracebacks are left out — they would
    dominate the payload. Ask for a single thought to see those."""
    return {
        **hub.party.internals(),
        "paused": hub.paused,
        "speed": hub.speed,
        "seconds_left": round(hub.left),
        "clients": len(hub.watchers),
        "thoughts": [thought.as_dict()
                     for thought in hub.party.log.recent(limit, agent)],
    }


@app.get("/debug/thought/{seq}")
async def one_thought(seq: int) -> dict:
    """One thought in full: the exact prompt it sent, and the traceback if it
    never came back."""
    thought = hub.party.log.get(seq)
    if thought is None:
        raise HTTPException(status_code=404, detail=f"no thought {seq} in the log")
    return thought.as_dict(full=True)


# Mounted last, so the socket and the debug routes win first.
app.mount("/", StaticFiles(directory=str(BROWSER_FILES), html=True), name="frontend")

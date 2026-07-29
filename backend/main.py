"""FastAPI app: transport + the two concurrent loops.

Responsibilities split (on purpose):
  - stub_sim.py owns *game logic* (pure-ish, no IO).
  - this file owns *IO*: the WebSocket, broadcasting snapshots/events, and the
    two async loops that drive the sim at their two different rhythms.

The two-loops model from docs/architecture.md, made real with asyncio:
  - movement loop  ~30Hz : cheap physics + broadcast full world_state snapshot
  - decision loop  ~1.5s : the (currently fake) "planner"; emits events

They run as independent asyncio tasks so a slow decision (later: an LLM call)
never freezes motion. Right now the stub decision is instant, but the structure
is what matters — it's the seam the real brain slots into.
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from backend.stub_sim import StubSim

MOVEMENT_HZ = 30
DECISION_PERIOD_S = 1.5

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: kick off the two loops; shutdown: cancel them cleanly.
    # `hub` is defined lower in the module — resolved when this runs, not now.
    hub.start()
    yield
    await hub.stop()


app = FastAPI(lifespan=lifespan)


class Hub:
    """Holds the single shared sim and the set of connected clients, and runs
    the two loops. One party, many spectators."""

    def __init__(self) -> None:
        self.sim = StubSim(seed=42)
        self.clients: set[WebSocket] = set()
        self.paused = False
        self.speed = 1  # sim fast-forward multiplier (1/2/3)
        self._tasks: list[asyncio.Task] = []

    async def broadcast(self, message: dict) -> None:
        dead = []
        for ws in self.clients:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    async def movement_loop(self) -> None:
        # broadcast at a real-time 30Hz; `speed` fast-forwards the *sim*, not the
        # wall clock, by advancing physics further per real frame.
        dt = 1.0 / MOVEMENT_HZ
        while True:
            if not self.paused:
                self.sim.movement_step(dt * self.speed)
                await self.broadcast(self.sim.snapshot())
            await asyncio.sleep(dt)

    async def decision_loop(self) -> None:
        while True:
            if not self.paused:
                for e in self.sim.decision_step():
                    await self.broadcast(e)
            # faster speed -> decisions fire more often
            await asyncio.sleep(DECISION_PERIOD_S / self.speed)

    def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self.movement_loop()),
            asyncio.create_task(self.decision_loop()),
        ]

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await t


hub = Hub()


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    hub.clients.add(ws)
    # send an immediate snapshot so a fresh/reconnecting client has full truth
    await ws.send_json(hub.sim.snapshot())
    try:
        while True:
            msg = await ws.receive_json()
            await handle_control(msg)
    except WebSocketDisconnect:
        pass
    finally:
        hub.clients.discard(ws)


async def handle_control(msg: dict) -> None:
    """Frontend -> backend control messages. The client sends *intent*, never
    world state."""
    mtype = msg.get("type")
    if mtype == "pause":
        hub.paused = True
    elif mtype == "resume":
        hub.paused = False
    elif mtype == "open_chat":
        hub.paused = True
        greeting = hub.sim.open_chat(msg.get("agent_id", ""))
        if greeting:
            await hub.broadcast(greeting)
    elif mtype == "close_chat":
        hub.paused = False
    elif mtype == "set_speed":
        hub.speed = max(1, min(3, int(msg.get("value", 1))))
    elif mtype == "user_message":
        reply = hub.sim.user_message(msg.get("agent_id", ""), msg.get("text", ""))
        if reply:
            await hub.broadcast(reply)


# Serve the frontend. Mounted last so /ws and any API routes win first.
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

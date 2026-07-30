"""FastAPI app: transport + the two concurrent loops.

Responsibilities split (on purpose):
  - sim.py owns *game logic* (the LLM planner + dispatcher; StubSim is the
    token-free stand-in with the same interface).
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

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from backend.sim import Sim

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
        self.sim = Sim(seed=42)
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

    async def step(self) -> None:
        """Advance one decision tick by hand, for the debug panel. Only meaningful
        while paused (both loops are then idle, so this is the sole driver).

        A step is one decision tick *plus* the movement that tick would have got.
        Decisions alone would be misleading: nobody would ever reach a target, so
        `_scan_arrivals` would never fire and repeated stepping would produce
        nothing but boredom triggers.

        It deliberately does NOT wait for the thoughts it spawns. Those are applied
        by the *next* tick, which is the dispatcher's real two-phase shape and what
        the panel shows (`in_flight` -> `applied`). Waiting here would also freeze
        the control channel: `ws_endpoint` handles one message at a time, so a step
        that blocked for a slow model would swallow the next pause/resume with it.
        """
        for e in self.sim.decision_step():
            await self.broadcast(e)
        dt = 1.0 / MOVEMENT_HZ
        for _ in range(round(DECISION_PERIOD_S * MOVEMENT_HZ)):
            self.sim.movement_step(dt)
        await self.broadcast(self.sim.snapshot())

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
    elif mtype == "step":
        # Debug supervision: only while paused, or it would double-advance the
        # sim behind the decision loop's back.
        if hub.paused:
            await hub.step()
    elif mtype == "user_message":
        reply = hub.sim.user_message(msg.get("agent_id", ""), msg.get("text", ""))
        if reply:
            await hub.broadcast(reply)


# --- debug introspection (read-only) --------------------------------------
# Deliberately HTTP, not the WebSocket: the wire contract in docs/architecture.md
# carries state (latest-wins) and events (append-only), and this is neither. Off
# the socket it costs the 30Hz path nothing, and it's curl-able without a browser.


def _debuggable_sim():
    """StubSim has no trace, and the sim is swappable — say so plainly."""
    if not hasattr(hub.sim, "debug_state"):
        raise HTTPException(status_code=501,
                            detail=f"{type(hub.sim).__name__} has no debug surface")
    return hub.sim


@app.get("/debug/state")
async def debug_state(limit: int = 60, agent: str | None = None) -> dict:
    """Everything the panel needs, in one latest-wins document: sim internals plus
    a page of recent thoughts. Prompts and tracebacks are omitted here (they'd
    dominate the payload) — fetch a single thought for those."""
    sim = _debuggable_sim()
    state = sim.debug_state()
    state["paused"] = hub.paused
    state["speed"] = hub.speed
    state["clients"] = len(hub.clients)
    state["thoughts"] = [r.to_dict() for r in sim.trace.recent(limit, agent)]
    return state


@app.get("/debug/thought/{seq}")
async def debug_thought(seq: int) -> dict:
    """One thought in full: the verbatim prompt that was sent, and the traceback
    if it failed."""
    sim = _debuggable_sim()
    rec = sim.trace.get(seq)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"no thought {seq} in the ring")
    return rec.to_dict(full=True)


# Serve the frontend. Mounted last so /ws and any API routes win first.
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

"""Shared simulation skeleton (Template Method pattern).

BaseSim owns everything that is *not* a decision: the world state, the physics
(movement + collision), the snapshot wire-format, and small geometry helpers.
The parts that invent choices or content — what an agent does next, what it says
— are left as holes (`decision_step`, `open_chat`, `user_message`) that raise
NotImplementedError. Subclasses fill those holes:

    StubSim  -> a fake state machine + canned dialogue (no LLM)
    Sim      -> the real, LLM-driven planner (holes still open for now)

So the base also serves as the interface contract main.py talks to: any sim it
holds is guaranteed to answer decision_step / open_chat / user_message.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

from backend.models import Agent

# World == the room the frontend draws, in display pixels (960 x 600).
ROOM_W = 960
ROOM_H = 600
AGENT_RADIUS = 16
ARRIVE_DIST = 6.0

# Standing spots that line up with the drawn furniture. (x, y, type)
WAYPOINTS = [
    (780, 360, "bar"),
    (90, 470, "couch"),
    (220, 470, "couch"),
    (140, 160, "window"),
    (480, 470, "snack"),
    (380, 260, "floor"),
    (560, 230, "floor"),
    (330, 330, "floor"),
    (620, 330, "floor"),
    (450, 220, "floor"),
]

# The guest list lives in a hand-authored file at the repo root.
AGENTS_FILE = Path(__file__).resolve().parent.parent / "agents.json"

# Sensible middle-of-the-road stats for an agent whose JSON leaves stats blank.
# Any stat the file *does* specify overrides its default (see _build_agent).
DEFAULT_STATS = {
    "drunkenness": 0,
    "confidence": 20,
    "fun": 10,
    "attractiveness": 60,
}


class BaseSim:
    def __init__(self, seed: int | None = None, agents_file: Path = AGENTS_FILE):
        self.rng = random.Random(seed)
        self.tick = 0
        self.agents: dict[str, Agent] = {}
        self._load_agents(agents_file)

    # ---- agent loading (shared: every sim gets its guests from the file) ----

    def _load_agents(self, path: Path) -> None:
        data = json.loads(path.read_text())
        for cfg in data["agents"]:
            agent = self._build_agent(cfg)
            self.agents[agent.id] = agent
        # Agents refer to each other by NAME in `approach` (the planner only ever
        # sees names, not ids), so names must resolve to exactly one guest. Match
        # the case-insensitive lookup the controller will use, and fail loudly here
        # rather than silently misroute an approach later.
        names = [a.name.strip().lower() for a in self.agents.values()]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise ValueError(f"agent names must be unique (case-insensitive); duplicates: {dupes}")

    def _build_agent(self, cfg: dict) -> Agent:
        """Hydrate one authored config row into a runtime-valid Agent.

        Authored values win; blank fields ("", [], {}, null / missing) fall back
        to a runtime default. Physics needs pos/target/stats to be real, so those
        are the ones the file is allowed to leave empty.
        """
        # Enter at the "door" (bottom-center) heading to a random floor spot, so
        # a planner-less agent still walks in and settles instead of freezing.
        x, y, t = self.rng.choice(WAYPOINTS[5:])
        pos = cfg["pos"] or [ROOM_W / 2 + self.rng.uniform(-20, 20), ROOM_H - 12]
        target = cfg["target"] or [float(x), float(y)]
        target_type = cfg["target_type"] or t

        return Agent(
            id=cfg["id"],
            name=cfg["name"],
            age=cfg["age"],
            pos=[float(pos[0]), float(pos[1])],
            target=[float(target[0]), float(target[1])],
            target_type=target_type,
            stats={**DEFAULT_STATS, **(cfg.get("stats") or {})},
            action=cfg.get("action") or "walking",
            conversation_id=cfg.get("conversation_id"),
            speed=cfg.get("speed") or 95.0,
            personality=cfg.get("personality", ""),
            goal=cfg.get("goal", ""),
        )

    # ---- state broadcast ---------------------------------------------------

    def snapshot(self) -> dict:
        return {
            "type": "world_state",
            "tick": self.tick,
            "agents": [a.snapshot() for a in self.agents.values()],
        }

    # ---- fast loop: physics only (never touches action/state) --------------

    def movement_step(self, dt: float) -> None:
        for a in self.agents.values():
            dx = a.target[0] - a.pos[0]
            dy = a.target[1] - a.pos[1]
            dist = math.hypot(dx, dy)
            if dist > ARRIVE_DIST:
                step = min(a.speed * dt, dist)
                a.pos[0] += dx / dist * step
                a.pos[1] += dy / dist * step
        self._resolve_collisions()

    def _resolve_collisions(self) -> None:
        """Backend owns collision. Talking pairs stand ~50px apart so the small
        separation radius leaves them alone; everyone else gets nudged apart."""
        agents = list(self.agents.values())
        min_dist = AGENT_RADIUS * 2
        for i in range(len(agents)):
            for j in range(i + 1, len(agents)):
                a, b = agents[i], agents[j]
                dx = b.pos[0] - a.pos[0]
                dy = b.pos[1] - a.pos[1]
                dist = math.hypot(dx, dy) or 0.01
                if dist < min_dist:
                    push = (min_dist - dist) / 2
                    nx, ny = dx / dist, dy / dist
                    a.pos[0] -= nx * push
                    a.pos[1] -= ny * push
                    b.pos[0] += nx * push
                    b.pos[1] += ny * push
        for a in self.agents.values():
            a.pos[0] = _clamp(a.pos[0], AGENT_RADIUS, ROOM_W - AGENT_RADIUS)
            a.pos[1] = _clamp(a.pos[1], AGENT_RADIUS, ROOM_H - AGENT_RADIUS)

    # ---- geometry helpers (reusable movement primitives, not decisions) ----

    def _reached(self, a: Agent) -> bool:
        return math.hypot(a.target[0] - a.pos[0], a.target[1] - a.pos[1]) <= ARRIVE_DIST

    def _send_to_waypoint(self, a: Agent) -> None:
        x, y, t = self.rng.choice(WAYPOINTS)
        a.target = [float(x), float(y)]
        a.target_type = t
        a.action = "walking"

    # ---- the holes: the "brain" surface subclasses must fill ---------------

    def decision_step(self) -> list[dict]:
        """Slow loop: advance the planner one tick, return events to broadcast."""
        raise NotImplementedError

    def open_chat(self, agent_id: str) -> dict | None:
        """User clicked an agent: return its greeting event (or None)."""
        raise NotImplementedError

    def user_message(self, agent_id: str, text: str) -> dict | None:
        """User said something to an agent: return its reply event (or None)."""
        raise NotImplementedError


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

"""Stub simulation.

A *fake* party sim — no LLM, no real brains. Its job is to speak the real wire
contract (docs/architecture.md) so the frontend is built against something that
behaves like the eventual backend.

The conversation/clustering logic here was ported from the Claude Design mockup,
which originally ran it *in the browser*. It lives in the backend now because
that's the whole point of the architecture: conversation forming/ending is
simulation state, and simulation state is authoritative here, not in the UI.

Two rhythms, still split:
  - movement_step(dt) : pure physics. Advance positions toward targets, resolve
                        collisions. Never changes an agent's *action* / state.
  - decision_step()   : the "planner" (fake). The state machine: pick targets,
                        drink, form/maintain/end conversations, emit events.
                        This is where the LLM eventually goes.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

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

_NAMES = ["Dana", "Sam", "Priya", "Jordan", "Marcus", "Elena", "Theo", "Naomi", "Kai", "Rosa"]
_AGES = [24, 29, 26, 31, 27, 23, 33, 28, 25, 30]

_CLUSTER_LINES = [
    "That's hilarious.", "No way, really?", "I needed this drink.",
    "This song is so good.", "Wait, tell me more.", "I'm having a great time.",
    "Same, honestly.", "Who put this playlist together?",
    "This party is wild tonight.", "Okay but hear me out...",
]
_OPENING_LINES = [
    "Hey! Great party, right?", "Oh, hi there. Having fun?",
    "Didn't expect to talk to you tonight.", "Hey! You made it.",
    "This party's pretty good so far.",
]
_REPLY_NORMAL = ["Yeah, totally.", "Ha, fair point.", "I'm just here for the snacks, honestly.",
                 "Same here.", "Tell me about it."]
_REPLY_TIPSY = ["Wooo, yeah!! Love that.", "Okay honestly? Best party ever.",
                "Wait what were we talking about.", "I love everyone here right now."]
_REPLY_SHY = ["Oh, um, yeah I guess.", "Sorry, I'm not great at parties.",
              "That's... nice.", "I've kind of been standing here a while."]


@dataclass
class Agent:
    id: str
    name: str
    age: int
    pos: list[float]
    target: list[float]
    target_type: str
    stats: dict[str, float]
    action: str = "walking"        # walking | idle | drinking | talking
    conversation_id: str | None = None
    speed: float = 95.0            # pixels / second

    def snapshot(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "age": self.age,
            "pos": [round(self.pos[0], 1), round(self.pos[1], 1)],
            "stats": {k: round(v) for k, v in self.stats.items()},
            "action": self.action,
            "conversation_id": self.conversation_id,
        }


class StubSim:
    def __init__(self, n_agents: int = 10, seed: int | None = None):
        self.rng = random.Random(seed)
        self.tick = 0
        self.agents: dict[str, Agent] = {}
        self.clusters: dict[str, dict] = {}
        self._cid_seq = 0
        self._next_arrival = 0
        self._n_target = min(n_agents, len(_NAMES))

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

    # ---- slow loop: the state machine (fake "planner") ---------------------

    def decision_step(self) -> list[dict]:
        self.tick += 1
        events: list[dict] = []

        if len(self.agents) < self._n_target:
            events.append(self._spawn_agent())

        for a in self.agents.values():
            if a.action == "talking":
                continue  # driven by cluster logic below
            if a.action == "drinking":
                a.stats["drunkenness"] = min(100, a.stats["drunkenness"] + 8)
                if self.rng.random() < 0.35:
                    self._send_to_waypoint(a)
                continue
            # not talking/drinking: act on arrival
            if self._reached(a):
                if a.target_type == "bar":
                    a.action = "drinking"
                    events.append({"type": "agent_drank", "tick": self.tick,
                                   "agent_id": a.id, "name": a.name})
                elif self.rng.random() < 0.55:
                    self._send_to_waypoint(a)
                else:
                    a.action = "idle"

        events += self._form_clusters()
        events += self._update_clusters()
        return events

    def _reached(self, a: Agent) -> bool:
        return math.hypot(a.target[0] - a.pos[0], a.target[1] - a.pos[1]) <= ARRIVE_DIST

    def _send_to_waypoint(self, a: Agent) -> None:
        x, y, t = self.rng.choice(WAYPOINTS)
        a.target = [float(x), float(y)]
        a.target_type = t
        a.action = "walking"

    def _form_clusters(self) -> list[dict]:
        events: list[dict] = []
        free = [a for a in self.agents.values()
                if a.conversation_id is None and a.action in ("walking", "idle")]
        for a in free:
            if a.conversation_id is not None:
                continue
            if self.rng.random() > 0.15:
                continue
            partner = next(
                (b for b in free
                 if b.id != a.id and b.conversation_id is None
                 and math.hypot(b.pos[0] - a.pos[0], b.pos[1] - a.pos[1]) < 170),
                None,
            )
            if not partner:
                continue
            cid = f"c{self._cid_seq}"
            self._cid_seq += 1
            cx = (a.pos[0] + partner.pos[0]) / 2
            cy = (a.pos[1] + partner.pos[1]) / 2
            for who, off in ((a, -25), (partner, 25)):
                who.action = "talking"
                who.conversation_id = cid
                who.target = [cx + off, cy]
                who.target_type = "floor"
            self.clusters[cid] = {
                "members": [a.id, partner.id],
                "duration": self.rng.randint(4, 8),
            }
            events.append({
                "type": "conversation_started", "tick": self.tick,
                "conversation_id": cid,
                "participants": [a.id, partner.id],
                "names": [a.name, partner.name],
            })
        return events

    def _update_clusters(self) -> list[dict]:
        events: list[dict] = []
        for cid, cl in list(self.clusters.items()):
            cl["duration"] -= 1
            members = [self.agents[i] for i in cl["members"] if i in self.agents]
            if cl["duration"] > 0:
                if members and self.rng.random() < 0.5:
                    speaker = self.rng.choice(members)
                    events.append({
                        "type": "agent_spoke", "tick": self.tick,
                        "agent_id": speaker.id, "conversation_id": cid,
                        "text": self.rng.choice(_CLUSTER_LINES),
                    })
                continue
            # conversation over: neutral-or-better bumps fun, everyone disperses
            for m in members:
                m.action = "walking"
                m.conversation_id = None
                m.stats["fun"] = _clamp(m.stats["fun"] + 6, -100, 100)
                self._send_to_waypoint(m)
            del self.clusters[cid]
            events.append({
                "type": "conversation_ended", "tick": self.tick,
                "conversation_id": cid,
                "participants": [m.id for m in members],
                "names": [m.name for m in members],
            })
        return events

    def _spawn_agent(self) -> dict:
        i = self._next_arrival
        self._next_arrival += 1
        aid = f"a{i}"
        x, y, t = self.rng.choice(WAYPOINTS[5:])  # enter heading to a floor spot
        agent = Agent(
            id=aid,
            name=_NAMES[i],
            age=_AGES[i],
            pos=[ROOM_W / 2 + self.rng.uniform(-20, 20), ROOM_H - 12],
            target=[float(x), float(y)],
            target_type=t,
            stats={
                "drunkenness": self.rng.randint(0, 30),
                "confidence": self.rng.randint(-70, 70),
                "fun": self.rng.randint(-30, 70),
                "attractiveness": self.rng.randint(40, 95),
            },
            action="walking",
        )
        self.agents[aid] = agent
        return {"type": "agent_arrived", "tick": self.tick, "agent_id": aid, "name": agent.name}

    # ---- control (frontend -> backend) ------------------------------------

    def open_chat(self, agent_id: str) -> dict | None:
        """The agent greets the user. conversation_id is None so the frontend
        routes it to the chat panel, not an in-world cluster bubble."""
        a = self.agents.get(agent_id)
        if not a:
            return None
        return {"type": "agent_spoke", "tick": self.tick, "agent_id": agent_id,
                "conversation_id": None, "text": self.rng.choice(_OPENING_LINES)}

    def user_message(self, agent_id: str, text: str) -> dict | None:
        a = self.agents.get(agent_id)
        if not a:
            return None
        if a.stats["drunkenness"] > 60:
            reply = self.rng.choice(_REPLY_TIPSY)
        elif a.stats["confidence"] < -20:
            reply = self.rng.choice(_REPLY_SHY)
        else:
            reply = self.rng.choice(_REPLY_NORMAL)
        return {"type": "agent_spoke", "tick": self.tick, "agent_id": agent_id,
                "conversation_id": None, "text": reply}


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

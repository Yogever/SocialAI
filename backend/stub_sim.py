"""Stub simulation.

A *fake* party sim — no LLM, no real brains. Its job is to speak the real wire
contract (docs/architecture.md) so the frontend is built against something that
behaves like the eventual backend.

Physics, snapshotting and the world constants live in BaseSim; this file only
holds the *decisions*: the fake state machine (pick targets, drink, form/end
conversations) and the canned dialogue. That's the seam the real LLM planner
replaces — see Sim in sim.py.
"""

from __future__ import annotations

import math

from backend.base_sim import BaseSim, _clamp

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


class StubSim(BaseSim):
    def __init__(self, seed: int | None = None):
        super().__init__(seed)
        self.clusters: dict[str, dict] = {}
        self._cid_seq = 0

    # ---- slow loop: the state machine (fake "planner") ---------------------

    def decision_step(self) -> list[dict]:
        self.tick += 1
        events: list[dict] = []

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

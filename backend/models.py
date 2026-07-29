"""Domain data models for the party sim.

Pure data — no IO, no game logic. Lives apart from the sim so both the stub sim
and the real (LLM-driven) sim import the *same* Agent shape instead of each
defining their own and drifting.
"""

from __future__ import annotations

from dataclasses import dataclass


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
    personality: str = ""          # free-text trait; fuels the real planner later
    goal: str = ""                 # static intent, sometimes blank; identity tier (D10)

    def snapshot(self) -> dict:
        # personality is intentionally omitted: it's a static trait, and this
        # dict is broadcast to clients ~30x/sec — no need to ship it every frame.
        return {
            "id": self.id,
            "name": self.name,
            "age": self.age,
            "pos": [round(self.pos[0], 1), round(self.pos[1], 1)],
            "stats": {k: round(v) for k, v in self.stats.items()},
            "action": self.action,
            "conversation_id": self.conversation_id,
        }

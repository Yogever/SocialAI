"""A guest at the party.

Three things make up a guest, and they are separate because they change at
completely different rates:

    Identity   fixed for the night — a name, an age, a personality, a goal
    Feelings   move a few points when something happens
    Body       moves thirty times a second

plus what they've been told just happened (their inbox) and the handful of things
they still have in mind (their memory).

Everything above this file talks to the Guest and never to the three parts. That
is the whole point of the split: the party says "walk to the bar", the guest says
"head for this spot", the body does arithmetic — and nothing above the guest has
ever needed to know that a position is a pair of floats.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

from backend.room import ARRIVED, PERSONAL_SPACE, Spot
from backend.trigger import News, Trigger

# How much one drink moves the needle.
DRINK = 8

# How far apart two people stand to have a conversation. Wider than PERSONAL_SPACE
# so the room's crowd-control leaves a talking pair exactly where they were put.
CHATTING_DISTANCE = 50.0

# How many things a guest carries forward. Deliberately few: this is what they'd
# still have in mind, not a transcript of the evening.
MEMORY = 8

# The range each feeling lives in. Nothing that happens at the party can push one
# off its own scale, whatever the mind decides it felt.
RANGES = {
    "drunkenness": (0, 100),
    "confidence": (-100, 100),
    "fun": (-100, 100),
}


@dataclass(frozen=True)
class Identity:
    """Who a guest is. None of it changes once the party starts."""

    id: str
    name: str
    age: int
    personality: str
    goal: str
    # How others read you across a room. It sits here rather than with the
    # feelings because it isn't one: it never changes, and it is the one trait a
    # guest can't perceive about themselves, only about everybody else.
    attractiveness: float = 60.0

    def as_told(self) -> dict:
        """The version a mind is given of itself. Attractiveness is left out on
        purpose — nobody deliberates about their own."""
        return {
            "name": self.name,
            "age": self.age,
            "personality": self.personality,
            "goal": self.goal,
        }


class Feelings:
    """How a guest feels right now."""

    def __init__(self, **values: float) -> None:
        self.values = {name: _clamp(values.get(name, 0), *span)
                       for name, span in RANGES.items()}

    def shift(self, name: str, amount: float) -> None:
        low, high = RANGES.get(name, (-100, 100))
        self.values[name] = _clamp(self.values.get(name, 0) + amount, low, high)

    def absorb(self, deltas) -> None:
        """Take on what a thought decided this guest just felt."""
        for delta in deltas:
            self.shift(delta.stat, delta.delta)

    def as_dict(self) -> dict:
        return {name: round(value) for name, value in self.values.items()}


class Body:
    """Where a guest is and where they're walking. It knows nothing about why."""

    def __init__(self, pos, target, destination: str, speed: float) -> None:
        self.pos = [float(pos[0]), float(pos[1])]
        self.target = [float(target[0]), float(target[1])]
        # The *kind* of place the target is — the semantic half of "where I'm going".
        self.destination = destination
        self.speed = speed

    @property
    def has_arrived(self) -> bool:
        return self.distance_to_target <= ARRIVED

    @property
    def distance_to_target(self) -> float:
        return math.hypot(self.target[0] - self.pos[0], self.target[1] - self.pos[1])

    def walk(self, dt: float) -> None:
        gap = self.distance_to_target
        if gap <= ARRIVED:
            return
        step = min(self.speed * dt, gap)
        self.pos[0] += (self.target[0] - self.pos[0]) / gap * step
        self.pos[1] += (self.target[1] - self.pos[1]) / gap * step

    def head_for(self, spot: Spot) -> None:
        self.target = [spot.x, spot.y]
        self.destination = spot.kind

    def head_towards(self, other: Body) -> None:
        """Aim at a person rather than a place. Called again every tick while
        walking over, because people move and a stale target is a miss."""
        self.target = list(other.pos)
        self.destination = other.destination

    def stand_at(self, x: float, y: float) -> None:
        self.target = [x, y]
        self.destination = "floor"

    def stop(self) -> None:
        self.target = list(self.pos)

    def distance_to(self, other: Body) -> float:
        return math.hypot(other.pos[0] - self.pos[0], other.pos[1] - self.pos[1])

    def is_beside(self, other: Body) -> bool:
        """Close enough to talk. Not the same as having arrived: crowd control
        holds two people PERSONAL_SPACE apart, so nobody can ever reach the exact
        pixel somebody else is standing on."""
        return self.distance_to(other) <= CHATTING_DISTANCE

    def midpoint_with(self, other: Body) -> tuple[float, float]:
        return ((self.pos[0] + other.pos[0]) / 2, (self.pos[1] + other.pos[1]) / 2)

    def push_apart_from(self, other: Body) -> None:
        """If we've ended up standing in each other, both step back by half the
        overlap — neither has more right to the floor than the other."""
        gap = self.distance_to(other) or 0.01
        if gap >= PERSONAL_SPACE:
            return
        step = (PERSONAL_SPACE - gap) / 2
        away = ((other.pos[0] - self.pos[0]) / gap, (other.pos[1] - self.pos[1]) / gap)
        for axis in (0, 1):
            self.pos[axis] -= away[axis] * step
            other.pos[axis] += away[axis] * step

    def stay_inside(self, width: float, height: float) -> None:
        margin = PERSONAL_SPACE / 2
        self.pos[0] = _clamp(self.pos[0], margin, width - margin)
        self.pos[1] = _clamp(self.pos[1], margin, height - margin)


class Memory:
    """The handful of things a guest still has in mind, oldest first."""

    def __init__(self, keep: int = MEMORY) -> None:
        self.lines: deque[str] = deque(maxlen=keep)

    def add(self, line: str) -> None:
        self.lines.append(line)

    def as_list(self) -> list[str]:
        return list(self.lines)


class Guest:
    def __init__(self, identity: Identity, feelings: Feelings, body: Body,
                 doing: str = "walking") -> None:
        self.identity = identity
        self.feelings = feelings
        self.body = body
        self.memory = Memory()
        self.inbox: list[Trigger] = []
        self.conversation_id: str | None = None
        # What they're up to, as the browser draws it. The wire also allows
        # "drinking", which nothing here currently produces.
        self.doing = doing
        self.last_thought_tick = 0
        # Set off for a drink and not had it yet. An intention, so it can't be
        # derived from where they're standing — plenty of people stand at a bar
        # without wanting anything.
        self.wants_a_drink = False

    # ---- who they are ----------------------------------------------------

    @property
    def id(self) -> str:
        return self.identity.id

    @property
    def name(self) -> str:
        return self.identity.name

    # ---- how they are ----------------------------------------------------

    def feel(self, deltas) -> None:
        self.feelings.absorb(deltas)

    def drink(self) -> None:
        """Have the drink they came for. The errand ends here — one decision to
        get a drink buys exactly one drink."""
        self.feelings.shift("drunkenness", DRINK)
        self.wants_a_drink = False

    # ---- where they are --------------------------------------------------

    @property
    def destination(self) -> str:
        return self.body.destination

    @property
    def is_free(self) -> bool:
        return self.conversation_id is None

    @property
    def is_idle(self) -> bool:
        return self.doing == "idle"

    @property
    def just_got_somewhere(self) -> bool:
        """Was walking, and now isn't going anywhere. The moment worth reacting to
        — being *at* the bar is only interesting on the tick you got there."""
        return self.doing == "walking" and self.body.has_arrived

    def is_standing_at(self, kind: str) -> bool:
        """At a kind of place, rather than on the way to one."""
        return self.is_idle and self.destination == kind

    def walk(self, dt: float) -> None:
        self.body.walk(dt)

    def walk_to(self, spot: Spot) -> None:
        """Set off for a spot — unless that spot is where they already are, which
        is not a journey and so is not something anyone can arrive from. Deciding
        to go where you already stand leaves you standing there."""
        self.body.head_for(spot)
        self.doing = "idle" if self.body.has_arrived else "walking"

    def set_off_for_a_drink(self, bar: Spot) -> None:
        """Go to the bar meaning to have one. Whether that is a walk across the
        room or no walk at all, the drink is owed either way."""
        self.wants_a_drink = True
        self.walk_to(bar)

    def walk_over_to(self, other: Guest) -> None:
        self.body.head_towards(other.body)
        self.doing = "walking"

    def stay_put(self) -> None:
        """Stop where you are. The body keeps walking toward its target whatever
        the guest thinks it's doing, so standing still means moving the target."""
        self.body.stop()
        self.doing = "idle"

    def stand_facing(self, other: Guest) -> None:
        """Settle into a conversation: both step to arm's length either side of
        the point halfway between where each of them was."""
        middle_x, middle_y = self.body.midpoint_with(other.body)
        half = CHATTING_DISTANCE / 2
        self.body.stand_at(middle_x - half, middle_y)
        other.body.stand_at(middle_x + half, middle_y)
        self.doing = other.doing = "talking"

    def is_beside(self, other: Guest) -> bool:
        return self.body.is_beside(other.body)

    def make_room_for(self, other: Guest) -> None:
        self.body.push_apart_from(other.body)

    def stay_inside(self, width: float, height: float) -> None:
        self.body.stay_inside(width, height)

    # ---- what they've been told -----------------------------------------

    def notice(self, trigger: Trigger) -> None:
        self.inbox.append(trigger)

    @property
    def has_news(self) -> bool:
        return bool(self.inbox)

    def take_news(self) -> News:
        """Take the newest thing that happened, and drop the rest unread."""
        latest = self.inbox[-1]
        missed = [older.kind for older in self.inbox[:-1]]
        self.inbox.clear()
        return News(latest, missed)

    def remember(self, line: str) -> None:
        self.memory.add(line)

    def thought_at(self, tick: int) -> None:
        self.last_thought_tick = tick

    # ---- how they look ---------------------------------------------------

    def snapshot(self) -> dict:
        """What the browser draws thirty times a second. Personality and goal are
        left out: they never change, so shipping them every frame is waste."""
        return {
            "id": self.id,
            "name": self.name,
            "age": self.identity.age,
            "pos": [round(self.body.pos[0], 1), round(self.body.pos[1], 1)],
            "stats": self.as_stats(),
            "action": self.doing,
            "conversation_id": self.conversation_id,
        }

    def as_stats(self) -> dict:
        """Everything the tooltip shows as a bar. Attractiveness lives with the
        identity but reads as a stat, so it is put back together here."""
        return {**self.feelings.as_dict(),
                "attractiveness": round(self.identity.attractiveness)}

    def as_others_see(self) -> dict:
        """What you'd clock about this person from across the room.

        Their private feelings are deliberately absent: you infer someone's mood
        from how they're behaving, you don't read their confidence off a number.
        That inference is where a personality gets to make a difference.
        """
        return {
            "name": self.name,
            "location": self.destination,
            "action": self.doing,
            "available": self.is_free,
            "attractiveness": round(self.identity.attractiveness),
        }

    def as_debug(self) -> dict:
        """Everything the snapshot deliberately doesn't carry — the static, the
        private and the intended."""
        return {
            "id": self.id,
            "name": self.name,
            "age": self.identity.age,
            "personality": self.identity.personality,
            "goal": self.identity.goal,
            "action": self.doing,
            "pos": [round(self.body.pos[0], 1), round(self.body.pos[1], 1)],
            "target": [round(self.body.target[0], 1), round(self.body.target[1], 1)],
            "target_type": self.destination,
            "stats": self.as_stats(),
            "conversation_id": self.conversation_id,
            "inbox": [pending.kind for pending in self.inbox],
            "memory": self.memory.as_list(),
        }


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))

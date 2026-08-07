"""Everyone at the party, and where they came from.

The guest list is authored by hand in agents.json at the repo root, so this file
is also where authored data becomes something the party can run: blanks get
filled in, and the one rule the whole rest of the system leans on is checked
before anything starts.

That rule is that a name points at exactly one person. Guests refer to each other
by name and only by name — it is the only thing they perceive of one another —
so two guests called Sam would make "approach Sam" ambiguous at the exact moment
somebody is walking across a room. Better to refuse to start.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from backend.guest import Body, Feelings, Guest, Identity
from backend.room import Room

GUEST_FILE = Path(__file__).resolve().parent.parent / "agents.json"

# Middle-of-the-road values for a guest whose entry leaves them blank. Anything
# the file does specify wins.
DEFAULTS = {"drunkenness": 0, "confidence": 20, "fun": 10, "attractiveness": 60}
WALKING_SPEED = 95.0        # pixels per second


class GuestList:
    def __init__(self, guests: list[Guest]) -> None:
        self.guests = {guest.id: guest for guest in guests}
        _refuse_duplicate_names(guests)

    @classmethod
    def load(cls, room: Room, path: Path = GUEST_FILE) -> GuestList:
        authored = json.loads(path.read_text())["agents"]
        return cls([_arrive(entry, room) for entry in authored])

    def __iter__(self) -> Iterator[Guest]:
        return iter(self.guests.values())

    def get(self, guest_id: str) -> Guest | None:
        return self.guests.get(guest_id)

    def named(self, name: str) -> Guest | None:
        """Look someone up the way a guest would: by the name they'd say out loud,
        without caring how it was capitalised."""
        wanted = name.strip().lower()
        return next((guest for guest in self
                     if guest.name.strip().lower() == wanted), None)

    def other_than(self, guest: Guest) -> list[Guest]:
        return [other for other in self if other is not guest]


def _arrive(entry: dict, room: Room) -> Guest:
    """Turn one authored entry into a guest standing in the room.

    Authored values win; blanks ("", [], null, missing) become something the
    physics can actually use. Position, target and stats are the fields the file
    is allowed to leave empty, because they're the ones nobody wants to author.
    """
    heading_for = room.somewhere("floor")
    stats = {**DEFAULTS, **(entry.get("stats") or {})}

    identity = Identity(
        id=entry["id"],
        name=entry["name"],
        age=entry["age"],
        personality=entry.get("personality", ""),
        goal=entry.get("goal", ""),
        attractiveness=stats["attractiveness"],
    )
    body = Body(
        pos=entry.get("pos") or room.doorway,
        target=entry.get("target") or (heading_for.x, heading_for.y),
        destination=entry.get("target_type") or heading_for.kind,
        speed=entry.get("speed") or WALKING_SPEED,
    )
    guest = Guest(
        identity=identity,
        feelings=Feelings(**stats),
        body=body,
        doing=entry.get("action") or "walking",
    )
    guest.conversation_id = entry.get("conversation_id")
    return guest


def _refuse_duplicate_names(guests: list[Guest]) -> None:
    names = [guest.name.strip().lower() for guest in guests]
    duplicates = {name for name in names if names.count(name) > 1}
    if duplicates:
        raise ValueError(
            f"guest names must be unique (case-insensitive); duplicates: {duplicates}"
        )

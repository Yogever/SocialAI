"""The room the party happens in: the places people stand, and how bodies fit.

This is the only file that thinks in pixels. Everything above it decides in terms
of "the bar" or "the couch"; turning that into somewhere to actually stand is the
room's job, and it is the room that decides two guests can't occupy one square
foot of floor.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

# The room as the browser draws it, in display pixels.
WIDTH = 960
HEIGHT = 600

PERSONAL_SPACE = 32     # closer than this and two guests are standing in each other
ARRIVED = 6.0           # this close to where you were heading counts as being there


@dataclass(frozen=True)
class Spot:
    """Somewhere a guest can stand, named by what it is rather than where it is.

    `kind` is the half a guest reasons about ("I'll go to the bar"); the
    coordinates are the half only the room and the bodies care about.
    """

    x: float
    y: float
    kind: str


# Standing spots that line up with the furniture drawn in the browser. Several
# are plain "floor" so mingling has somewhere to happen that isn't a landmark.
SPOTS = [
    Spot(780, 360, "bar"),
    Spot(90, 470, "couch"),
    Spot(220, 470, "couch"),
    Spot(140, 160, "window"),
    Spot(480, 470, "snack"),
    Spot(380, 260, "floor"),
    Spot(560, 230, "floor"),
    Spot(330, 330, "floor"),
    Spot(620, 330, "floor"),
    Spot(450, 220, "floor"),
]

# The kinds a guest is allowed to name. The mind is told this list, and the
# decision schema is built from it, so the two can't drift apart.
KINDS = ("bar", "couch", "window", "snack", "floor")


class Room:
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.spots = SPOTS

    def somewhere(self, kind: str) -> Spot:
        """A place of the requested kind to go and stand.

        Which one doesn't matter — a guest who decides "the couch" has no opinion
        about which end of it — so the room picks, and the choice being arbitrary
        is what keeps the party from lining everyone up on the same pixel.
        """
        matching = [spot for spot in self.spots if spot.kind == kind]
        return self.rng.choice(matching or self.spots)

    def anywhere(self) -> Spot:
        return self.rng.choice(self.spots)

    @property
    def doorway(self) -> tuple[float, float]:
        """Where guests come in: the bottom edge, roughly centred, jittered so
        arrivals don't stack up on one point."""
        return WIDTH / 2 + self.rng.uniform(-20, 20), HEIGHT - 12

    def keep_clear(self, guests) -> None:
        """Nobody stands inside anybody else, and nobody stands through a wall.

        Guests in a conversation are placed further apart than PERSONAL_SPACE, so
        this leaves talking pairs exactly where the conversation put them.
        """
        crowd = list(guests)
        for i, guest in enumerate(crowd):
            for other in crowd[i + 1:]:
                guest.make_room_for(other)
        for guest in crowd:
            guest.stay_inside(WIDTH, HEIGHT)

"""What a mind is told.

A situation is everything one guest knows at one moment, and nothing they don't.
It is plain values copied out of the party when the thought starts, never live
references, for two reasons: a thought runs concurrently with the party moving on
without it, and the debug panel renders the prompt long after the fact — both
need the world exactly as it was when the guest looked at it.

The three tiers below are ordered by how often they change: the rules are the
same for everyone forever, an identity is the same for one guest all night, and
the rest changes every single call. That order is also the order a model caches
in, so the cheapest arrangement and the most readable one are the same one.

Guests perceive semantically. `where` is "the bar", never a coordinate; other
guests are described by what you'd clock across a room, never by their private
feelings. Reading someone's mood off their behaviour, rather than off their
numbers, is where personality gets to matter.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from backend.trigger import Trigger

# The world explained to the model: the mechanics, and only the mechanics. We
# describe the party — the spots, the scales, the menu of verbs — and trust its
# pretrained understanding of people for everything else. Nothing in here tells a
# guest how to feel; that is what a personality is for.
RULES = """\
You are a single guest at a house party, deciding what to do next AS this specific \
person. Act as they genuinely would: their personality, goal, and how they currently \
feel drive every choice. Do not narrate an omniscient view — you only know what this \
person can see.

The party is one room. The spots you can move to are: bar, couch, window, snack, floor.

Each turn you output three things:

- reasoning: think first, in this person's own head. One sentence, no more.

- deltas: how this person's feelings just changed, a list of {stat, delta, reason}.
    Scales:  drunkenness 0..100   confidence -100..100   fun -100..100
    Each delta is bounded to -15..+15 — a single moment can only move a feeling so \
much. Include only stats that actually changed; every delta needs a short reason.

- action: exactly one of
    go_to(spot)                  move to a spot to mingle or settle
    go_drink                     head to the bar and have a drink
    approach(target_name, opener)  walk over to someone (by their name, as shown in
                                   the room) and open with a line (they may decline)
    reply_in_conversation(text)  say your next turn in a conversation you're in
    leave_conversation           end the conversation you're in
    idle                         stay put
"""

# Asked of a mind when the person watching the party is the one talking. Same
# guest, same knowledge — a different shape of answer.
CHAT_INSTRUCTION = (
    "Reply as this person would, out loud, in one or two sentences. "
    "Say only the words they would say — no narration, no quotation marks."
)


@dataclass(frozen=True)
class Situation:
    """One guest's view of one moment."""

    identity: dict           # who they are; the same every time they think
    feelings: dict           # how they feel right now
    where: str               # the kind of place they're standing, semantically
    room: list[dict]         # everyone else, as they appear from across the room
    because: Trigger         # the thing that happened, and why they're thinking
    memory: list[str] = field(default_factory=list)
    # Only present mid-conversation, so its absence is itself the signal that
    # they aren't talking to anybody.
    transcript: list[str] | None = None

    @property
    def just_happened(self) -> str:
        """The event in the guest's own second person — the one sentence of this
        whole situation that is *news*."""
        return self.because.describe()

    def as_messages(self) -> list[tuple[str, str]]:
        """The exact prompt for this situation. Pure, so it can be read, asserted
        and re-rendered later without spending a token or touching the network."""
        return [
            ("system", f"{RULES}\n\n<you>\n{_as_json(self.identity)}\n</you>"),
            ("human", _as_json(self.moment)),
        ]

    def as_chat_messages(self) -> list[tuple[str, str]]:
        """The same knowledge, asked for a line of dialogue instead of a decision."""
        system, human = self.as_messages()
        return [system, ("human", f"{human[1]}\n\n{CHAT_INSTRUCTION}")]

    @property
    def moment(self) -> dict:
        """The volatile half, as one document. Derived rather than stored so it
        can't disagree with the fields it's made of."""
        moment = {
            "stats": self.feelings,
            "location": self.where,
            "room": self.room,
            "just_happened": self.just_happened,
            "memory": self.memory,
        }
        if self.transcript is not None:
            moment["transcript"] = self.transcript
        return moment


def _as_json(payload: dict) -> str:
    # A structured skeleton with prose inside the values: the model reads the
    # shape at a glance and the content in its own language. `ensure_ascii=False`
    # so names and dialogue stay legible to us too.
    return json.dumps(payload, ensure_ascii=False)

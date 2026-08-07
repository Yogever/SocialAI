"""Two guests talking, and the awkward moment before they are.

There is no conversation loop anywhere in this project, and that is the design.
A conversation is a small pile of state plus a handful of handlers: when a guest
takes their turn, their partner is handed the line as something that happened to
them, which makes the partner think, which produces the next turn. The ping-pong
*is* two guests triggering each other. The only loop in the whole system is the
party's tick.

Approaching somebody is a handshake rather than an order. You commit, you walk
over, you say your line — and only then does the other person get to decide
whether they're interested. Between setting off and being answered you are in
limbo: committed, but talking to nobody. That limbo is an Approach, and it is the
single most confusing state in the sim, which is why the debug panel has a name
for every phase of it.
"""

from __future__ import annotations

from typing import Iterator

from backend import event
from backend.guest import Guest
from backend.room import Room
from backend.trigger import ApproachDeclined, ConversationEnded, PartnerSpoke, WasApproached

# A conversation nobody ends is a conversation that runs forever, and every turn
# costs a model call. This is the fuse, not the intended ending.
TURN_CAP = 10


class Conversation:
    """Two guests taking turns."""

    def __init__(self, id: str, between: tuple[Guest, Guest], transcript: list[str],
                 cap: int = TURN_CAP) -> None:
        self.id = id
        self.between = between
        self.transcript = transcript        # "Name: line", in the order said
        self.turns = 0
        self.cap = cap
        self.speaker: Guest = between[0]    # whose turn it is right now

    @property
    def is_exhausted(self) -> bool:
        return self.turns >= self.cap

    def partner_of(self, guest: Guest) -> Guest:
        first, second = self.between
        return second if guest is first else first

    def said(self, guest: Guest, line: str) -> None:
        self.transcript.append(f"{guest.name}: {line}")
        self.turns += 1

    def as_debug(self) -> dict:
        return {
            "id": self.id,
            "participants": [guest.id for guest in self.between],
            "names": [guest.name for guest in self.between],
            "turn_count": self.turns,
            "cap": self.cap,
            "speaker": self.speaker.id,
            "speaker_name": self.speaker.name,
            "transcript": list(self.transcript),
        }


class Approach:
    """One guest crossing the room with an opening line ready."""

    def __init__(self, by: Guest, to: Guest, opener: str) -> None:
        self.by = by
        self.to = to
        self.opener = opener
        self.delivered = False      # False: still walking. True: line said, awaiting judgement.


class Conversations:
    """Every conversation happening, and every approach still in the air.

    Approaches are filed under the person being approached, so somebody can only
    be walked up to once at a time — a second approacher racing the first bounces
    off rather than both arriving at once.
    """

    def __init__(self, room: Room) -> None:
        self.room = room
        self.live: dict[str, Conversation] = {}
        self.approaches: dict[str, Approach] = {}
        self._ids = 0

    def __iter__(self) -> Iterator[Conversation]:
        return iter(self.live.values())

    # ---- who is doing what ----------------------------------------------

    def of(self, guest: Guest) -> Conversation | None:
        return self.live.get(guest.conversation_id or "")

    def can_pair_up(self, one: Guest, other: Guest) -> bool:
        """Whether these two could start something, right now.

        Both have to be completely unattached, and the case worth spelling out is
        two people setting off at each other: both would arrive, both would owe
        the other an answer, and both would say yes — leaving two conversations
        where there should have been one, and an orphaned one nobody can end.
        """
        return one is not other and self.unattached(one) and self.unattached(other)

    def unattached(self, guest: Guest) -> bool:
        """Not talking to anyone, not being walked up to, and not already walking
        over to somebody."""
        return (guest.is_free
                and guest.id not in self.approaches
                and self.crossing_the_room(guest) is None)

    def crossing_the_room(self, guest: Guest) -> Approach | None:
        """The approach this guest is making, if they're making one. They look
        idle to everything else, so anything that reacts to idleness has to ask."""
        return next((approach for approach in self.approaches.values()
                     if approach.by is guest), None)

    def awaiting_answer_from(self, guest: Guest) -> Approach | None:
        """An approach that has been delivered to this guest and not yet judged.
        While one exists, this guest's next thought *is* the answer to it."""
        approach = self.approaches.get(guest.id)
        return approach if approach is not None and approach.delivered else None

    # ---- the handshake ---------------------------------------------------

    def expect(self, approach: Approach) -> None:
        self.approaches[approach.to.id] = approach
        approach.by.walk_over_to(approach.to)

    def deliver_openers(self) -> None:
        """Anyone who has walked far enough says their line, and then waits.

        "Far enough" is standing-next-to, not pixel-exact: crowd control holds two
        guests apart, so the walker can never reach the spot the target occupies.
        The target may also have wandered off in the meantime, so the walker
        re-aims every tick.
        """
        for approach in list(self.approaches.values()):
            if approach.delivered:
                continue
            approach.by.walk_over_to(approach.to)
            if approach.by.is_beside(approach.to):
                approach.delivered = True
                approach.by.stay_put()          # nothing to do but wait to be judged
                approach.to.notice(WasApproached(approach.by.name, approach.opener))

    def accept(self, approach: Approach, reply: str) -> list[dict]:
        """The opener landed. Two lines are already on the table, so the
        conversation starts mid-flow, with the approacher owing the next turn."""
        self.approaches.pop(approach.to.id, None)
        approacher, target = approach.by, approach.to
        conversation = self._open(approacher, target, [
            f"{approacher.name}: {approach.opener}",
            f"{target.name}: {reply}",
        ])
        conversation.speaker = approacher
        approacher.notice(PartnerSpoke(target.name, reply))
        return [
            event.conversation_started(conversation),
            event.spoke(approacher, approach.opener, conversation.id),
            event.spoke(target, reply, conversation.id),
        ]

    def rebuff(self, approach: Approach) -> list[dict]:
        """The opener didn't land. The approacher un-parks and is told, so they
        get to have a feeling about it."""
        self.approaches.pop(approach.to.id, None)
        approach.by.stay_put()
        approach.by.notice(ApproachDeclined(approach.to.name))
        return []

    # ---- taking turns ----------------------------------------------------

    def speak(self, guest: Guest, text: str) -> list[dict]:
        """A guest takes their turn, and hands their partner something to react
        to. That handoff is what makes the next turn happen."""
        conversation = self.of(guest)
        if conversation is None:            # a reply with nowhere to go
            return []
        conversation.said(guest, text)
        spoken = [event.spoke(guest, text, conversation.id)]
        if conversation.is_exhausted:
            return spoken + self.wind_down(conversation)
        partner = conversation.partner_of(guest)
        conversation.speaker = partner # switch turns
        partner.notice(PartnerSpoke(guest.name, text))
        return spoken

    def leave(self, guest: Guest) -> list[dict]:
        conversation = self.of(guest)
        if conversation is None:
            return []
        return self._close(conversation, walked_out_on=conversation.partner_of(guest),
                           by_name=guest.name)

    def wind_down(self, conversation: Conversation) -> list[dict]:
        """Out of turns. Nobody chose this, so both are told the same thing."""
        return self._close(conversation, walked_out_on=None, by_name=None)

    # ---- private ---------------------------------------------------------

    def _open(self, first: Guest, second: Guest, transcript: list[str]) -> Conversation:
        self._ids += 1
        conversation = Conversation(f"c{self._ids}", (first, second), transcript)
        self.live[conversation.id] = conversation
        first.conversation_id = second.conversation_id = conversation.id
        first.stand_facing(second)
        return conversation

    def _close(self, conversation: Conversation, *, walked_out_on: Guest | None,
               by_name: str | None) -> list[dict]:
        """Both sides stop talking on the same tick and drift off. Whoever didn't
        choose it is told, because being left is a thing that happens *to* you."""
        self.live.pop(conversation.id, None)
        ending = event.conversation_ended(conversation)
        for guest in conversation.between:
            guest.conversation_id = None
            guest.walk_to(self.room.anywhere())
        if walked_out_on is not None:
            walked_out_on.notice(ConversationEnded(who=by_name))
        else:
            for guest in conversation.between:
                guest.notice(ConversationEnded(who=None))
        return [ending]

    # ---- what it looks like from outside ---------------------------------

    def involvement_of(self, guest: Guest) -> dict | None:
        """This guest's side of an approach, in words. A guest parked mid-approach
        is `idle` like anybody else, so on the party screen they are
        indistinguishable from someone genuinely doing nothing."""
        being_approached = self.approaches.get(guest.id)
        if being_approached is not None:
            return {
                "role": "target",
                "who": being_approached.by.name,
                "opener": being_approached.opener,
                "state": "owes_consent" if being_approached.delivered else "incoming",
            }
        approaching = self.crossing_the_room(guest)
        if approaching is not None:
            return {
                "role": "approacher",
                "who": approaching.to.name,
                "opener": approaching.opener,
                "state": "awaiting_consent" if approaching.delivered else "walking_over",
            }
        return None

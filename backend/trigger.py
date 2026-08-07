"""The things that happen to a guest, and make them think.

A guest never thinks because a timer said so — they think because something
happened. That something is a trigger, and there are exactly eight of them: they
walked in, they got where they were going, someone walked up to them, their
partner said something, an approach fell through or was brushed off, a
conversation ended, or they have been standing about long enough to go looking
for something to do. (The user walking up to a guest is a ninth; it lands in the
chat panel rather than in a thought, but it is the same kind of thing.)

Each trigger knows how to say itself in the second person, because the sentence
the guest reads *is* the trigger — there is no separate table mapping kinds to
prose that can fall out of step with the kinds themselves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar


@dataclass(frozen=True)
class Trigger:
    """Something that happened to one guest."""

    # Short label the debug panel groups by. Set by each kind of trigger below.
    kind: ClassVar[str] = "something"

    def describe(self) -> str:
        """The event as the guest experiences it — this exact sentence is what
        the mind is handed as `just_happened`."""
        return "Something happened."


@dataclass(frozen=True)
class WalkedIn(Trigger):
    kind: ClassVar[str] = "entry"

    def describe(self) -> str:
        return "You just walked into the party."


@dataclass(frozen=True)
class Arrived(Trigger):
    kind: ClassVar[str] = "arrived"
    spot: str = "floor"

    def describe(self) -> str:
        return f"You arrived at the {self.spot}."


@dataclass(frozen=True)
class WasApproached(Trigger):
    kind: ClassVar[str] = "was_approached"
    who: str = "someone"
    opener: str = ""

    def describe(self) -> str:
        return f'{self.who} walked over to you and said: "{self.opener}"'


@dataclass(frozen=True)
class PartnerSpoke(Trigger):
    kind: ClassVar[str] = "partner_spoke"
    who: str = "they"
    said: str = ""

    def describe(self) -> str:
        return f'{self.who} said: "{self.said}"'


@dataclass(frozen=True)
class ApproachDeclined(Trigger):
    kind: ClassVar[str] = "approach_declined"
    who: str = "they"

    def describe(self) -> str:
        return f"{self.who} brushed off your approach and didn't engage."


@dataclass(frozen=True)
class ApproachFailed(Trigger):
    kind: ClassVar[str] = "approach_failed"

    def describe(self) -> str:
        return "You went to talk to someone, but they weren't available."


@dataclass(frozen=True)
class ConversationEnded(Trigger):
    kind: ClassVar[str] = "conversation_ended"
    # Who walked off, or None when it simply ran out of steam.
    who: str | None = None

    def describe(self) -> str:
        if self.who is None:
            return "Your conversation wound down naturally."
        return f"{self.who} ended the conversation and walked off."


@dataclass(frozen=True)
class Bored(Trigger):
    kind: ClassVar[str] = "boredom"

    def describe(self) -> str:
        return "You've been standing around a while; nothing much is happening."


@dataclass(frozen=True)
class UserWalkedUp(Trigger):
    """The person watching the party clicked this guest. Not a reason to re-plan
    — the party is paused — but the mind still needs to be told what happened."""

    kind: ClassVar[str] = "user_walked_up"

    def describe(self) -> str:
        return "Someone at the party has come over to talk to you."


@dataclass(frozen=True)
class UserSaid(Trigger):
    kind: ClassVar[str] = "user_said"
    said: str = ""

    def describe(self) -> str:
        return f'They said to you: "{self.said}"'


@dataclass(frozen=True)
class News:
    """What a guest is reacting to, and what it displaced.

    A guest reacts to the newest thing that happened, not to a backlog — being
    approached three seconds ago stops mattering once the person gave up. So the
    older triggers are dropped unread, and `missed` keeps their names, because
    "why did it ignore that?" is otherwise unanswerable.
    """

    latest: Trigger
    missed: list[str] = field(default_factory=list)

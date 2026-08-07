"""The party: one evening, one room, a handful of guests, and what they make of it.

Everything the simulation is lives here or one level below. Above it, nothing
knows a guest from a conversation — the server just runs the party's two rhythms
and posts the results to whoever is watching.

The two rhythms are the shape of the whole design:

    move()      thirty times a second. Bodies advance. Nobody thinks.
    decide()    every second and a half. Whoever has something to react to,
                reacts to it.

They are separate because thinking is slow and walking must not be. A guest whose
thought is still with the model keeps walking to wherever their last thought sent
them, and the party keeps going without them.

`decide()` is a tick, not a loop, and it never awaits. Thoughts are started here
and collected here, but they happen elsewhere and in parallel; every change to
the world happens inside this one method, which runs start to finish without
yielding. That is why nothing in this file has to think about two things
happening at once.
"""

from __future__ import annotations

import random

from backend import event
from backend.conversation import Approach, Conversations, TURN_CAP
from backend.guest import MEMORY, Guest
from backend.guest_list import GuestList
from backend.mind import Decision, Situation
from backend.mind.decision import Action, GoDrink, GoTo, Idle, Leave, Reply
# The verb and the thing it sets in motion are both "an approach"; only here do
# they meet, so only here does one of them need a longer name.
from backend.mind.decision import Approach as ApproachSomeone
from backend.room import Room
from backend.thinking import AT_ONCE, Thinking
from backend.thought_log import ThoughtLog
from backend.trigger import (
    ApproachFailed,
    Arrived,
    Bored,
    UserSaid,
    UserWalkedUp,
    WalkedIn,
)

# How long a guest will stand about before going to look for something to do.
# The safety net, not the intended source of behaviour: everything else that
# makes a guest think is something that actually happened to them.
BOREDOM = 8


class Party:
    def __init__(self, mind, seed: int | None = None) -> None:
        self.rng = random.Random(seed)
        self.room = Room(self.rng)
        self.guests = GuestList.load(self.room)
        self.conversations = Conversations(self.room)
        self.mind = mind
        self.log = ThoughtLog()
        self.thinking = Thinking(mind, self.log)
        self.tick = 0
        # Guests who had something to react to and lost the race for a model call.
        self.crowded_out: list[str] = []
        self.failures = 0
        # Everybody walks in with nothing decided yet, which is itself a thing to
        # think about — otherwise nobody would ever have a first thought.
        for guest in self.guests:
            guest.notice(WalkedIn())

    # ==================================================================
    #  THE TWO RHYTHMS
    # ==================================================================

    def move(self, dt: float) -> None:
        """The fast rhythm. Bodies advance toward wherever they were last sent,
        and the room stops anyone standing inside anyone else."""
        for guest in self.guests:
            guest.walk(dt)
        self.room.keep_clear(self.guests)

    def decide(self) -> list[dict]:
        """The slow rhythm: finished thoughts change the world, the world hands
        guests new things to react to, and whoever has something starts thinking."""
        self.tick += 1
        happened = self.carry_out_finished_thoughts()
        happened += self.clear_up_after_failures()
        happened += self.notice_what_the_world_did()
        self.start_thinking()
        return [{**one, "tick": self.tick} for one in happened]

    # ==================================================================
    #  CARRYING OUT A THOUGHT
    # ==================================================================

    def carry_out_finished_thoughts(self) -> list[dict]:
        happened = []
        for guest, decision, thought in self.thinking.finished():
            guest.thought_at(self.tick)
            happened += self.carry_out(guest, decision, thought)
        return happened

    def carry_out(self, guest: Guest, decision: Decision, thought) -> list[dict]:
        """A thought becomes real. The guest feels what they felt and remembers
        what they chose — and then either answers the person standing in front of
        them, or gets on with it."""
        before = guest.feelings.as_dict()
        guest.feel(decision.deltas)
        guest.remember(decision.action.remembered())

        owed = self.conversations.awaiting_answer_from(guest)
        thought.applied(self.tick, before, guest.feelings.as_dict(),
                        answered_an_approach=owed is not None)
        if owed is not None:
            return self.answer(guest, owed, decision.action)
        return self.perform(guest, decision.action)

    def answer(self, guest: Guest, approach: Approach, action: Action) -> list[dict]:
        """Somebody walked over with a line, so this whole thought is the reply to
        it. Saying something back means yes; anything else means no — and they
        still get to do the thing they'd rather be doing."""
        if isinstance(action, Reply):
            return self.conversations.accept(approach, action.text)
        return self.conversations.rebuff(approach) + self.perform(guest, action)

    def perform(self, guest: Guest, action: Action) -> list[dict]:
        """One chosen verb, one change to the world."""
        match action:
            case GoTo():
                guest.walk_to(self.room.somewhere(action.spot))
            case GoDrink():
                guest.set_off_for_a_drink(self.room.somewhere("bar"))
            case Idle():
                guest.stay_put()
            case ApproachSomeone():
                return self.set_off_towards(guest, action.target_name, action.opener)
            case Reply():
                return self.conversations.speak(guest, action.text)
            case Leave():
                return self.conversations.leave(guest)
        return []

    def set_off_towards(self, guest: Guest, name: str, opener: str) -> list[dict]:
        """Commit to walking across the room to somebody. If either of them is
        already tangled up with someone else, don't — and say so, or the guest
        stands there having decided something that will never resolve."""
        target = self.guests.named(name)
        if target is None or not self.conversations.can_pair_up(guest, target):
            guest.notice(ApproachFailed())
            return []
        self.conversations.expect(Approach(by=guest, to=target, opener=opener))
        return []

    def clear_up_after_failures(self) -> list[dict]:
        """A thought that raised must not leave its guest frozen, or their partner
        waiting on a turn that will never come."""
        happened = []
        for guest in self.thinking.failed():
            self.failures += 1
            guest.thought_at(self.tick)
            if self.conversations.of(guest) is not None:
                happened += self.conversations.leave(guest)
            else:
                guest.stay_put()
        return happened

    # ==================================================================
    #  WHAT HAPPENS WITHOUT ANYBODY DECIDING IT
    # ==================================================================

    def notice_what_the_world_did(self) -> list[dict]:
        """Three things happen to a guest that nobody chose: they get where they
        were going, somebody arrives in front of them, and time passes."""
        self.conversations.deliver_openers()
        self.notice_arrivals()
        happened = self.serve_drinks()
        self.notice_boredom()
        return happened

    def notice_arrivals(self) -> None:
        """Getting somewhere is worth reacting to."""
        for guest in self.guests:
            if not guest.just_got_somewhere:
                continue
            if self.conversations.crossing_the_room(guest):
                continue        # they're mid-approach; arriving is that handshake's business
            arrived_at = guest.destination
            guest.stay_put()
            guest.notice(Arrived(arrived_at))

    def serve_drinks(self) -> list[dict]:
        """Everyone who came to the bar for a drink and has got there gets one.

        Standing at the bar is not enough and neither is arriving at it — a guest
        drinks because they decided to, which is why this asks what they wanted
        rather than where they are. Runs after arrivals so that the walk across
        the room and the drink at the end of it land on the same tick.
        """
        happened = []
        for guest in self.guests:
            if guest.wants_a_drink and guest.is_standing_at("bar"):
                guest.drink()
                happened.append(event.drank(guest))
        return happened

    def notice_boredom(self) -> None:
        for guest in self.guests:
            if self.is_at_a_loose_end(guest):
                guest.notice(Bored())

    def is_at_a_loose_end(self, guest: Guest) -> bool:
        """Standing about with nothing to react to, no thought in flight and no
        approach in progress, for long enough that a real person would go and
        find something to do."""
        return (guest.is_idle
                and not guest.has_news
                and not self.thinking.busy_with(guest)
                and self.conversations.crossing_the_room(guest) is None
                and self.ticks_since_thinking(guest) >= BOREDOM)

    def ticks_since_thinking(self, guest: Guest) -> int:
        return self.tick - guest.last_thought_tick

    # ==================================================================
    #  STARTING THOUGHTS
    # ==================================================================

    def start_thinking(self) -> None:
        """Everyone with something to react to starts thinking about it — as many
        at once as we're willing to pay for, and no more."""
        self.crowded_out = []
        for guest in self.guests:
            if not guest.has_news or self.thinking.busy_with(guest):
                continue
            if self.thinking.at_capacity:
                self.crowded_out = [waiting.id for waiting in self.guests
                                    if waiting.has_news
                                    and not self.thinking.busy_with(waiting)]
                return
            news = guest.take_news()
            guest.remember(news.latest.describe())
            self.thinking.begin(guest, self.situation_for(guest, news.latest),
                                news, self.tick)

    def situation_for(self, guest: Guest, because) -> Situation:
        """Everything this guest knows right now, and nothing they don't.

        Built from copies, because the thought that reads it runs while the party
        carries on around it — and because the debug panel renders this prompt
        long after the moment has passed.
        """
        conversation = self.conversations.of(guest)
        return Situation(
            identity=guest.identity.as_told(),
            feelings=guest.feelings.as_dict(),
            where=guest.destination,
            room=[other.as_others_see() for other in self.guests.other_than(guest)],
            because=because,
            memory=guest.memory.as_list(),
            transcript=list(conversation.transcript) if conversation else None,
        )

    # ==================================================================
    #  THE PERSON WATCHING
    # ==================================================================
    #  Someone clicking a guest is not a trigger: the party is paused, nothing
    #  else is happening, and the answer is wanted right now rather than on the
    #  next tick. So this path awaits the mind directly instead of going through
    #  the dispatcher, and produces a line rather than a decision.

    async def greet(self, guest_id: str) -> dict | None:
        return await self._say_something(guest_id, UserWalkedUp())

    async def hear(self, guest_id: str, said: str) -> dict | None:
        return await self._say_something(guest_id, UserSaid(said))

    async def _say_something(self, guest_id: str, because) -> dict | None:
        guest = self.guests.get(guest_id)
        if guest is None:
            return None
        try:
            line = await self.mind.small_talk(self.situation_for(guest, because))
        except Exception:
            return None         # the drawer stays open and empty; the party is fine
        guest.remember(because.describe())
        guest.remember(f'You said: "{line}"')
        # No conversation id: this belongs in the chat drawer, not in a bubble
        # over the room.
        return {**event.spoke(guest, line, None), "tick": self.tick}

    # ==================================================================
    #  BEING WATCHED
    # ==================================================================

    def snapshot(self) -> dict:
        """The whole truth, latest-wins, thirty times a second."""
        return {
            "type": "world_state",
            "tick": self.tick,
            "agents": [guest.snapshot() for guest in self.guests],
        }

    def internals(self) -> dict:
        """One document with everything the debug panel needs: all the state that
        exists but never reaches a snapshot, because it is static, private, or
        internal to the dispatcher. Pure reads — nothing here steers the party."""
        return {
            "tick": self.tick,
            "thinking": self.thinking.thinkers,
            "starved": list(self.crowded_out),
            "failures": self.failures,
            "knobs": {
                "max_concurrent": AT_ONCE,
                "boredom_ticks": BOREDOM,
                "conv_cap": TURN_CAP,
                "memory_n": MEMORY,
            },
            "agents": [self.inspect(guest) for guest in self.guests],
            "conversations": [conversation.as_debug()
                              for conversation in self.conversations],
        }

    def inspect(self, guest: Guest) -> dict:
        """One guest, as the panel shows them: what they are, plus the three
        things only the party knows about them."""
        return {
            **guest.as_debug(),
            "thinking": self.thinking.busy_with(guest),
            "ticks_until_boredom": max(0, BOREDOM - self.ticks_since_thinking(guest)),
            "approach": self.conversations.involvement_of(guest),
        }

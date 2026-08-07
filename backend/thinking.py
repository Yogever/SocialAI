"""The thoughts in flight right now.

Thinking is slow — a model call, sometimes minutes of it on a cold local model —
and the party is not allowed to stop while it happens. So a thought runs as its
own task, and the rule that makes that safe is: **a thought in flight never
writes to the party.** It is handed a Situation assembled before it started, it
waits for an answer, and it leaves that answer here. Every change to the world
happens in the tick, which runs start to finish without ever awaiting, so two
changes can't interleave and tear.

Two guards bound it. One thought per guest, because a guest arguing with
themselves in parallel produces two decisions for one moment. And a ceiling on
how many are open at once, because every one of them costs money.

The second guard has a cost of its own: when it trips, somebody is left holding
news that nobody will read this tick. The party asks who, and says so, because a
party that looks frozen and a party that is waiting are indistinguishable
otherwise.
"""

from __future__ import annotations

import asyncio
import time

from backend.guest import Guest
from backend.mind import Decision, Situation
from backend.thought_log import Thought, ThoughtLog
from backend.trigger import News

# How many model calls may be open at once, across the whole party.
AT_ONCE = 5


class Thinking:
    def __init__(self, mind, log: ThoughtLog, at_once: int = AT_ONCE) -> None:
        self.mind = mind
        self.log = log
        self.at_once = at_once
        self._busy: set[str] = set()
        # Strong references, so a running thought isn't collected mid-flight.
        self._tasks: set[asyncio.Task] = set()
        self._answered: list[tuple[Guest, Decision, Thought]] = []
        self._broken: list[Guest] = []

    # ---- who's thinking --------------------------------------------------

    @property
    def at_capacity(self) -> bool:
        return len(self._busy) >= self.at_once

    @property
    def thinkers(self) -> list[str]:
        return sorted(self._busy)

    def busy_with(self, guest: Guest) -> bool:
        return guest.id in self._busy

    def in_flight(self) -> list[asyncio.Task]:
        """The running tasks themselves, for a caller that needs to wait for them.
        The party drives its own tick and never does; a test harness does."""
        return list(self._tasks)

    # ---- starting and collecting -----------------------------------------

    def begin(self, guest: Guest, situation: Situation, news: News, tick: int) -> None:
        self._busy.add(guest.id)
        thought = self.log.open(guest, news, situation, tick)
        task = asyncio.create_task(self._think(guest, situation, thought))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _think(self, guest: Guest, situation: Situation, thought: Thought) -> None:
        """One thought, start to finish. Reads nothing and writes nothing but its
        own record — which has no other writer while it runs."""
        started = time.perf_counter()
        try:
            decision = await self.mind.decide(situation)
            thought.decided(decision, _ms_since(started))
            self._answered.append((guest, decision, thought))
        except Exception as exc:
            # Swallowed here because one bad call must not take the party down —
            # but recorded, and handed to the tick, which owns the cleaning up.
            thought.failed(exc, _ms_since(started))
            self._broken.append(guest)

    def finished(self) -> list[tuple[Guest, Decision, Thought]]:
        """Thoughts that came back since the last tick. Taking them frees their
        guests to think again."""
        answered, self._answered = self._answered, []
        for guest, _, _ in answered:
            self._busy.discard(guest.id)
        return answered

    def failed(self) -> list[Guest]:
        """Guests whose thought raised. They're free to think again too — an
        unreachable model must not wedge a guest for the rest of the night."""
        broken, self._broken = self._broken, []
        for guest in broken:
            self._busy.discard(guest.id)
        return broken


def _ms_since(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)

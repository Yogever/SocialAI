"""One party, many spectators.

The hub is the party's clock and its loudspeaker, and deliberately nothing else.
It owns no world state: it runs the two rhythms at their two different speeds,
posts what comes out to every connected browser, and relays what the browsers ask
for. Anything that changes the party happens inside the party.

The two loops are independent tasks so that a slow thought can't stop the room
moving. That is the entire reason they are separate.
"""

from __future__ import annotations

import asyncio
import contextlib

from backend import event

MOVES_PER_SECOND = 30
SECONDS_BETWEEN_DECISIONS = 5
FASTEST = 3
# How long an evening lasts before the lights come up. Counted in party-seconds,
# so a paused party doesn't age and a fast-forwarded one ages quicker than the
# clock on the wall — the cap is on the evening, not on how long you watch it.
LASTS = 90.0


class Hub:
    def __init__(self, party) -> None:
        self.party = party
        self.watchers: set = set()
        self.paused = False
        self.speed = 1          # fast-forwards the party, not the wall clock
        self.elapsed = 0.0
        self._loops: list[asyncio.Task] = []

    # ---- how far into the evening ----------------------------------------

    @property
    def over(self) -> bool:
        return self.elapsed >= LASTS

    @property
    def left(self) -> float:
        return max(0.0, LASTS - self.elapsed)

    # ---- talking to the browsers ----------------------------------------

    async def tell_everyone(self, message: dict) -> None:
        gone = []
        for watcher in self.watchers:
            try:
                await watcher.send_json(message)
            except Exception:
                gone.append(watcher)
        for watcher in gone:
            self.watchers.discard(watcher)

    async def tell_everyone_about(self, happenings) -> None:
        for happening in happenings:
            await self.tell_everyone(happening)

    # ---- the two rhythms -------------------------------------------------

    async def keep_moving(self) -> None:
        """Broadcast at a real thirty frames a second whatever the speed setting;
        going faster advances the party further per frame rather than sending
        more of them.

        This is also the loop that keeps the time, because it is the one that
        advances the party's own — and so it is the one that announces the end.
        """
        frame = 1.0 / MOVES_PER_SECOND
        while not self.over:
            if not self.paused:
                self.advance(frame * self.speed)
                await self.tell_everyone(self.party.snapshot())
            await asyncio.sleep(frame)
        await self.tell_everyone(event.party_ended(LASTS))

    async def keep_deciding(self) -> None:
        while not self.over:
            if not self.paused:
                await self.tell_everyone_about(self.party.decide())
            await asyncio.sleep(SECONDS_BETWEEN_DECISIONS / self.speed)

    def advance(self, seconds: float) -> None:
        """Move the party forward, and the evening with it."""
        self.elapsed += seconds
        self.party.move(seconds)

    def start(self) -> None:
        self._loops = [asyncio.create_task(self.keep_moving()),
                       asyncio.create_task(self.keep_deciding())]

    async def stop(self) -> None:
        for loop in self._loops:
            loop.cancel()
        for loop in self._loops:
            with contextlib.suppress(asyncio.CancelledError):
                await loop

    # ---- what the browser asks for ---------------------------------------

    async def obey(self, request: dict) -> None:
        """The browser sends intent, never world state. It asks; the party decides."""
        match request.get("type"):
            case "pause":
                self.paused = True
            case "resume":
                self.paused = False
            case "set_speed":
                self.speed = max(1, min(FASTEST, int(request.get("value", 1))))
            case "step":
                await self.step()
            case "open_chat":
                self.paused = True
                await self.relay(self.party.greet(request.get("agent_id", "")))
            case "close_chat":
                self.paused = False
            case "user_message":
                await self.relay(self.party.hear(request.get("agent_id", ""),
                                                request.get("text", "")))

    async def relay(self, awaitable) -> None:
        said = await awaitable
        if said is not None:
            await self.tell_everyone(said)

    async def step(self) -> None:
        """Advance the party by hand, for somebody watching it in slow motion.

        A step is one decision plus the movement that decision would have got.
        Decisions alone would mislead: nobody would ever reach anywhere, so
        nothing would ever arrive, and stepping would produce nothing but
        boredom. Only meaningful while paused, when both loops are idle and this
        is the sole thing driving the party.

        It deliberately does not wait for the thoughts it starts. Those land on
        the *next* step, which is the dispatcher's real two-phase shape and what
        the panel shows. Waiting here would also block the control channel, and
        swallow the resume that was meant to end the investigation.
        """
        if not self.paused or self.over:
            return
        await self.tell_everyone_about(self.party.decide())
        frame = 1.0 / MOVES_PER_SECOND
        for _ in range(round(SECONDS_BETWEEN_DECISIONS * MOVES_PER_SECOND)):
            self.advance(frame)
        await self.tell_everyone(self.party.snapshot())

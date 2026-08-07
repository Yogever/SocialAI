"""A record of what every guest thought, and what it did to the party.

A decision is required to explain itself — reasoning first, a reason on every
feeling it changes — and this is where those explanations land instead of on the
floor. One Thought covers a single thought end to end: what caused it, what the
guest was told, what the model said, how long it took, and what changed when it
was carried out. The log keeps a bounded ring of them and writes nothing to disk.

Two writers, and they never overlap. A thought is opened and later applied by the
tick; in between it is filled in by its own task, which nothing else touches. The
one field that could have had two writers — did it come back, or did it raise —
can't, because a thought either returns or throws, never both.

Nothing here is read by the party. It exists to be looked at.
"""

from __future__ import annotations

import traceback
from collections import deque
from dataclasses import dataclass

from backend.mind import Decision, Situation
from backend.trigger import News

# ~20 decision ticks of a ten-guest party: far enough back to see what went
# wrong, short enough to scroll past.
KEEP = 200

# Tracebacks are for reading, not archiving. Keep the tail, where the cause is.
TRACEBACK_TAIL = 1200


@dataclass
class Thought:
    """One guest's single thought, from what caused it to what it changed."""

    # --- opened by the tick, before the thinking starts ---
    seq: int
    guest_id: str
    guest_name: str
    spawned_at: int
    news: News
    situation: Situation

    # --- filled in by the thought's own task ---
    decision: Decision | None = None
    latency_ms: int | None = None
    error: dict | None = None

    # --- stamped by the tick when it is carried out ---
    status: str = "in_flight"        # in_flight | applied | failed
    applied_at: int | None = None
    felt_before: dict | None = None
    felt_after: dict | None = None
    # True when the whole thought was judged as an answer to somebody's approach
    # rather than executed as an ordinary action — the same words mean very
    # different things on those two paths.
    answered_an_approach: bool = False

    # ---- writing ---------------------------------------------------------

    def decided(self, decision: Decision, latency_ms: int) -> None:
        self.decision = decision
        self.latency_ms = latency_ms

    def failed(self, exc: BaseException, latency_ms: int) -> None:
        """Keep what a bare `except` would have thrown away. A refused connection,
        a schema violation and a timeout are three different bugs; unrecorded they
        are one indistinguishable silence."""
        self.status = "failed"
        self.latency_ms = latency_ms
        self.error = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            )[-TRACEBACK_TAIL:],
        }

    def applied(self, tick: int, before: dict, after: dict,
                answered_an_approach: bool) -> None:
        self.status = "applied"
        self.applied_at = tick
        self.felt_before = before
        self.felt_after = after
        self.answered_an_approach = answered_an_approach

    # ---- reading ---------------------------------------------------------

    def as_dict(self, full: bool = False) -> dict:
        """Wire form, in the browser's vocabulary (see event.py).

        The prompt and the traceback are left out by default: the panel polls a
        whole page of these a few times a second, and a prompt is a couple of
        kilobytes of mostly-identical rules. Ask for one thought in full to read
        them.
        """
        record = {
            "seq": self.seq,
            "agent_id": self.guest_id,
            "agent_name": self.guest_name,
            "tick_spawned": self.spawned_at,
            "trigger_kind": self.news.latest.kind,
            "event_str": self.situation.just_happened,
            "dropped_triggers": list(self.news.missed),
            "reasoning": self.decision.reasoning if self.decision else "",
            "deltas": [d.model_dump() for d in self.decision.deltas] if self.decision else [],
            "action": self.decision.action.model_dump() if self.decision else None,
            "latency_ms": self.latency_ms,
            "status": self.status,
            "tick_applied": self.applied_at,
            "stats_before": self.felt_before,
            "stats_after": self.felt_after,
            "gate": "consent" if self.answered_an_approach else None,
            "error": self.error,
        }
        if full:
            # Rendered from the situation on demand, so it is always the prompt
            # this thought would have sent, and can't drift from it.
            record["prompt"] = dict(self.situation.as_messages())
        elif self.error:
            record["error"] = {key: value for key, value in self.error.items()
                               if key != "traceback"}
        return record


class ThoughtLog:
    """A bounded ring of thoughts, oldest first."""

    def __init__(self, keep: int = KEEP) -> None:
        self.thoughts: deque[Thought] = deque(maxlen=keep)
        self._seq = 0

    def open(self, guest, news: News, situation: Situation, tick: int) -> Thought:
        """Start a record and hand it back to be filled in.

        It goes into the ring immediately, before the thinking has happened, so a
        thought that is still running is visible while it runs — which is the only
        way to see a call that never came back.
        """
        self._seq += 1
        thought = Thought(
            seq=self._seq,
            guest_id=guest.id,
            guest_name=guest.name,
            spawned_at=tick,
            news=news,
            situation=situation,
        )
        self.thoughts.append(thought)
        return thought

    def recent(self, limit: int = 60, guest_id: str | None = None) -> list[Thought]:
        """Newest first, optionally just one guest's."""
        matching = [thought for thought in self.thoughts
                    if guest_id is None or thought.guest_id == guest_id]
        return matching[-limit:][::-1]

    def get(self, seq: int) -> Thought | None:
        return next((thought for thought in self.thoughts if thought.seq == seq), None)

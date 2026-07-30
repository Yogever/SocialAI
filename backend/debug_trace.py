"""Thought records — the observability the planner was designed for but never got.

`PlannerDecision` puts `reasoning` first on purpose (planner.py) and requires a
`reason` on every stat delta, both so a human can read *why* an agent acted. Until
now the controller applied the numbers and dropped the prose on the floor. This
module is where it lands instead.

One `ThoughtRecord` covers a single thought end to end — the trigger that caused
it, the verbatim prompt, what the model said, how long it took, and what it did to
the world. `DebugTrace` keeps a bounded ring of them; nothing is written to disk.

**Single-writer discipline.** A record spans the tick and a `plan()` task, which
run concurrently, so every field has exactly one writer and the four mutators
below are grouped by who calls them:

    tick   ->  DebugTrace.open()      creates + appends the record
    task   ->  record_prompt()        the messages actually sent
    task   ->  record_decision()      the model's reply
    task   ->  mark_failed()          the exception, instead of swallowing it
    tick   ->  mark_applied()         what applying it changed

`record_decision` and `mark_failed` are mutually exclusive (a thought either
returns or raises), so the `status` field never has two live writers. Nothing here
touches shared *world* state, which is what concurrency-notes.md actually forbids.
"""

from __future__ import annotations

import traceback
from collections import deque
from dataclasses import asdict, dataclass, field

# How many thoughts to retain. 200 is ~20 decision-ticks of a 10-agent party —
# enough to scroll back through what just went wrong, small enough to ignore.
TRACE_N = 200

# Tracebacks are for reading, not archiving; keep the tail (where the cause is).
TRACEBACK_CHARS = 1200


@dataclass
class ThoughtRecord:
    """One agent's single thought, from trigger to applied world-change."""

    # --- opened by the tick ---
    seq: int
    agent_id: str
    agent_name: str
    tick_spawned: int
    trigger_kind: str
    event_str: str
    # Triggers this thought consumed but never reacted to: the dispatcher feeds
    # the model only the newest one (`box[-1]`) and clears the rest, so these are
    # events that happened to the agent and vanished. Silent by default; a common
    # cause of "why did it ignore that?".
    dropped_triggers: list[str] = field(default_factory=list)

    # --- filled by the think task ---
    prompt: dict | None = None            # {"system": ..., "human": ...}
    reasoning: str = ""
    deltas: list[dict] = field(default_factory=list)
    action: dict | None = None
    latency_ms: int | None = None
    error: dict | None = None             # {"type", "message", "traceback"}

    # --- stamped by the tick when the decision is applied ---
    status: str = "in_flight"             # in_flight | applied | failed
    tick_applied: int | None = None
    stats_before: dict | None = None
    stats_after: dict | None = None
    # "consent" when this decision was judged as an answer to an approach (D7)
    # rather than executed as an ordinary action — the same `reply_in_conversation`
    # means very different things on the two paths.
    gate: str | None = None

    # ---- writers (see the single-writer table in the module docstring) ----

    def record_prompt(self, messages: dict) -> None:
        self.prompt = dict(messages)

    def record_decision(
        self,
        *,
        reasoning: str,
        deltas: list[dict],
        action: dict,
        latency_ms: int,
    ) -> None:
        self.reasoning = reasoning
        self.deltas = deltas
        self.action = action
        self.latency_ms = latency_ms

    def mark_failed(self, exc: BaseException, *, latency_ms: int) -> None:
        """Capture what the bare `except Exception` used to throw away. A refused
        connection, a schema-validation failure and a timeout are three different
        bugs; without this they are one indistinguishable silence."""
        self.status = "failed"
        self.latency_ms = latency_ms
        self.error = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            )[-TRACEBACK_CHARS:],
        }

    def mark_applied(
        self,
        *,
        tick: int,
        stats_before: dict,
        stats_after: dict,
        gate: str | None,
    ) -> None:
        self.status = "applied"
        self.tick_applied = tick
        self.stats_before = stats_before
        self.stats_after = stats_after
        self.gate = gate

    # ---- reading ----

    def to_dict(self, *, full: bool = False) -> dict:
        """Wire form. The default omits the prompt and traceback: the debug panel
        polls a whole page of these a few times a second, and the prompt is ~2KB
        of mostly-identical rules text. Fetch one record `full` to see them."""
        d = asdict(self)
        if not full:
            d.pop("prompt", None)
            if d["error"]:
                d["error"] = {k: v for k, v in d["error"].items() if k != "traceback"}
        return d


class DebugTrace:
    """Bounded ring of thought records, newest-last internally."""

    def __init__(self, maxlen: int = TRACE_N) -> None:
        self._records: deque[ThoughtRecord] = deque(maxlen=maxlen)
        self._seq = 0

    def open(
        self,
        *,
        agent_id: str,
        agent_name: str,
        tick: int,
        trigger_kind: str,
        event_str: str,
        dropped_triggers: list[str],
    ) -> ThoughtRecord:
        """Start a record and hand it to the caller, who passes it to the think
        task. Already in the ring, so an in-flight thought is visible while it
        runs — that's how you see a call that never came back."""
        self._seq += 1
        rec = ThoughtRecord(
            seq=self._seq,
            agent_id=agent_id,
            agent_name=agent_name,
            tick_spawned=tick,
            trigger_kind=trigger_kind,
            event_str=event_str,
            dropped_triggers=dropped_triggers,
        )
        self._records.append(rec)
        return rec

    def recent(self, limit: int = 60, agent_id: str | None = None) -> list[ThoughtRecord]:
        """Newest first, optionally one agent's only."""
        rs = [r for r in self._records
              if agent_id is None or r.agent_id == agent_id]
        return rs[-limit:][::-1]

    def get(self, seq: int) -> ThoughtRecord | None:
        return next((r for r in self._records if r.seq == seq), None)

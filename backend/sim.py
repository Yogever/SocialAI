"""Real simulation: the LLM-driven brain (D6/D11).

Same world and guest list as StubSim (both inherit BaseSim's physics, snapshot
format and agent loading). What StubSim faked with a state machine + canned lines,
this fills with the planner — and, crucially, the *wiring* around it.

The shape of that wiring, decided in docs/planner-decisions.md:

  - D11  Dispatcher + task-per-think. `decision_step` is a NON-blocking tick: it
         drains finished thoughts, applies them, scans for what should think next,
         and spawns `plan()` calls as background asyncio tasks. It never awaits an
         LLM, so a slow model can't freeze the party — 10 agents think in parallel.
  - D12  Six triggers land in per-agent inboxes; the tick drains them. A thought
         is caused by an event (entry, arrival, being approached, a partner
         speaking, a conversation ending, boredom), never by polling.
  - D6   A conversation is NOT its own loop. It's a `Conversation` state object plus
         a handful of apply-block handlers: an agent's `reply_in_conversation`
         appends a line and drops a `partner_spoke` trigger in its partner's inbox.
         The ping-pong *is* two agents triggering each other; the only loop in the
         whole system is this tick.
  - D7   `approach` is a physical walk-over, then the target judges the opener and
         may decline. The gap is the `PendingApproach` limbo (like TCP SYN-SENT).
  - D8   Leave any turn to end it; a hard turn-cap is a runaway fuse.

The one concurrency rule that makes this safe (concurrency-notes.md): a `plan()`
task NEVER writes shared state. It only reads (at spawn), awaits the model, and
drops its result in `_completed`. All writes happen here in the tick, which runs
start-to-finish with no `await` — so mutations can't interleave and tear.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field

from backend.base_sim import WAYPOINTS, BaseSim, _clamp
from backend.planner import PlannerDecision
from backend.planner_client import plan

# Tuning knobs, all in one place.
CONV_CAP = 10             # D8 fuse: max turns before a conversation is wound down
MEMORY_N = 8             # D9: how many recent events an agent carries forward
MAX_CONCURRENT = 5       # D11 guard 2: cap simultaneous planner calls (bounds cost)
BOREDOM_TICKS = 8        # D1 safety net: idle this many decision-ticks -> re-plan

# Stat ranges the deltas are clamped INTO (the -15..+15 band bounds the step; this
# bounds the ceiling). Mirrors the scales the RULES prompt tells the model about.
STAT_RANGE = {"drunkenness": (0, 100), "confidence": (-100, 100), "fun": (-100, 100)}


@dataclass
class Conversation:
    """The whole 'orchestrator' state for one chat. No behaviour of its own — the
    apply-block handlers read/write it. `turn_count` is the D8 cap counter; whoever
    holds the latest `partner_spoke` trigger is the one who speaks next."""
    id: str
    participants: tuple[str, str]      # (approacher_id, target_id)
    transcript: list[str]              # rendered "Name: line", in speaking order
    turn_count: int = 0
    cap: int = CONV_CAP
    speaker: str = ""                  # whose turn it is right now (guard/debug)


@dataclass
class PendingApproach:
    """The D7 limbo: A has committed to approach B and is walking over, but B hasn't
    judged the opener yet. Keyed in `self.pending` by TARGET id, so a target can
    only be claimed once — a second approacher racing the first bounces off."""
    approacher: str
    opener: str
    opened: bool = False               # False = still walking; True = opener delivered


@dataclass
class Trigger:
    """One reason-to-think dropped in an agent's inbox (D12). `kind` selects the
    render; `payload` carries whatever that render needs."""
    kind: str
    payload: dict = field(default_factory=dict)


class Sim(BaseSim):
    def __init__(self, seed: int | None = None) -> None:
        super().__init__(seed)
        # --- conversation + handshake state (sim-owned) ---
        self.conversations: dict[str, Conversation] = {}
        self.pending: dict[str, PendingApproach] = {}         # target_id -> approach
        self._cid_seq = 0
        # --- the event-sourced machinery (D11/D12) ---
        self.inbox: dict[str, list[Trigger]] = {a: [] for a in self.agents}
        self.memory: dict[str, list[str]] = {a: [] for a in self.agents}  # D9 raw log
        self._thinking: set[str] = set()          # in-flight guard (one thought/agent)
        self._tasks: set[asyncio.Task] = set()    # strong refs so tasks aren't GC'd
        self._completed: list[tuple[str, PlannerDecision]] = []
        self._failed: list[str] = []
        self._last_decided: dict[str, int] = {}   # for the boredom timer
        self._dtick = 0
        # Everyone walks in with no intention yet -> an `entry` thought (D12 #6).
        for a in self.agents:
            self._emit(a, Trigger("entry"))

    # ==================================================================
    #  THE TICK  — the only loop in the system. Sync + await-free, so every
    #  write below is serialized against every other. Called ~1.5s by main.py.
    # ==================================================================

    def decision_step(self) -> list[dict]:
        self._dtick += 1
        self.tick = self._dtick
        events: list[dict] = []

        # 1) Apply finished thoughts. This is the await-free apply block: results
        #    computed off-thread (well, off-tick) land here and mutate the world.
        while self._completed:
            agent_id, decision = self._completed.pop(0)
            self._thinking.discard(agent_id)
            self._last_decided[agent_id] = self._dtick
            agent = self.agents.get(agent_id)
            if agent is not None:
                events += self._apply(agent, decision)

        # 2) A failed call must not wedge its agent forever (the shell owns errors).
        while self._failed:
            agent_id = self._failed.pop(0)
            self._thinking.discard(agent_id)
            agent = self.agents.get(agent_id)
            if agent and agent.conversation_id in self.conversations:
                # end the chat so the partner isn't left waiting on a dead turn
                events += self._end(self.conversations[agent.conversation_id],
                                    reason="left", by=agent_id)
            elif agent:
                agent.action = "idle"

        # 3) World-driven triggers: arrivals (incl. approach openers) and boredom.
        events += self._scan_arrivals()
        self._scan_boredom()

        # 4) Dispatch: for every agent with a pending trigger, spawn a think.
        self._dispatch_thinks()
        return events

    def _dispatch_thinks(self) -> None:
        """Turn queued triggers into background `plan()` tasks, honouring both D11
        guards: never two calls for one agent, never more than MAX in flight."""
        for agent_id, box in self.inbox.items():
            if not box or agent_id in self._thinking:
                continue
            if len(self._thinking) >= MAX_CONCURRENT:
                break
            trigger = box[-1]          # the focal event; older ones already lived
            box.clear()                # their moment; drop the rest to avoid pile-up
            event_str = self._render(trigger, self.agents[agent_id])
            self._remember(agent_id, event_str)
            self._thinking.add(agent_id)
            task = asyncio.create_task(self._think(agent_id, event_str))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _think(self, agent_id: str, event_str: str) -> None:
        """One planner call as a concurrent task. Reads state ONCE at the top (a
        consistent snapshot, since no tick is writing while this runs), awaits the
        model, then hands the result back to the tick. It never writes the world."""
        try:
            agent = self.agents[agent_id]
            others = [o for o in self.agents.values() if o.id != agent_id]
            memory = list(self.memory.get(agent_id, []))
            transcript = None
            if agent.conversation_id in self.conversations:
                transcript = list(self.conversations[agent.conversation_id].transcript)
            decision = await plan(agent, others, event_str, memory, transcript)
            self._completed.append((agent_id, decision))
        except Exception:
            # swallow + queue for cleanup in the tick; one bad call can't crash the loop
            self._failed.append(agent_id)

    # ==================================================================
    #  APPLY  — a finished decision becomes world changes + broadcast events.
    # ==================================================================

    def _apply(self, agent, decision: PlannerDecision) -> list[dict]:
        self._apply_deltas(agent, decision.deltas)

        # GATE (D7): is this agent answering an approach it received? Then this whole
        # decision is an accept/decline, not an ordinary action.
        pending = self.pending.get(agent.id)
        if pending is not None and pending.opened:
            self.pending.pop(agent.id)
            return self._resolve_consent(agent, pending, decision.action)

        self._remember(agent.id, self._summarize(decision.action))
        return self._dispatch_action(agent, decision.action)

    def _apply_deltas(self, agent, deltas) -> None:
        for d in deltas:
            lo, hi = STAT_RANGE.get(d.stat, (-100, 100))
            agent.stats[d.stat] = _clamp(agent.stats.get(d.stat, 0) + d.delta, lo, hi)

    def _dispatch_action(self, agent, act) -> list[dict]:
        """The single place a verb turns into a world-change. Deltas are already
        applied by the time we get here, so the decline path can reuse this freely."""
        if act.type == "go_to":
            self._go(agent, act.spot)
        elif act.type == "go_drink":
            self._go(agent, "bar")
        elif act.type == "idle":
            agent.action = "idle"
            agent.target = list(agent.pos)   # 'idle' means stay put — kill any drift
                                             # (movement_step moves toward target
                                             #  regardless of action, so pin it)
        elif act.type == "approach":
            return self._begin_approach(agent, act)
        elif act.type == "reply_in_conversation":
            return self._on_reply(agent, act.text)
        elif act.type == "leave_conversation":
            return self._on_leave(agent)
        return []

    # ---- conversation handlers (the 'orchestrator', such as it is) ----------

    def _begin_approach(self, a, act) -> list[dict]:
        b = self._by_name(act.target_name)
        if b is None or b.id == a.id or b.conversation_id or b.id in self.pending:
            # stale/busy/self target: bounce so A re-plans instead of freezing.
            self._emit(a.id, Trigger("approach_failed"))
            return []
        self.pending[b.id] = PendingApproach(approacher=a.id, opener=act.opener)
        a.target = list(b.pos)          # walk over; controller re-grounds on B's real pos
        a.target_type = b.target_type
        a.action = "walking"
        return []

    def _resolve_consent(self, b, pending, act) -> list[dict]:
        a = self.agents.get(pending.approacher)
        if a is None:                    # approacher vanished; nothing to accept
            return []
        self._remember(b.id, self._summarize(act))
        if act.type == "reply_in_conversation":                 # ENGAGED -> accept
            conv = self._start_conversation(a, b, pending.opener, act.text)
            conv.speaker = a.id
            self._emit(a.id, Trigger("partner_spoke",
                                     {"conv": conv.id, "speaker": b.name, "text": act.text}))
            return [
                {"type": "conversation_started", "tick": self._dtick,
                 "conversation_id": conv.id, "participants": list(conv.participants),
                 "names": [a.name, b.name]},
                self._speech(a, pending.opener, conv.id),
                self._speech(b, act.text, conv.id),
            ]
        # ANY other action -> decline. A un-parks and reacts; B still does its real move.
        a.action = "idle"
        self._emit(a.id, Trigger("approach_declined", {"who": b.name}))
        return self._dispatch_action(b, act)

    def _start_conversation(self, a, b, opener: str, reply: str) -> Conversation:
        self._cid_seq += 1
        cid = f"c{self._cid_seq}"
        conv = Conversation(
            id=cid,
            participants=(a.id, b.id),
            transcript=[f"{a.name}: {opener}", f"{b.name}: {reply}"],
        )
        self.conversations[cid] = conv
        # Stand them together (~50px apart) at their midpoint, like the stub did.
        cx = (a.pos[0] + b.pos[0]) / 2
        cy = (a.pos[1] + b.pos[1]) / 2
        for who, off in ((a, -25), (b, 25)):
            who.conversation_id = cid
            who.action = "talking"
            who.target = [cx + off, cy]
            who.target_type = "floor"
        return conv

    def _on_reply(self, agent, text: str) -> list[dict]:
        cid = agent.conversation_id
        if cid not in self.conversations:      # guard: stray reply outside a chat
            return []
        conv = self.conversations[cid]
        conv.transcript.append(f"{agent.name}: {text}")
        conv.turn_count += 1
        events = [self._speech(agent, text, cid)]
        partner_id = self._partner(conv, agent.id)
        if conv.turn_count >= conv.cap:
            events += self._end(conv, reason="cap")            # D8 fuse
        else:
            conv.speaker = partner_id
            self._emit(partner_id, Trigger("partner_spoke",
                                           {"conv": cid, "speaker": agent.name, "text": text}))
        return events

    def _on_leave(self, agent) -> list[dict]:
        cid = agent.conversation_id
        if cid not in self.conversations:
            return []
        return self._end(self.conversations[cid], reason="left", by=agent.id)

    def _end(self, conv, reason: str, by: str | None = None) -> list[dict]:
        """Tear the conversation down for BOTH parties at once (D8.2), send them
        drifting, and hand the left-behind party a trigger to react to (D8.3)."""
        self.conversations.pop(conv.id, None)
        names = []
        for pid in conv.participants:
            ag = self.agents.get(pid)
            if ag:
                ag.conversation_id = None
                names.append(ag.name)
                self._send_to_waypoint(ag)          # walk off; arrival re-triggers later
        if reason == "left" and by is not None:
            leaver = self.agents.get(by)
            other = self._partner(conv, by)
            self._emit(other, Trigger("conversation_ended",
                                      {"who": leaver.name if leaver else "someone"}))
        elif reason == "cap":
            for pid in conv.participants:
                self._emit(pid, Trigger("conversation_ended", {"cap": True}))
        return [{"type": "conversation_ended", "tick": self._dtick,
                 "conversation_id": conv.id, "participants": list(conv.participants),
                 "names": names}]

    # ==================================================================
    #  TRIGGER SOURCES  — the world (not another agent) causing a think.
    # ==================================================================

    def _scan_arrivals(self) -> list[dict]:
        events: list[dict] = []
        approachers = {pa.approacher for pa in self.pending.values()}

        # (a) approach openers: the walker reached its target -> the D7 handshake fires.
        for target_id, pa in list(self.pending.items()):
            if pa.opened:
                continue
            a = self.agents.get(pa.approacher)
            b = self.agents.get(target_id)
            if a is None or b is None:
                self.pending.pop(target_id, None)
                continue
            a.target = list(b.pos)              # D7: re-ground on B's real (moved) pos
            # "Arrived" for an approach == close enough to talk, NOT pixel-exact:
            # collision resolution holds agents ~32px apart, so _reached (6px) at
            # B's position is unreachable. Proximity to B (who may have drifted) is
            # both the correct test and robust to B moving.
            if self._near(a, b):
                pa.opened = True
                a.action = "idle"                   # park A: waiting for B to judge
                self._emit(target_id, Trigger("was_approached",
                                              {"who": a.name, "opener": pa.opener}))

        # (b) ordinary arrivals: a walker settled at its spot -> decide what's next.
        for a in self.agents.values():
            if a.action != "walking" or a.id in approachers or not self._reached(a):
                continue
            if a.target_type == "bar":
                a.stats["drunkenness"] = _clamp(a.stats.get("drunkenness", 0) + 8, 0, 100)
                events.append({"type": "agent_drank", "tick": self._dtick,
                               "agent_id": a.id, "name": a.name})
            a.action = "idle"
            self._emit(a.id, Trigger("arrived", {"spot": a.target_type}))
        return events

    def _scan_boredom(self) -> None:
        approachers = {pa.approacher for pa in self.pending.values()}
        for a in self.agents.values():
            if a.action != "idle" or a.id in self._thinking or a.id in approachers:
                continue
            if self.inbox.get(a.id):               # already has a reason to think
                continue
            if self._dtick - self._last_decided.get(a.id, -BOREDOM_TICKS) >= BOREDOM_TICKS:
                self._emit(a.id, Trigger("boredom"))

    # ==================================================================
    #  SMALL HELPERS
    # ==================================================================

    def _go(self, agent, spot: str) -> None:
        choices = [(x, y) for (x, y, t) in WAYPOINTS if t == spot]
        x, y = self.rng.choice(choices) if choices else (agent.pos[0], agent.pos[1])
        agent.target = [float(x), float(y)]
        agent.target_type = spot
        agent.action = "walking"

    def _emit(self, agent_id: str, trigger: Trigger) -> None:
        self.inbox.setdefault(agent_id, []).append(trigger)

    def _remember(self, agent_id: str, line: str) -> None:
        log = self.memory.setdefault(agent_id, [])
        log.append(line)
        del log[:-MEMORY_N]              # keep only the last N (D9 bounded raw log)

    def _speech(self, agent, text: str, cid: str) -> dict:
        return {"type": "agent_spoke", "tick": self._dtick, "agent_id": agent.id,
                "conversation_id": cid, "text": text}

    def _by_name(self, name: str):
        key = name.strip().lower()       # matches the case-insensitive load-time guard
        return next((a for a in self.agents.values()
                     if a.name.strip().lower() == key), None)

    def _partner(self, conv: Conversation, agent_id: str) -> str:
        a, b = conv.participants
        return b if agent_id == a else a

    def _near(self, a, b, dist: float = 50.0) -> bool:
        return math.hypot(a.pos[0] - b.pos[0], a.pos[1] - b.pos[1]) <= dist

    # ---- rendering: trigger/action -> the prose the model reads or remembers ----
    # This is the 'renderer' we parked. It's the central render(trigger, agent)
    # form; it lives in exactly these two methods and nothing upstream cares.

    def _render(self, trigger: Trigger, agent) -> str:
        k, p = trigger.kind, trigger.payload
        if k == "entry":
            return "You just walked into the party."
        if k == "arrived":
            return f"You arrived at the {p.get('spot', 'floor')}."
        if k == "was_approached":
            return f"{p['who']} walked over to you and said: \"{p['opener']}\""
        if k == "partner_spoke":
            return f"{p['speaker']} said: \"{p['text']}\""
        if k == "approach_declined":
            return f"{p['who']} brushed off your approach and didn't engage."
        if k == "approach_failed":
            return "You went to talk to someone, but they weren't available."
        if k == "conversation_ended":
            if p.get("cap"):
                return "Your conversation wound down naturally."
            return f"{p.get('who', 'They')} ended the conversation and walked off."
        if k == "boredom":
            return "You've been standing around a while; nothing much is happening."
        return "Something happened."

    def _summarize(self, act) -> str:
        if act.type == "go_to":
            return f"You headed to the {act.spot}."
        if act.type == "go_drink":
            return "You went to get a drink."
        if act.type == "approach":
            return f"You approached {act.target_name}: \"{act.opener}\""
        if act.type == "reply_in_conversation":
            return f"You said: \"{act.text}\""
        if act.type == "leave_conversation":
            return "You left the conversation."
        return "You stayed put."

    # open_chat / user_message (the user-as-participant path) are a distinct piece:
    # they need their own async round-trip to the chat panel, not the agent-agent
    # orchestrator above. Undesigned — but overridden as safe no-ops (not BaseSim's
    # NotImplementedError) so an accidental agent-click can't crash a client socket.
    def open_chat(self, agent_id: str) -> dict | None:
        return None

    def user_message(self, agent_id: str, text: str) -> dict | None:
        return None

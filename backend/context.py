"""Context assembly — the *input* half of the planner contract.

The planner's output is docs Part 1 (see planner.py); this is Part 2: turning
world-state into the payload the model reads. It is deliberately **pure** — no IO,
no model call — so the whole thing is assertable with zero tokens: given these
agents, the envelope is exactly this dict.

The shape follows F1's caching tiers (docs/planner-context-and-schema.md), ordered
most-shared -> per-agent-static -> volatile:

    RULES              module constant, identical for every agent   -> cached once
    build_identity()   per-agent, stable across its re-plans         -> cached per agent
    build_dynamic()    changes every call                            -> never cached

The assembler owns the split because stability is a *semantic* property: it knows
`personality` is forever and `stats` are per-tick; the downstream call layer just
sees dicts. Whoever understands the fields owns the partition.

The agent reasons entirely in **semantic space** (F2): spots and actions, never
coordinates. `target_type` is the semantic location; pixels never appear here.
"""

from __future__ import annotations

import json

from backend.models import Agent

# Stats the LLM actually reads *and* writes (D10 dynamic). `attractiveness` is
# intentionally absent: it's a static "how others read you" trait, so it shows up
# in perception of *others*, never in an agent's own feelings, and the LLM never
# emits a delta for it (StatDelta.stat doesn't include it either).
DYNAMIC_STATS = ("drunkenness", "confidence", "fun")

# --- The rules tier (F1 most-shared): the sim's mechanics, not psychology (F4). -
# We describe the *world* — spots, stat scales, the action menu, the delta bound —
# and trust the model's pretrained understanding of *people* for everything else.
# v1 wording; expect to iterate it once we see real decisions (step #3).
RULES = """\
You are a single guest at a house party, deciding what to do next AS this specific \
person. Act as they genuinely would: their personality, goal, and how they currently \
feel drive every choice. Do not narrate an omniscient view — you only know what this \
person can see.

The party is one room. The spots you can move to are: bar, couch, window, snack, floor.

Each turn you output three things:

- reasoning: think first, in a sentence or two, in this person's own head.

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


def build_identity(agent: Agent) -> dict:
    """Per-agent static tier: who this agent is. Stable across all its re-plans,
    so this dict is the per-agent cached segment (F1). Coordinates and dynamic
    stats deliberately excluded — nothing in here should ever change mid-party."""
    return {
        "name": agent.name,
        "age": agent.age,
        "personality": agent.personality,
        "goal": agent.goal,
    }


def build_dynamic(
    agent: Agent,
    others: list[Agent],
    event: str,
    memory: list[str],
    transcript: list[str] | None = None,
) -> dict:
    """Volatile tier: everything that can change between calls.

    Pure and dumb on purpose — `event`, `memory`, and `transcript` arrive already
    rendered (prose strings) from the caller, so the assembler never has to know
    where memory is stored or how the orchestrator formats a turn. That keeps this
    testable and decouples it from the state-management decisions in wiring (#4).
    """
    payload = {
        "stats": {k: round(agent.stats.get(k, 0)) for k in DYNAMIC_STATS},
        "location": agent.target_type,           # semantic; never pixels (F2)
        "room": [_perceive(o) for o in others],
        "just_happened": event,
        "memory": memory,
    }
    # Only present mid-conversation, so its absence itself signals "not talking".
    if transcript is not None:
        payload["transcript"] = transcript
    return payload


def _perceive(other: Agent) -> dict:
    """The observable surface of another agent (F2): what you'd clock across a
    room. Name, semantic location, what they're doing, whether they're free — and
    attractiveness, the one internal-ish trait readable from a distance. Their
    private stats are NOT here: you infer their state from behaviour, you don't
    read their confidence integer. That inference is where personality-filtered
    perception (and thus emergence) lives."""
    return {
        "name": other.name,
        "location": other.target_type,
        "action": other.action,
        "available": other.conversation_id is None,
        "attractiveness": round(other.stats.get("attractiveness", 0)),
    }


def serialize(payload: dict) -> str:
    """Envelope -> JSON string (F3: structured skeleton, prose inside the values).
    Kept separate from the dict builders so tests assert on structure, not text.
    `ensure_ascii=False` so names/dialogue with non-ASCII stay human-readable."""
    return json.dumps(payload, ensure_ascii=False)

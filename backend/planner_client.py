"""The imperative shell: the one place the planner talks to a model.

Pure core in, validated decision out. The core is provable without tokens
(planner.py's schema, context.py's assembler); this file is the thin,
hard-to-test layer that actually spends a token and reaches the network.

LangChain touches *only* this file, and only for two things: the model call and
the structured-output parse. No chains, no agents, no memory classes leak in —
that's the boundary we agreed to hold (the dispatcher and conversation loop stay
hand-rolled; LangGraph is a conscious future decision, not a default).

The model is a config knob (`PLANNER_MODEL`): today a local Ollama model, tomorrow
a hosted one, changed without touching this code. The ordering discipline that
makes caching work (RULES -> identity -> volatile) is baked into how the messages
are laid out below, and transfers across providers even though the explicit
cache-control markers do not.

The call is deliberately **two steps**, not one:

    build_messages()   pure, no network — the exact prompt, assertable token-free
    invoke()           the one impure line: send it and validate the reply

A single `plan()` that did both would hide the prompt inside the await, and the
moment you most want to read a prompt is while its call is still hanging (a cold
local model can sit there for minutes). Splitting them lets the caller record what
it is about to send *before* sending it.
"""

from __future__ import annotations

import os
from functools import lru_cache

from langchain.chat_models import init_chat_model

from backend.context import RULES, build_dynamic, build_identity, serialize
from backend.models import Agent
from backend.planner import PlannerDecision

# "provider:model" — the whole model choice, in one swappable string.
MODEL_ID = os.environ.get("PLANNER_MODEL", "ollama:qwen2.5:7b")


@lru_cache(maxsize=1)
def _planner():
    """Lazily build the structured-output runnable, once.

    Lazy on purpose: importing this module must not require Ollama to be up (tests,
    the pure core, and tooling all import freely). The client is only constructed
    on the first real `plan()` call. `method="json_schema"` asks Ollama to
    constrain decoding to the schema itself — the most reliable structured-output
    path for a local model, vs. hoping it emits valid tool-call JSON unaided.
    """
    model = init_chat_model(MODEL_ID)
    return model.with_structured_output(PlannerDecision, method="json_schema")


def build_messages(
    agent: Agent,
    others: list[Agent],
    event: str,
    memory: list[str],
    transcript: list[str] | None = None,
) -> list[tuple[str, str]]:
    """Assemble the exact messages the model will see. Pure — the last piece of
    the planner's core that was still buried inside the network call, split out so
    the prompt can be inspected (and asserted) without spending a token.

    The ordering is the F1 caching discipline: shared rules, then per-agent stable
    identity, then the volatile turn.
    """
    identity = build_identity(agent)
    dynamic = build_dynamic(agent, others, event, memory, transcript)
    return [
        # system == the cached prefix: shared rules, then this agent's stable identity.
        ("system", f"{RULES}\n\n<you>\n{serialize(identity)}\n</you>"),
        # human == the volatile turn: how it feels, what it sees, what just happened.
        ("human", serialize(dynamic)),
    ]


async def invoke(messages: list[tuple[str, str]]) -> PlannerDecision:
    """Send an assembled prompt and return the validated decision — the whole
    impure surface of the planner, in one line.

    Async because it runs inside the D11 dispatcher as one concurrent task among
    many. Raises on anything the model or the schema rejects; the caller (the
    dispatcher) owns error handling.
    """
    return await _planner().ainvoke(messages)

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


async def plan(
    agent: Agent,
    others: list[Agent],
    event: str,
    memory: list[str],
    transcript: list[str] | None = None,
) -> PlannerDecision:
    """Run one planner call for `agent` and return its validated decision.

    Three steps: assemble the context (pure core), lay it into the cached/volatile
    message slots (F1), invoke and let Pydantic validate the reply. Async because
    it runs inside the D11 dispatcher as one concurrent task among many.
    """
    identity = build_identity(agent)
    dynamic = build_dynamic(agent, others, event, memory, transcript)
    messages = [
        # system == the cached prefix: shared rules, then this agent's stable identity.
        ("system", f"{RULES}\n\n<you>\n{serialize(identity)}\n</you>"),
        # human == the volatile turn: how it feels, what it sees, what just happened.
        ("human", serialize(dynamic)),
    ]
    return await _planner().ainvoke(messages)

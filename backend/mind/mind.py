"""A guest's capacity to think — the one place the party talks to a model.

Everything either side of this file is provable without spending a token: a
Situation is assembled from plain values, a Decision is validated against a
schema. This is the thin layer in between that actually reaches the network, and
it is deliberately the only one, so "what does the party do when the model is
slow, wrong, or down" has exactly one place to be answered.

A mind answers two questions:

    decide(situation)      -> Decision   what does this person do next?
    small_talk(situation)  -> str        what does this person say back?

Anything that can answer those two is a mind, which is why ScriptedMind can stand
in for this one without the party noticing. LangChain is used for the model call
and the structured-output parse and nothing else — no chains, no agent
abstractions, no memory classes. The dispatcher and the conversations are ours.

Which model runs is a config knob, not a code change.
"""

from __future__ import annotations

import os
from functools import lru_cache

from langchain.chat_models import init_chat_model

from backend.mind.decision import Decision
from backend.mind.situation import Situation

# "provider:model" — the whole model choice, in one swappable string.
#
# Hosted rather than local, because the party is watched live: a local 7b on CPU
# answers in ~44s, which is thirty ticks of a guest standing still. This one
# answers in ~1.2s — inside a single tick — and is the cheapest Flash-Lite still
# open to new keys (2.5 Flash-Lite is not; see llm-costs.md §6). Needs
# GOOGLE_API_KEY; PARTY_MODEL=ollama:qwen2.5:7b goes back to the local one.
MODEL_ID = os.environ.get("PARTY_MODEL", "google_genai:gemini-3.1-flash-lite")


class Mind:
    async def decide(self, situation: Situation) -> Decision:
        """What this person does next. Raises on anything the model or the schema
        rejects — a thought that fails is the party's problem to clean up, not
        something to paper over here with a default action."""
        return await _decider().ainvoke(situation.as_messages())

    async def small_talk(self, situation: Situation) -> str:
        """What this person says back to whoever just spoke to them. Plain words,
        no schema: there is nothing structured to commit to, only a line."""
        reply = await _talker().ainvoke(situation.as_chat_messages())
        return str(reply.content).strip()


@lru_cache(maxsize=1)
def _talker():
    """The model itself, built once and lazily.

    Lazy on purpose: importing this module must not require the model to be
    running, so tests, tooling and the whole pure core can import freely and only
    a real thought pays the connection.
    """
    return init_chat_model(MODEL_ID)


@lru_cache(maxsize=1)
def _decider():
    """The same model, constrained to the decision schema.

    `json_schema` asks the model to constrain its decoding to the schema rather
    than hoping it emits valid JSON unaided — by far the more reliable path for a
    small local model.
    """
    return _talker().with_structured_output(Decision, method="json_schema")

"""The planner's output contract — the structured decision an agent emits.

This is the *trust boundary*: everything here is what comes back out of a language
model's mouth, so it's Pydantic (not a dataclass). One `PlannerDecision` class does
two jobs from a single definition:

  - generates the JSON Schema we constrain the model with  (.model_json_schema())
  - parses + validates the model's reply                   (.model_validate_json())

Schema-out and validate-in stay in sync by construction. Internal, trusted structs
(see models.py's `Agent`) stay dataclasses; Pydantic earns its keep only here, at
the edge where untrusted text becomes a typed object the controller can execute.

Design record: docs/planner-context-and-schema.md (Part 1). The action space is
D5 in docs/planner-decisions.md.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class StatDelta(BaseModel):
    """One bounded change to one dynamic stat, with its reason.

    The band (-15..+15) is the D2 guardrail: the LLM owns the magnitude so
    personality-specific reactions can emerge, but it can't move a stat more than
    one event's worth. Code still clamps the *resulting* stat to its own range
    (e.g. 0..100) after applying — this bounds the step, not the ceiling. `reason`
    is required: an emergent number you can't inspect is a bug you can't find.
    """

    stat: Literal["drunkenness", "confidence", "fun"]
    delta: int = Field(ge=-15, le=15)
    reason: str


# --- Action space (D5): one class per verb, discriminated on `type`. -----------
# Each variant carries only its own params, so the model physically cannot emit
# e.g. `approach` without an `agent_id` + `opener`. Pydantic reads `type` and
# validates against that one variant.

class GoTo(BaseModel):
    type: Literal["go_to"]
    # Semantic spot, never coordinates — the controller resolves it to a waypoint.
    spot: Literal["bar", "couch", "window", "snack", "floor"]


class GoDrink(BaseModel):
    type: Literal["go_drink"]


class Approach(BaseModel):
    type: Literal["approach"]
    # The NAME of the person to approach — the agent reasons in names (it only
    # perceives names, not ids), so the name is the key. Uniqueness is enforced at
    # agent load, so a name resolves to exactly one guest. The controller does
    # name -> agent lookup at execution time.
    target_name: str
    # F5: the target judges this line and may decline (D7). Consent needs words on
    # the table — an `approach` with no opener leaves the target judging nothing.
    opener: str


class Reply(BaseModel):
    type: Literal["reply_in_conversation"]
    text: str


class Leave(BaseModel):
    type: Literal["leave_conversation"]


class Idle(BaseModel):
    type: Literal["idle"]


Action = Annotated[
    Union[GoTo, GoDrink, Approach, Reply, Leave, Idle],
    Field(discriminator="type"),
]


class PlannerDecision(BaseModel):
    """One agent's whole thought: how it now feels, and what it does next (D3).

    `reasoning` is deliberately declared *first*. Because the model generates
    fields top-to-bottom, a free-text field before the structured commitments makes
    it think before it decides — chain-of-thought smuggled inside a JSON schema, and
    our window into *why* it acted. Placed last it would only rationalize a choice
    already made.
    """

    reasoning: str
    deltas: list[StatDelta]
    action: Action

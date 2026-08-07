"""What a mind is allowed to answer.

This is the trust boundary. Everything in this file describes text that came out
of a language model, so it is Pydantic rather than a dataclass: one definition
both generates the JSON schema the model is constrained to and validates what
comes back, so the shape we ask for and the shape we accept cannot drift apart.
Structures we build ourselves (a Guest, a Situation) stay plain — Pydantic earns
its keep only here, where untrusted text becomes something the party can execute.

Each action also knows how it would be remembered afterwards, in the guest's own
words. That sentence goes straight into their memory and back into the next
prompt, so it belongs to the action rather than to a table somewhere else.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union, get_args

from pydantic import BaseModel, Field

from backend import room


class StatDelta(BaseModel):
    """One bounded change to one feeling, with its reason.

    The band is the guardrail: the mind owns the magnitude, so a nervous guest and
    a brash one can react to the same moment by different amounts, but no single
    moment can move a feeling more than a few points. The room's own range is
    applied on top when it lands (see Feelings) — this bounds the step, that
    bounds the ceiling. `reason` is required: a number nobody can explain is a bug
    nobody can find.
    """

    stat: Literal["drunkenness", "confidence", "fun"]
    delta: int = Field(ge=-15, le=15)
    reason: str


# --- The action space: one class per verb, told apart by `type`. --------------
# Each verb carries only its own parameters, so the model physically cannot emit
# an approach without someone to approach and something to say.


class GoTo(BaseModel):
    type: Literal["go_to"]
    # A kind of place, never coordinates. The room resolves it to somewhere to stand.
    spot: Literal["bar", "couch", "window", "snack", "floor"]

    def remembered(self) -> str:
        return f"You headed to the {self.spot}."


class GoDrink(BaseModel):
    type: Literal["go_drink"]

    def remembered(self) -> str:
        return "You went to get a drink."


class Approach(BaseModel):
    type: Literal["approach"]
    # A name, because a name is all a guest ever perceives of anybody else. The
    # guest list guarantees a name points at exactly one person.
    target_name: str
    # The line they open with. Consent needs words on the table: an approach with
    # nothing said leaves the other person judging nothing.
    opener: str

    def remembered(self) -> str:
        return f'You approached {self.target_name}: "{self.opener}"'


class Reply(BaseModel):
    type: Literal["reply_in_conversation"]
    text: str

    def remembered(self) -> str:
        return f'You said: "{self.text}"'


class Leave(BaseModel):
    type: Literal["leave_conversation"]

    def remembered(self) -> str:
        return "You left the conversation."


class Idle(BaseModel):
    type: Literal["idle"]

    def remembered(self) -> str:
        return "You stayed put."


Action = Annotated[
    Union[GoTo, GoDrink, Approach, Reply, Leave, Idle],
    Field(discriminator="type"),
]

# The room promises these are the same list. Say so out loud, once, at import.
assert set(get_args(GoTo.model_fields["spot"].annotation)) == set(room.KINDS)


class Decision(BaseModel):
    """One whole thought: why, how it felt, and what it does about it.

    `reasoning` comes first on purpose. A model fills fields in the order they are
    declared, so putting free text before the structured commitments makes it
    think before it chooses — and gives us the only honest record of *why* an
    agent did something. Declared last, it would be a rationalisation of a choice
    already made.
    """

    reasoning: str
    deltas: list[StatDelta]
    action: Action

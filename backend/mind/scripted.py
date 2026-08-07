"""A mind with nothing behind it — the party without the language model.

It answers the same two questions a real Mind answers, from the same Situation,
and returns decisions that pass the same schema. So swapping it in exercises
every part of the party except the model call itself: the dispatcher, the
approach handshake, the conversation turn-taking, the debug panel, the wire.

Useful for running the party for free, for seeing the shell work while a local
model is cold, and for reading what the machinery does without a network in the
way. It is not trying to be convincing.
"""

from __future__ import annotations

import random

from backend.mind.decision import (
    Approach,
    Decision,
    GoDrink,
    GoTo,
    Idle,
    Leave,
    Reply,
    StatDelta,
)
from backend.mind.situation import Situation
from backend import trigger

OPENERS = [
    "Hey! Great party, right?",
    "Oh, hi there. Having fun?",
    "Didn't expect to see you tonight.",
    "Hey, you made it!",
    "This party's pretty good so far.",
]
REPLIES = [
    "Yeah, totally.",
    "Ha, fair point.",
    "I'm just here for the snacks, honestly.",
    "Same here.",
    "Tell me about it.",
    "Wait, tell me more.",
]
TIPSY = [
    "Wooo, yeah!! Love that.",
    "Okay honestly? Best party ever.",
    "Wait, what were we talking about.",
    "I love everyone here right now.",
]
SHY = [
    "Oh, um, yeah I guess.",
    "Sorry, I'm not great at parties.",
    "That's... nice.",
    "I've kind of been standing here a while.",
]

# How long a scripted chat runs before it starts looking for the door. The real
# cap lives with the conversation; this is just a mind that gets bored sooner.
ENOUGH_TURNS = 6


class ScriptedMind:
    def __init__(self, seed: int | None = None) -> None:
        self.rng = random.Random(seed)

    async def decide(self, situation: Situation) -> Decision:
        action = self.choose(situation)
        return Decision(
            reasoning=f"(scripted) reacting to: {situation.just_happened}",
            deltas=self.feel_about(situation),
            action=action,
        )

    async def small_talk(self, situation: Situation) -> str:
        """A canned line, picked by how the guest is doing rather than by what was
        actually said — which is exactly the limit of a mind with no model."""
        return self.rng.choice(self.register(situation))

    # ---- what to do ------------------------------------------------------

    def choose(self, situation: Situation):
        """One verb, chosen from what just happened."""
        match situation.because:
            case trigger.WasApproached():
                return self.judge_an_opener(situation)
            case trigger.PartnerSpoke():
                return self.take_a_turn(situation)
            case trigger.Arrived(spot="bar"):
                return GoTo(type="go_to", spot="floor")
            case _:
                return self.find_something_to_do(situation)

    def judge_an_opener(self, situation: Situation):
        """Most openers land. The ones that don't are what makes the decline path
        worth having."""
        if self.rng.random() < 0.75:
            return Reply(type="reply_in_conversation",
                         text=self.rng.choice(self.register(situation)))
        return GoTo(type="go_to", spot="floor")

    def take_a_turn(self, situation: Situation):
        said_so_far = len(situation.transcript or [])
        if said_so_far >= ENOUGH_TURNS and self.rng.random() < 0.5:
            return Leave(type="leave_conversation")
        return Reply(type="reply_in_conversation",
                     text=self.rng.choice(self.register(situation)))

    def find_something_to_do(self, situation: Situation):
        """Nothing is happening, so: talk to somebody, get a drink, or wander."""
        free = [other["name"] for other in situation.room if other["available"]]
        if free and self.rng.random() < 0.5:
            return Approach(type="approach",
                            target_name=self.rng.choice(free),
                            opener=self.rng.choice(OPENERS))
        if situation.feelings.get("drunkenness", 0) < 60 and self.rng.random() < 0.4:
            return GoDrink(type="go_drink")
        if self.rng.random() < 0.15:
            return Idle(type="idle")
        return GoTo(type="go_to",
                    spot=self.rng.choice(["couch", "window", "snack", "floor"]))

    # ---- how it felt -----------------------------------------------------

    def feel_about(self, situation: Situation) -> list[StatDelta]:
        match situation.because:
            case trigger.Arrived(spot="bar"):
                return [StatDelta(stat="drunkenness", delta=8, reason="had a drink")]
            case trigger.PartnerSpoke() | trigger.WasApproached():
                return [StatDelta(stat="fun", delta=4, reason="someone's talking to me")]
            case trigger.ApproachDeclined():
                return [StatDelta(stat="confidence", delta=-6, reason="that stung")]
            case trigger.Bored():
                return [StatDelta(stat="fun", delta=-3, reason="nothing is happening")]
            case _:
                return []

    # ---- how they'd say it -----------------------------------------------

    def register(self, situation: Situation) -> list[str]:
        """Which pile of canned lines suits the state they're in."""
        if situation.feelings.get("drunkenness", 0) > 60:
            return TIPSY
        if situation.feelings.get("confidence", 0) < -20:
            return SHY
        return REPLIES

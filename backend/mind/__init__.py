"""Thinking: what a guest is told, what they may answer, and who answers it.

    situation.py   what a mind is told        (the input contract)
    decision.py    what a mind may answer     (the output contract, and the
                                               trust boundary — it's model text)
    mind.py        the one call to a model
    scripted.py    the same two answers, with no model behind them

Nothing outside this package knows what a prompt looks like.
"""

from backend.mind.decision import Decision
from backend.mind.mind import Mind
from backend.mind.scripted import ScriptedMind
from backend.mind.situation import Situation

__all__ = ["Decision", "Mind", "ScriptedMind", "Situation"]

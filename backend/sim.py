"""Real simulation (work in progress).

Same world *and* same guest list as StubSim — it inherits everything from
BaseSim: the physics, the snapshot format, and loading agents from agents.json
at init. The only thing left to build is the brain: `decision_step`, `open_chat`
and `user_message` are the seams where the LLM planner slots in, and until then
they inherit BaseSim's NotImplementedError stubs.
"""

from __future__ import annotations

from backend.base_sim import BaseSim


class Sim(BaseSim):
    # Everything is inherited. decision_step / open_chat / user_message stay
    # unimplemented (raising stubs from BaseSim) until the real planner lands.
    pass

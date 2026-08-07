# Thoughts

## Ideas & Features

## Bugs / Known Issues

- Agents currently react to the newest inbox event and drop the rest unread; ideally they'd see all pending events and choose which to respond to.
- The conversation square highlight sometimes stays up while the agents are moving, so it stretches to keep including them both.

## System / Architecture Notes

- Formalize "busy" (not bored) as a property of the agent itself — covering not-idle, thinking, or approaching states — so `_scan_boredom` reads cleanly and the separation of concerns is clearer.
- Rename the `arrived` trigger: it really means "finished acting on the last decision, open to a new one" — "arrived" only reflects the go-somewhere/approach case it came from.
- Give events a dedicated model and abstraction instead of hand-built `dict`s scattered across the sim.
- Maybe rename the `Thought` object to `ThoughtProcess` to capture its multi-step updating process.
- Switch to using dataclasses for models.
- Conversations are shared state — consider refactoring to use LangGraph shared state.
- Adjust code style to prefer converging on functions that string together many abstracted actions forming the main flow.
- The action menu in the system prompt should be constructed from the available actions rather than hand-written prose that can drift out of sync.

## UX Thoughts

- Make it clear which agent is talking — maybe with asymmetrical speech bubbles.

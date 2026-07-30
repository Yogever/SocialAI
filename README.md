# SocialAI — AI Social Party Simulator

A Sims-style house party where the guests are autonomous agents. They arrive one
by one, wander a pixel-art room, drink, and strike up conversations — each driven
by a personality and a handful of stats. You watch the party unfold from above,
hover anyone to see how they're doing, or click to pause the party and chat with
them directly.

The point of the project is the **agentic layer** — per-tick decision making and
multi-agent conversations driven by personality and state. The current build
ships the full simulation *shell* with a stubbed brain; the LLM-backed decision
and dialogue logic slots in behind the same interfaces.

## Stats each agent carries

- **drunkenness** `0…100`
- **confidence** `-100…100`
- **fun** `-100…100`
- **attractiveness** `0…100`
- plus name and age

## Architecture

The system is split into an **authoritative Python backend** and a **thin browser
renderer**, talking over a single WebSocket.

- **Backend owns all world truth** — positions, stats, who's talking to whom.
  Nothing is "true" until the backend says so. Movement and collisions live here
  because they're inputs to agent decisions ("am I near someone to talk to?").
- **Frontend only renders** whatever the backend reports, and handles interaction
  (hover, click-to-chat). It never decides world state.

**Two backend rhythms run concurrently:**

- a fast, cheap **movement loop** (~30Hz) — advances positions toward targets and
  resolves collisions, no thinking;
- a slow **decision loop** (~seconds) — the "planner" that picks targets, forms
  and ends conversations, and (eventually) calls an LLM.

This is a deliberate *planner / controller* split: the slow loop sets intentions,
the fast loop executes them, so a slow decision never freezes the party.

**The wire contract has two kinds of message:**

- **State** (`world_state`) — latest-wins snapshots of every agent; the client
  interpolates between them for smooth motion, and a reconnecting client is
  instantly correct from the next snapshot.
- **Events** (`agent_spoke`, `conversation_started`/`_ended`, `agent_arrived`,
  `agent_drank`) — append-only, ordered things that *happened*; they feed the
  chat, the party log, and speech bubbles.

## Status

**Simulation shell complete, brain stubbed.** `backend/stub_sim.py` moves agents,
forms/ends conversations, and emits canned dialogue — but speaks the real wire
contract, so the frontend is built against something that behaves like the
eventual LLM backend. The next step is replacing the stub's `decision_step()`
with real per-agent LLM decisions and conversations.

The pixel art (procedural sprites + room, in `frontend/js/sprites.js`) and the
UI layout originated as a Claude Design mockup; only its *visuals* were kept, and
all simulation was moved into the authoritative backend.

## Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000 — agents trickle in and mingle. Hover an agent for
stats; click one to pause the party and chat.

## Layout

```
backend/
  main.py         # FastAPI: WebSocket + the two concurrent loops (transport/IO)
  base_sim.py     # shared world, physics, snapshot format (Template Method)
  sim.py          # the real brain: planner dispatcher + conversation orchestrator
  stub_sim.py     # fake party sim; pure logic, no IO (token-free stand-in)
  models.py       # Agent dataclass
  planner.py      # planner output schema (Pydantic; the trust boundary)
  context.py      # context assembly — what each agent knows (pure)
  planner_client.py  # build_messages (pure) + invoke (the one model call)
  debug_trace.py  # bounded ring of thought records (reasoning, deltas, errors)
frontend/
  index.html
  style.css
  js/
    app.js      # wiring
    net.js      # WebSocket client (receives state/events, sends intent)
    state.js    # authoritative world store (latest-wins) + render positions
    sprites.js  # procedural pixel-art sprites, room, and stat icons
    render.js   # DOM render loop + entity interpolation
    ui.js       # tooltip / chat drawer / party log / controls
    debug.js    # debug panel: per-agent reasoning, sim internals, step control
    util.js     # shared helpers
```

## Debugging the sim

Hit **Debug** in the top bar. The panel shows, per agent, the things the 30Hz
snapshot deliberately doesn't carry: personality and goal, the current
*intention* (not just position), private rolling memory, the trigger inbox, the
pending-approach limbo, and a stream of **thought records** — each with the
model's reasoning, every stat delta and its stated reason, latency, the verbatim
prompt, and the full error if the call failed. Click a guest in the room to
inspect them.

Pause the party and **Step** advances exactly one decision tick, so you can watch
one thought resolve at a time.

It's also readable without the browser:

```bash
curl -s localhost:8000/debug/state | jq        # internals + recent thoughts
curl -s localhost:8000/debug/thought/12 | jq   # one thought, with its prompt
```

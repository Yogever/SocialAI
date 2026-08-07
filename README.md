# SocialAI — AI Social Party Simulator

A Sims-style house party where the guests are autonomous agents. They arrive one
by one, wander a pixel-art room, drink, and strike up conversations — each driven
by a personality and a handful of stats. You watch the party unfold from above,
hover anyone to see how they're doing, or click to pause the party and chat with
them directly.

The point of the project is the **agentic layer** — per-tick decision making and
multi-agent conversations driven by personality and state.

## The party, explained top down

The code is written to read like this list, one abstraction level at a time. Each
line is explained by the lines indented under it, and every named thing is a
class in the same shape.

```
A Party is one evening, in one Room, with a handful of Guests.
  A Guest is an Identity, some Feelings, and a Body.
    An Identity is a name, an age, a personality and a goal — fixed for the night.
    Feelings are drunkenness, confidence and fun — each with a range it can't leave.
    A Body is a position and somewhere it is walking to.
  A Room is a set of Spots — bar, couch, window, snack, floor — and it keeps
    guests from standing inside each other.
  The party runs on two rhythms.
    Thirty times a second, bodies move. Nobody thinks.
    Every second and a half, whoever has something to react to reacts to it.
  A Guest thinks because something happened to them.
    That something is a Trigger, and it knows how to describe itself.
    Thinking is asking a Mind what this person does next.
      A Mind is handed a Situation and answers with a Decision.
      A Situation is everything the guest knows, and nothing they don't.
      A Decision is why, how it felt, and one action.
  Approaching someone is a handshake, not an order.
    You walk over, you say your line, and then they judge it.
    A reply means yes. Anything else means no.
  A Conversation is two guests taking turns.
    Each turn hands the partner something to react to, which produces the next
    turn — so there is no conversation loop anywhere, only the party's tick.
    It ends when someone leaves, or when it has run too many turns.
```

## Stats each guest carries

- **drunkenness** `0…100`
- **confidence** `-100…100`
- **fun** `-100…100`
- **attractiveness** `0…100` — the one others can read and nobody can change

## Architecture

An **authoritative Python backend** and a **thin browser renderer**, talking over
a single WebSocket.

- **The backend owns all world truth** — positions, stats, who's talking to whom.
  Nothing is true until the backend says so. Movement and collisions live there
  because they're inputs to decisions ("am I near someone to talk to?").
- **The browser only renders** what it is told, and handles interaction. It sends
  *intent* — pause, open a chat, say this — and never world state.

**Two rhythms run concurrently**, so a slow thought never freezes the party: a
cheap movement loop at ~30Hz, and a decision tick every ~1.5s. The tick is
`Party.decide()`, and it never awaits — thoughts run as separate tasks and a
running thought never writes to the world. Every change happens inside that one
method, which is why nothing in the party has to reason about interleaving.

**The wire carries two kinds of message:**

- **State** (`world_state`) — latest-wins snapshots; the client interpolates
  between them, and a reconnecting client is instantly correct again.
- **Events** (`agent_spoke`, `conversation_started`/`_ended`, `agent_drank`) —
  append-only, ordered things that *happened*; they feed the chat, the party log
  and the speech bubbles.

The browser was written against those names and calls a guest an "agent". The
backend calls it a guest. `backend/event.py` is the single place the two
vocabularies meet.

## Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# The guests think with Gemini 3.1 Flash-Lite — put a key in .env
uvicorn backend.main:app --env-file .env --reload
```

`.env` is gitignored and read by uvicorn, not by the code: everything in it is
plain environment, so exporting the same names by hand works identically.

Open http://127.0.0.1:8000 — guests trickle in and mingle. Hover one for stats;
click one to pause the party and talk to them. **The evening lasts 90 seconds**
(`LASTS` in `backend/hub.py`) and then stops for good; pausing doesn't spend it,
and running at 2× or 3× spends it faster than the wall clock.

Which mind the guests think with is a startup choice, not a code change:

```bash
PARTY_MIND=scripted uvicorn backend.main:app     # no model, no tokens
PARTY_MODEL=ollama:qwen2.5:7b uvicorn backend.main:app   # local, no API key
```

`ScriptedMind` answers the same two questions a real mind does, from the same
`Situation`, and returns decisions that pass the same schema — so it exercises
every part of the party except the model call. Useful for running it for free,
and for watching the machinery with no network in the way.

## Layout

```
backend/
  main.py           # the server: a socket, two debug routes, the browser's files
  hub.py            # one party, many spectators; the two rhythms
  party.py          # the whole simulated evening — the top-level concept
  guest.py          # Guest = Identity + Feelings + Body, plus memory and an inbox
  guest_list.py     # everyone at the party, and loading them from agents.json
  room.py           # Spots, and keeping bodies out of each other
  conversation.py   # Conversations, one Conversation, and the approach handshake
  trigger.py        # the eight things that make a guest think; each says itself
  thinking.py       # the thoughts in flight, and the two guards that bound them
  thought_log.py    # a bounded ring of what was thought and what it changed
  event.py          # things that happened, in the words the browser understands
  mind/
    situation.py    # what a mind is told      (input contract, + the RULES text)
    decision.py     # what a mind may answer   (output contract; the trust boundary)
    mind.py         # the one call to a model
    scripted.py     # the same two answers, with no model behind them
frontend/
  index.html
  style.css
  js/
    app.js          # wiring: the only file that knows all the pieces exist
    connection.js   # the socket: messages in, intent out
    world.js        # the party as the backend last described it
    viewer.js       # what this browser is showing (hover, drawers, lights)
    room.js         # the room on screen: sprites, rings, bubbles, tooltip
    sprites.js      # procedural pixel art — guests, the room, the stat icons
    stats.js        # the four stat bars, shared by tooltip and chat
    controls.js     # the top bar
    log.js          # the party log
    chat.js         # the chat drawer
    debug.js        # the debug panel
    guest_detail.js # one guest, as the panel shows them
    thought.js      # one thought, as the panel shows it
    html.js         # escaping
```

## Debugging the party

Hit **Debug** in the top bar. The panel shows, per guest, everything the 30Hz
snapshot deliberately doesn't carry: personality and goal, the current
*intention* (not just the position), private memory, the trigger inbox, the
approach limbo, and a stream of **thoughts** — each with the model's reasoning,
every change to a feeling and its stated reason, latency, the verbatim prompt,
and the full error if the call failed. Click a guest in the room to inspect them.

Pause the party and **Step** advances exactly one decision tick, so you can watch
one thought resolve at a time.

It's also readable without a browser:

```bash
curl -s localhost:8000/debug/state | jq        # internals + recent thoughts
curl -s localhost:8000/debug/thought/12 | jq   # one thought, with its prompt
```

## A note on the design records

`docs/` holds the design history, written against the previous structure: it
refers to a `Sim`, an `Agent`, a `planner` and decisions numbered D1–D12. The
reasoning still holds; the names moved.

| docs say | the code says |
| --- | --- |
| `Sim` / the controller | `Party` |
| `Agent` | `Guest` (`Identity` + `Feelings` + `Body`) |
| the planner / `PlannerDecision` | `Mind` / `Decision` |
| context assembly | `Situation` |
| the dispatcher (D11) | `Thinking` |
| triggers in inboxes (D12) | `Trigger`, `News`, `Guest.inbox` |
| `PendingApproach` (D7) | `Approach` |
| `StubSim` | `ScriptedMind` |
| `ThoughtRecord` / `DebugTrace` | `Thought` / `ThoughtLog` |

`CLAUDE.md` describes the abstraction-based style the code is written in.

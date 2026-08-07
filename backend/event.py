"""Things that happened, in the words the browser understands.

The wire carries two kinds of message and they behave differently on purpose:

    state   a full snapshot of everyone, latest-wins — a client that misses one
            is fine, because the next one is the whole truth again
    events  append-only, ordered things that *happened* — the party log, the
            speech bubbles, the chat

These are the events. They are built here, in one place, because the browser was
written against these exact names (docs/architecture.md) and still calls a guest
an "agent". That is the one vocabulary difference in the project, and this module
is where the two sides of it meet. The tick each event carries is stamped on by
the party when it hands them out — nothing down here needs to know the time.
"""

from __future__ import annotations


def spoke(guest, text: str, conversation_id: str | None) -> dict:
    """Somebody said something. A conversation id means it belongs in a bubble
    over the party; no id means it belongs in the chat drawer."""
    return {
        "type": "agent_spoke",
        "agent_id": guest.id,
        "conversation_id": conversation_id,
        "text": text,
    }


def drank(guest) -> dict:
    return {"type": "agent_drank", "agent_id": guest.id, "name": guest.name}


def conversation_started(conversation) -> dict:
    return {
        "type": "conversation_started",
        "conversation_id": conversation.id,
        "participants": [guest.id for guest in conversation.between],
        "names": [guest.name for guest in conversation.between],
    }


def conversation_ended(conversation) -> dict:
    return {
        "type": "conversation_ended",
        "conversation_id": conversation.id,
        "participants": [guest.id for guest in conversation.between],
        "names": [guest.name for guest in conversation.between],
    }


def party_ended(lasted: float) -> dict:
    """The evening ran its length. The only event nobody at the party caused —
    after it, nothing moves and nothing thinks."""
    return {"type": "party_ended", "lasted": round(lasted)}

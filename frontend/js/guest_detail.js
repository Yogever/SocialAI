// One guest, as the debug panel shows them.
//
// Everything here is something the thirty-per-second snapshot deliberately
// doesn't carry, and that is the whole reason this panel exists. The room view
// can tell you where somebody is. It cannot tell you what they are, what they
// were trying to do, what they still remember, or that the person standing
// perfectly still is in fact waiting to be told whether they've been rebuffed.

import { text } from "./html.js";

export function detailHtml(guest, internals) {
  const parts = [
    row("personality", text(guest.personality || "—")),
    guest.goal ? row("goal", text(guest.goal)) : "",
    row("doing", intention(guest)),
    guest.approach ? row("approach", approachHtml(guest.approach)) : "",
    row("stats", statsLine(guest.stats)),
    row("state", state(guest)),
    guest.inbox.length ? row("inbox", inbox(guest)) : "",
    conversationRow(guest, internals),
    row("memory", memory(guest)),
  ];
  return `<div class="dbg-detail"><div class="dbg-who">${text(guest.name)}`
    + `<span class="dim">age ${text(guest.age)}</span></div>${parts.join("")}</div>`;
}

export function hintHtml() {
  return `<div class="dbg-empty">Click a guest in the room — or a name above — to`
    + ` see their identity, intention, memory and reasoning.</div>`;
}

function row(key, value) {
  return `<div class="dbg-kv"><span class="k">${key}</span><span class="v">${value}</span></div>`;
}

function intention(guest) {
  // Where they're heading and why. The snapshot ships only where they *are*.
  return `${text(guest.action)} → ${text(guest.target_type)}`
    + ` <span class="dim">[${guest.target[0]}, ${guest.target[1]}]</span>`;
}

function approachHtml(approach) {
  const phases = {
    walking_over: `walking over to ${approach.who}`,
    awaiting_consent: `waiting on ${approach.who} to accept`,
    owes_consent: `must answer ${approach.who}`,
    incoming: `${approach.who} is walking over`,
  };
  return `<span class="dbg-warn">${text(phases[approach.state] ?? approach.state)}</span>`
    + `<div class="quote">${text(approach.opener)}</div>`;
}

function statsLine(stats) {
  return Object.entries(stats)
    .map(([name, value]) => `<span class="dbg-stat">${text(name.slice(0, 4))}`
      + ` <b>${text(value)}</b></span>`)
    .join(" ");
}

function state(guest) {
  if (guest.thinking) return `<span class="dbg-live">thinking…</span>`;
  if (guest.action === "idle") {
    return `idle — boredom re-plan in ${guest.ticks_until_boredom} tick(s)`;
  }
  return text(guest.action);
}

function inbox(guest) {
  // Only the newest survives; the dispatcher clears the rest unread.
  const queued = guest.inbox.map((kind, i) => {
    const newest = i === guest.inbox.length - 1;
    return `<span class="${newest ? "dbg-live" : "dim strike"}">${text(kind)}</span>`;
  }).join(", ");
  const caveat = guest.inbox.length > 1
    ? ` <span class="dim">(only the last is read)</span>` : "";
  return queued + caveat;
}

function conversationRow(guest, internals) {
  const talking = internals.conversations.find((c) => c.id === guest.conversation_id);
  if (!talking) return "";
  return row("talking",
    `${text(talking.names.join(" + "))} <span class="dim">`
    + `turn ${talking.turn_count}/${talking.cap}, `
    + `${text(talking.speaker_name || "?")} to speak</span>`
    + `<div class="dbg-transcript">`
    + talking.transcript.map((line) => `<div>${text(line)}</div>`).join("")
    + `</div>`);
}

function memory(guest) {
  // The actual prose fed into the next prompt, not a UI log of it.
  if (!guest.memory.length) return "—";
  return `<div class="dbg-memory">`
    + guest.memory.map((line) => `<div>${text(line)}</div>`).join("")
    + `</div>`;
}

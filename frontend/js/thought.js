// One thought, as the debug panel shows it.
//
// A decision is required to explain itself before it commits to anything — the
// reasoning is generated before the action, and every change to a feeling comes
// with a reason — so this is not a reconstruction of why a guest acted. It is
// the guest's own account of it, in the order they thought it.
//
// The prompt is fetched only when asked for. The panel polls a page of these
// twice a second, and a prompt is a couple of kilobytes of mostly-identical
// rules text.

import { text } from "./html.js";

const opened = new Set();     // seqs whose prompt is showing
const fetched = new Map();    // seq -> the full record, once it has been asked for

export function openPrompts() {
  return [...opened];
}

export async function togglePrompt(seq) {
  if (opened.has(seq)) {
    opened.delete(seq);
    return;
  }
  opened.add(seq);
  if (fetched.has(seq)) return;
  try {
    const response = await fetch(`/debug/thought/${seq}`);
    if (response.ok) fetched.set(seq, await response.json());
  } catch {
    // Leave it looking unopened; the next click tries again.
  }
}

export function thoughtHtml(thought) {
  const parts = [
    headline(thought),
    waiting(thought),
    failure(thought),
    // The event exactly as the guest read it — the literal `just_happened` line.
    `<div class="dbg-event">${text(thought.event_str)}</div>`,
    thought.reasoning ? `<div class="quote">${text(thought.reasoning)}</div>` : "",
    saidAloud(thought),
    feelings(thought),
    consent(thought),
    missed(thought),
    `<button class="dbg-promptbtn">`
      + `${opened.has(thought.seq) ? "hide" : "prompt"}</button>`,
    prompt(thought),
  ];
  const mood = thought.status === "failed" ? "bad"
    : thought.status === "in_flight" ? "live" : "";
  return `<div class="dbg-thought ${mood}" data-seq="${thought.seq}">`
    + parts.join("") + `</div>`;
}

function headline(thought) {
  const took = thought.latency_ms == null ? ""
    : `<span class="dbg-lat">${duration(thought.latency_ms)}</span>`;
  return `<div class="dbg-t-head">`
    + `<span class="dbg-tick">t${thought.tick_spawned}</span>`
    + `<span class="dbg-name">${text(thought.agent_name)}</span>`
    + `<span class="dbg-trigger">${text(thought.trigger_kind)}</span>`
    + `<span class="dbg-arrow">→</span>`
    + `<span class="dbg-action">${text(verb(thought.action))}</span>`
    + took + `</div>`;
}

function waiting(thought) {
  if (thought.status !== "in_flight") return "";
  return `<div class="dbg-live">waiting on the model…</div>`;
}

function failure(thought) {
  if (thought.status !== "failed" || !thought.error) return "";
  return `<div class="dbg-bad">${text(thought.error.type)}: `
    + `${text(thought.error.message)}</div>`;
}

function saidAloud(thought) {
  const words = spoken(thought.action);
  return words ? `<div class="dbg-said">“${text(words)}”</div>` : "";
}

function feelings(thought) {
  if (!thought.deltas?.length) return "";
  return `<div class="dbg-deltas">` + thought.deltas.map((delta) =>
    `<span class="dbg-delta ${delta.delta >= 0 ? "up" : "down"}">`
    + `${text(delta.stat)} ${delta.delta >= 0 ? "+" : ""}${delta.delta}</span>`
    + `<span class="dim">${text(delta.reason)}</span>`
  ).join("") + `</div>`;
}

function consent(thought) {
  if (thought.gate !== "consent") return "";
  return `<div class="dbg-tag" title="judged as the answer to an approach, not`
    + ` carried out as an ordinary action">consent decision</div>`;
}

function missed(thought) {
  if (!thought.dropped_triggers?.length) return "";
  return `<div class="dbg-warn" title="cleared unread by the dispatcher">`
    + `never saw: ${text(thought.dropped_triggers.join(", "))}</div>`;
}

function prompt(thought) {
  if (!opened.has(thought.seq)) return "";
  const full = fetched.get(thought.seq);
  if (!full) return `<pre class="dbg-pre">loading…</pre>`;
  const sent = full.prompt
    ? `SYSTEM\n${full.prompt.system}\n\nHUMAN\n${full.prompt.human}`
    : "(prompt not captured)";
  const trace = full.error?.traceback ? `\n\nTRACEBACK\n${full.error.traceback}` : "";
  return `<pre class="dbg-pre">${text(sent + trace)}</pre>`;
}

// --- reading an action ------------------------------------------------------

function verb(action) {
  if (!action) return "…";
  switch (action.type) {
    case "go_to": return `go_to ${action.spot}`;
    case "approach": return `approach ${action.target_name}`;
    case "reply_in_conversation": return "reply";
    case "leave_conversation": return "leave";
    default: return action.type;
  }
}

function spoken(action) {
  if (!action) return "";
  if (action.type === "approach") return action.opener;
  if (action.type === "reply_in_conversation") return action.text;
  return "";
}

function duration(ms) {
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

// Debug panel: what each agent is thinking, and why nothing is happening.
//
// Self-contained on purpose. It polls `/debug/state` over HTTP rather than riding
// the WebSocket — the socket carries world truth at 30Hz for every client, and
// this is introspection wanted a couple of times a second by one of them (see
// docs/architecture.md). It also means the render loop and the party UI don't
// change shape just because a debug view exists.
//
// Imports only state/net/util, never ui.js, so there's no import cycle: the panel
// draws its own compact stat rows instead of borrowing the pixel-art ones.

import { ui } from "./state.js";
import { send } from "./net.js";
import { escapeHtml } from "./util.js";

const POLL_MS = 500;       // the sim decides every ~1500ms; this is comfortably ahead
const THOUGHT_LIMIT = 80;

const app = document.getElementById("app");
const panel = document.getElementById("debugPanel");
const debugBtn = document.getElementById("debugBtn");
const stepBtn = document.getElementById("stepBtn");
const vitalsEl = document.getElementById("dbgVitals");
const agentsEl = document.getElementById("dbgAgents");
const detailEl = document.getElementById("dbgDetail");
const thoughtsEl = document.getElementById("dbgThoughts");

let timer = null;
let state = null;
const expanded = new Set();          // thought seqs whose prompt is open
const prompts = new Map();           // seq -> full record (fetched on expand)
let sigDetail = "";                  // skip re-render when nothing changed, so
let sigThoughts = "";                // scrolling and text selection survive polls

// --- open / close ---------------------------------------------------------

export function initDebug() {
  debugBtn.addEventListener("click", () => setOpen(!ui.debugOpen));
  stepBtn.addEventListener("click", () => send({ type: "step" }));

  // One delegated listener for the whole panel: rows are re-rendered constantly,
  // so per-row handlers would have to be re-attached every poll.
  panel.addEventListener("click", (e) => {
    const chip = e.target.closest("[data-agent]");
    if (chip) { selectAgent(chip.dataset.agent); return; }
    const row = e.target.closest("[data-seq]");
    if (row && e.target.closest(".dbg-promptbtn")) togglePrompt(Number(row.dataset.seq));
  });
}

function setOpen(open) {
  ui.debugOpen = open;
  panel.classList.toggle("hidden", !open);
  app.classList.toggle("debugging", open);
  debugBtn.classList.toggle("on", open);
  stepBtn.classList.toggle("hidden", !open);
  clearInterval(timer);
  timer = null;
  if (open) {
    poll();
    timer = setInterval(poll, POLL_MS);
  }
}

export function selectAgent(id) {
  ui.debugAgentId = ui.debugAgentId === id ? null : id;
  sigDetail = sigThoughts = "";       // force a redraw at the new selection
  render();
}

// --- polling -------------------------------------------------------------

async function poll() {
  try {
    const res = await fetch(`/debug/state?limit=${THOUGHT_LIMIT}`);
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    state = await res.json();
    render();
  } catch (err) {
    vitalsEl.innerHTML = `<span class="dbg-bad">debug unavailable — ${escapeHtml(err.message)}</span>`;
  }
}

async function togglePrompt(seq) {
  if (expanded.has(seq)) {
    expanded.delete(seq);
  } else {
    expanded.add(seq);
    if (!prompts.has(seq)) {
      try {
        const res = await fetch(`/debug/thought/${seq}`);
        if (res.ok) prompts.set(seq, await res.json());
      } catch { /* leave it unexpanded-looking; next click retries */ }
    }
  }
  sigThoughts = "";
  render();
}

// --- render --------------------------------------------------------------

function render() {
  if (!state) return;
  const d = state;

  stepBtn.disabled = !d.paused;
  stepBtn.title = d.paused
    ? "Advance one decision tick"
    : "Pause the party first — stepping only makes sense while it's frozen";

  // Vitals. `starved` and the thinking count are the two numbers that explain a
  // party that looks frozen: calls in flight, or agents that lost the dispatcher
  // race and are holding a trigger nobody will read this tick.
  const bits = [
    `<span class="k">tick</span> ${d.tick}`,
    `<span class="k">thinking</span> ${d.thinking.length}/${d.knobs.max_concurrent}`,
    `<span class="k">convs</span> ${d.conversations.length}`,
  ];
  if (d.failures) bits.push(`<span class="dbg-bad">${d.failures} failed</span>`);
  if (d.starved.length) {
    bits.push(`<span class="dbg-warn" title="had a trigger but lost to the concurrency cap">`
      + `starved ${d.starved.length}</span>`);
  }
  if (d.paused) bits.push(`<span class="dbg-warn">paused</span>`);
  vitalsEl.innerHTML = bits.join('<span class="sep">·</span>');

  agentsEl.innerHTML = d.agents.map(a => chip(a)).join("");

  const sel = d.agents.find(a => a.id === ui.debugAgentId) || null;
  const nextDetail = JSON.stringify([sel, d.conversations, d.tick]);
  if (nextDetail !== sigDetail) {
    sigDetail = nextDetail;
    detailEl.innerHTML = sel ? detail(sel, d) : hint();
  }

  const list = sel ? d.thoughts.filter(t => t.agent_id === sel.id) : d.thoughts;
  const nextThoughts = JSON.stringify([list, [...expanded]]);
  if (nextThoughts !== sigThoughts) {
    sigThoughts = nextThoughts;
    thoughtsEl.innerHTML =
      `<div class="dbg-section">${sel ? `${escapeHtml(sel.name)}'s thoughts` : "all thoughts"}`
      + `<span class="dbg-count">${list.length}</span></div>`
      + (list.length ? list.map(thought).join("") : `<div class="dbg-empty">nothing yet</div>`);
  }
}

function chip(a) {
  const on = a.id === ui.debugAgentId;
  const mark = a.thinking ? "◌"
    : a.approach ? "→"
    : a.conversation_id ? "◈"
    : a.action === "walking" ? "»"
    : "·";
  return `<button class="dbg-chip${on ? " on" : ""}" data-agent="${escapeHtml(a.id)}"`
    + ` title="${escapeHtml(a.action)}">${mark} ${escapeHtml(a.name)}</button>`;
}

function hint() {
  return `<div class="dbg-empty">Click a guest in the room — or a name above — to see`
    + ` their identity, intention, memory and reasoning.</div>`;
}

function detail(a, d) {
  const rows = [];

  rows.push(kv("personality", a.personality || "—"));
  if (a.goal) rows.push(kv("goal", a.goal));

  // The intention. The 30Hz snapshot ships `pos` only, so "where is it heading and
  // why" is precisely what the party screen cannot answer.
  rows.push(kv("doing", `${a.action} → ${a.target_type}`
    + ` <span class="dim">[${a.target[0]}, ${a.target[1]}]</span>`));

  // The D7 limbo. An agent parked mid-approach has action "idle", so on the room
  // view it is indistinguishable from someone genuinely doing nothing.
  if (a.approach) {
    const p = a.approach;
    const label = p.role === "approacher"
      ? (p.state === "walking_over"
          ? `walking over to ${p.who}`
          : `waiting on ${p.who} to accept`)
      : (p.state === "owes_consent"
          ? `must answer ${p.who}`
          : `${p.who} is walking over`);
    rows.push(kv("approach", `<span class="dbg-warn">${escapeHtml(label)}</span>`
      + `<div class="quote">${escapeHtml(p.opener)}</div>`));
  }

  rows.push(kv("stats", statsLine(a.stats)));

  if (a.thinking) {
    rows.push(kv("state", `<span class="dbg-live">thinking…</span>`));
  } else if (a.action === "idle") {
    rows.push(kv("state", `idle — boredom re-plan in ${a.ticks_until_boredom} tick(s)`));
  }

  if (a.inbox.length) {
    // Only the newest survives; the dispatcher clears the rest unread.
    const queued = a.inbox.map((k, i) =>
      `<span class="${i === a.inbox.length - 1 ? "dbg-live" : "dim strike"}">${escapeHtml(k)}</span>`
    ).join(", ");
    rows.push(kv("inbox", queued + (a.inbox.length > 1
      ? ` <span class="dim">(only the last is read)</span>` : "")));
  }

  const conv = d.conversations.find(c => c.id === a.conversation_id);
  if (conv) {
    rows.push(kv("talking",
      `${escapeHtml(conv.names.join(" + "))} <span class="dim">turn ${conv.turn_count}/${conv.cap}`
      + `, ${escapeHtml(conv.speaker_name || "?")} to speak</span>`
      + `<div class="dbg-transcript">`
      + conv.transcript.map(l => `<div>${escapeHtml(l)}</div>`).join("")
      + `</div>`));
  }

  // The prose actually fed to the next prompt — not a UI log, the real memory.
  rows.push(kv("memory", a.memory.length
    ? `<div class="dbg-memory">${a.memory.map(m =>
        `<div>${escapeHtml(m)}</div>`).join("")}</div>`
    : "—"));

  return `<div class="dbg-detail"><div class="dbg-who">${escapeHtml(a.name)}`
    + `<span class="dim">age ${a.age}</span></div>${rows.join("")}</div>`;
}

function kv(k, v) {
  return `<div class="dbg-kv"><span class="k">${k}</span><span class="v">${v}</span></div>`;
}

function statsLine(stats) {
  return Object.entries(stats)
    .map(([k, v]) => `<span class="dbg-stat">${escapeHtml(k.slice(0, 4))}`
      + ` <b>${v}</b></span>`)
    .join(" ");
}

// --- one thought ---------------------------------------------------------

function thought(t) {
  const cls = t.status === "failed" ? "bad" : t.status === "in_flight" ? "live" : "";
  const lat = t.latency_ms == null ? "" : `<span class="dbg-lat">${fmtMs(t.latency_ms)}</span>`;

  const head = `<div class="dbg-t-head">`
    + `<span class="dbg-tick">t${t.tick_spawned}</span>`
    + `<span class="dbg-name">${escapeHtml(t.agent_name)}</span>`
    + `<span class="dbg-trigger">${escapeHtml(t.trigger_kind)}</span>`
    + `<span class="dbg-arrow">→</span>`
    + `<span class="dbg-action">${escapeHtml(actionText(t.action))}</span>`
    + lat + `</div>`;

  const parts = [head];

  if (t.status === "in_flight") {
    parts.push(`<div class="dbg-live">waiting on the model…</div>`);
  }
  if (t.status === "failed" && t.error) {
    parts.push(`<div class="dbg-bad">${escapeHtml(t.error.type)}: `
      + `${escapeHtml(t.error.message)}</div>`);
  }
  // The event as the agent read it — the literal `just_happened` string.
  parts.push(`<div class="dbg-event">${escapeHtml(t.event_str)}</div>`);

  // Reasoning: the whole point. Generated before the action by schema order, so
  // it's the model's actual deliberation, not a post-hoc justification.
  if (t.reasoning) parts.push(`<div class="quote">${escapeHtml(t.reasoning)}</div>`);

  const said = spoken(t.action);
  if (said) parts.push(`<div class="dbg-said">“${escapeHtml(said)}”</div>`);

  if (t.deltas && t.deltas.length) {
    parts.push(`<div class="dbg-deltas">` + t.deltas.map(dd =>
      `<span class="dbg-delta ${dd.delta >= 0 ? "up" : "down"}">`
      + `${escapeHtml(dd.stat)} ${dd.delta >= 0 ? "+" : ""}${dd.delta}</span>`
      + `<span class="dim">${escapeHtml(dd.reason)}</span>`
    ).join("") + `</div>`);
  }

  if (t.gate === "consent") {
    parts.push(`<div class="dbg-tag" title="judged as an answer to an approach (D7),`
      + ` not executed as an ordinary action">consent decision</div>`);
  }
  if (t.dropped_triggers && t.dropped_triggers.length) {
    parts.push(`<div class="dbg-warn" title="cleared unread by the dispatcher">`
      + `never saw: ${escapeHtml(t.dropped_triggers.join(", "))}</div>`);
  }

  parts.push(`<button class="dbg-promptbtn">`
    + `${expanded.has(t.seq) ? "hide" : "prompt"}</button>`);

  if (expanded.has(t.seq)) {
    const full = prompts.get(t.seq);
    parts.push(full
      ? `<pre class="dbg-pre">${escapeHtml(full.prompt
          ? `SYSTEM\n${full.prompt.system}\n\nHUMAN\n${full.prompt.human}`
          : "(prompt not captured)")}`
        + (full.error?.traceback
            ? escapeHtml(`\n\nTRACEBACK\n${full.error.traceback}`) : "")
        + `</pre>`
      : `<pre class="dbg-pre">loading…</pre>`);
  }

  return `<div class="dbg-thought ${cls}" data-seq="${t.seq}">${parts.join("")}</div>`;
}

function actionText(act) {
  if (!act) return "…";
  switch (act.type) {
    case "go_to": return `go_to ${act.spot}`;
    case "approach": return `approach ${act.target_name}`;
    case "reply_in_conversation": return "reply";
    case "leave_conversation": return "leave";
    default: return act.type;
  }
}

function spoken(act) {
  if (!act) return "";
  return act.type === "approach" ? act.opener
    : act.type === "reply_in_conversation" ? act.text
    : "";
}

function fmtMs(ms) {
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

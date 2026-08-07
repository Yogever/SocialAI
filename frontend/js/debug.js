// The debug panel: what every guest is thinking, and why nothing is happening.
//
// It polls an HTTP route instead of riding the socket, on purpose. The socket
// carries world truth thirty times a second to every browser watching; this is
// introspection wanted twice a second by one of them. Kept off the socket it
// costs the fast path nothing, and it can be read with curl and no browser at
// all.
//
// The panel is redrawn from a poll, so it compares what it is about to draw with
// what is already there and leaves it alone when nothing changed — otherwise
// scrolling and text selection would be wiped twice a second.

import { ask } from "./connection.js";
import { viewer } from "./viewer.js";
import { text } from "./html.js";
import { detailHtml, hintHtml } from "./guest_detail.js";
import { openPrompts, thoughtHtml, togglePrompt } from "./thought.js";

const EVERY_MS = 500;        // the party decides every ~1500ms; comfortably ahead
const THOUGHTS = 80;

const app = document.getElementById("app");
const panel = document.getElementById("debugPanel");
const openButton = document.getElementById("debugBtn");
const stepButton = document.getElementById("stepBtn");
const vitalsBar = document.getElementById("dbgVitals");
const chipsBar = document.getElementById("dbgAgents");
const detailPane = document.getElementById("dbgDetail");
const thoughtsPane = document.getElementById("dbgThoughts");

let polling = null;
let internals = null;
// What each pane was last drawn from. Kept so a poll that changed nothing leaves
// the pane — and anything selected or scrolled inside it — completely alone.
const drawnFrom = { detail: "", thoughts: "" };

export function arm() {
  openButton.addEventListener("click", () => setOpen(!viewer.debugging));
  stepButton.addEventListener("click", () => ask({ type: "step" }));

  // One listener for the whole panel: its rows are rebuilt on every poll, so
  // per-row handlers would have to be re-attached just as often.
  panel.addEventListener("click", async (clicked) => {
    const chip = clicked.target.closest("[data-agent]");
    if (chip) return inspect(chip.dataset.agent);
    const row = clicked.target.closest("[data-seq]");
    if (row && clicked.target.closest(".dbg-promptbtn")) {
      await togglePrompt(Number(row.dataset.seq));
      redraw();
    }
  });
}

function setOpen(open) {
  viewer.debugging = open;
  panel.classList.toggle("hidden", !open);
  app.classList.toggle("debugging", open);
  openButton.classList.toggle("on", open);
  stepButton.classList.toggle("hidden", !open);

  clearInterval(polling);
  polling = null;
  if (!open) return;
  poll();
  polling = setInterval(poll, EVERY_MS);
}

export function inspect(id) {
  viewer.inspecting = viewer.inspecting === id ? null : id;
  redraw();
}

async function poll() {
  try {
    const response = await fetch(`/debug/state?limit=${THOUGHTS}`);
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    internals = await response.json();
    draw();
  } catch (failed) {
    vitalsBar.innerHTML = `<span class="dbg-bad">debug unavailable — `
      + `${text(failed.message)}</span>`;
  }
}

function redraw() {
  drawnFrom.detail = drawnFrom.thoughts = "";
  draw();
}

function draw() {
  if (!internals) return;
  armStepButton();
  drawVitals();
  chipsBar.innerHTML = internals.agents.map(chip).join("");

  const chosen = internals.agents.find((g) => g.id === viewer.inspecting) ?? null;
  drawIfChanged(detailPane, "detail", [chosen, internals.conversations],
    () => (chosen ? detailHtml(chosen, internals) : hintHtml()));

  const thoughts = chosen
    ? internals.thoughts.filter((t) => t.agent_id === chosen.id)
    : internals.thoughts;
  drawIfChanged(thoughtsPane, "thoughts", [thoughts, openPrompts()],
    () => heading(chosen, thoughts) + list(thoughts));
}

function drawIfChanged(pane, remembered, dependsOn, render) {
  const signature = JSON.stringify(dependsOn);
  if (signature === drawnFrom[remembered]) return;
  drawnFrom[remembered] = signature;
  pane.innerHTML = render();
}

function armStepButton() {
  stepButton.disabled = !internals.paused;
  stepButton.title = internals.paused
    ? "Advance one decision tick"
    : "Pause the party first — stepping only makes sense while it's frozen";
}

function drawVitals() {
  // The two numbers that explain a party which looks frozen: calls in flight,
  // and guests holding news that nobody will read this tick.
  const bits = [
    `<span class="k">tick</span> ${internals.tick}`,
    `<span class="k">thinking</span> ${internals.thinking.length}/${internals.knobs.max_concurrent}`,
    `<span class="k">convs</span> ${internals.conversations.length}`,
    `<span class="k">left</span> ${internals.seconds_left}s`,
  ];
  if (internals.failures) {
    bits.push(`<span class="dbg-bad">${internals.failures} failed</span>`);
  }
  if (internals.starved.length) {
    bits.push(`<span class="dbg-warn" title="had something to react to but lost`
      + ` the race for a model call">starved ${internals.starved.length}</span>`);
  }
  if (internals.paused) bits.push(`<span class="dbg-warn">paused</span>`);
  vitalsBar.innerHTML = bits.join('<span class="sep">·</span>');
}

function chip(guest) {
  const mark = guest.thinking ? "◌"
    : guest.approach ? "→"
    : guest.conversation_id ? "◈"
    : guest.action === "walking" ? "»"
    : "·";
  const on = guest.id === viewer.inspecting ? " on" : "";
  return `<button class="dbg-chip${on}" data-agent="${text(guest.id)}"`
    + ` title="${text(guest.action)}">${mark} ${text(guest.name)}</button>`;
}

function heading(chosen, thoughts) {
  const whose = chosen ? `${text(chosen.name)}'s thoughts` : "all thoughts";
  return `<div class="dbg-section">${whose}`
    + `<span class="dbg-count">${thoughts.length}</span></div>`;
}

function list(thoughts) {
  if (!thoughts.length) return `<div class="dbg-empty">nothing yet</div>`;
  return thoughts.map(thoughtHtml).join("");
}

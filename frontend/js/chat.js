// The chat drawer: talking to one guest, with the party held still.
//
// Opening it pauses the party. That isn't a nicety — the guest answers with a
// real thought, and a party that carried on around a conversation you were
// having would leave them replying to a moment that had already passed.
//
// A guest's reply arrives the same way everything else does: as an event on the
// socket. The one with no conversation id is the one meant for this drawer.

import { ask } from "./connection.js";
import { world } from "./world.js";
import { viewer } from "./viewer.js";
import { spriteFor } from "./sprites.js";
import { statsHtml } from "./stats.js";
import { showWhetherFrozen } from "./controls.js";

const drawer = document.getElementById("chat");
const dimmer = document.getElementById("chatOverlay");
const portrait = document.getElementById("chatPortrait");
const nameLine = document.getElementById("chatName");
const ageLine = document.getElementById("chatAge");
const statsPanel = document.getElementById("chatStats");
const transcript = document.getElementById("chatTranscript");
const form = document.getElementById("chatForm");
const input = document.getElementById("chatInput");

export function arm() {
  document.getElementById("chatClose").addEventListener("click", close);
  dimmer.addEventListener("click", close);
  form.addEventListener("submit", say);
}

export function open(id) {
  const guest = world.guest(id);
  if (!guest) return;

  viewer.chattingWith = id;
  viewer.hovering = null;
  ask({ type: "open_chat", agent_id: id });   // the backend pauses and says hello

  portrait.src = spriteFor(id, false);
  nameLine.textContent = guest.name;
  ageLine.textContent = `age ${guest.age}`;
  statsPanel.innerHTML = statsHtml(guest.stats);
  transcript.innerHTML = "";
  dimmer.classList.remove("hidden");
  drawer.classList.remove("hidden");
  showWhetherFrozen();
  input.focus();
}

function close() {
  if (viewer.chattingWith === null) return;
  ask({ type: "close_chat", agent_id: viewer.chattingWith });
  viewer.chattingWith = null;
  drawer.classList.add("hidden");
  dimmer.classList.add("hidden");
  showWhetherFrozen();
}

function say(submitted) {
  submitted.preventDefault();
  const words = input.value.trim();
  if (!words || viewer.chattingWith === null) return;
  append("user", words);
  ask({ type: "user_message", agent_id: viewer.chattingWith, text: words });
  input.value = "";
}

export function hear(spoken) {
  if (spoken.agent_id !== viewer.chattingWith) return;
  append("agent", spoken.text);
}

function append(who, words) {
  const line = document.createElement("div");
  line.className = `msg ${who}`;
  line.textContent = words;
  transcript.appendChild(line);
  transcript.scrollTop = transcript.scrollHeight;
}

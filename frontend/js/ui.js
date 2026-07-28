// DOM glue: top-bar controls, party log, chat drawer, and the stat-bar renderer
// shared by the hover tooltip and the chat panel. Sends user intent to the
// backend; never invents world truth.

import { agents, ui, noteLine, clearLine } from "./state.js";
import { spriteFor, ICONS } from "./sprites.js";
import { send } from "./net.js";
import { escapeHtml } from "./util.js";

const statusEl = document.getElementById("status");
const pauseBtn = document.getElementById("pauseBtn");
const speedBtn = document.getElementById("speedBtn");
const modeBtn = document.getElementById("modeBtn");
const pausedBadge = document.getElementById("pausedBadge");
const logList = document.getElementById("logList");

const chat = document.getElementById("chat");
const chatOverlay = document.getElementById("chatOverlay");
const chatPortrait = document.getElementById("chatPortrait");
const chatName = document.getElementById("chatName");
const chatAge = document.getElementById("chatAge");
const chatStats = document.getElementById("chatStats");
const chatTranscript = document.getElementById("chatTranscript");
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");

// --- stat bars (tooltip + chat share this) --------------------------------

const STAT_DEFS = [
  { key: "drunkenness", label: "Drunkenness", icon: ICONS.drink, bipolar: false, color: "#e8b34d" },
  { key: "confidence", label: "Confidence", icon: ICONS.bolt, bipolar: true },
  { key: "fun", label: "Fun", icon: ICONS.star, bipolar: true },
  { key: "attractiveness", label: "Attractiveness", icon: ICONS.heart, bipolar: false, color: "#e0607a" },
];

export function statsHTML(stats) {
  return STAT_DEFS.map(def => {
    const v = stats?.[def.key] ?? 0;
    let color = def.color, leftPct, widthPct, valueLabel, mid = "";
    if (def.bipolar) {
      color = v >= 0 ? "#7fae6b" : "#c15c5c";
      const mag = Math.min(50, Math.abs(v) / 100 * 50);
      leftPct = v >= 0 ? 50 : 50 - mag;
      widthPct = mag;
      valueLabel = (v >= 0 ? "+" : "") + Math.round(v);
      mid = '<div class="mid"></div>';
    } else {
      leftPct = 0;
      widthPct = Math.max(0, Math.min(100, v));
      valueLabel = Math.round(v);
    }
    return `<div class="stat">
        <img src="${def.icon}" alt="" />
        <div class="body">
          <div class="row"><span>${def.label}</span><span class="val" style="color:${color}">${valueLabel}</span></div>
          <div class="track">${mid}<div class="fill" style="left:${leftPct}%;width:${widthPct}%;background:${color}"></div></div>
        </div>
      </div>`;
  }).join("");
}

// --- chat drawer ----------------------------------------------------------

export function openChat(id) {
  const a = agents.get(id);
  if (!a) return;
  ui.chatId = id;
  send({ type: "open_chat", agent_id: id }); // backend pauses + greets
  chatPortrait.src = spriteFor(id, false);
  chatName.textContent = a.name;
  chatAge.textContent = `age ${a.age}`;
  chatStats.innerHTML = statsHTML(a.stats);
  chatTranscript.innerHTML = "";
  chatOverlay.classList.remove("hidden");
  chat.classList.remove("hidden");
  ui.hoveredId = null;
  updateBadge();
  chatInput.focus();
}

function closeChat() {
  if (ui.chatId == null) return;
  send({ type: "close_chat", agent_id: ui.chatId });
  ui.chatId = null;
  chat.classList.add("hidden");
  chatOverlay.classList.add("hidden");
  updateBadge();
}

function appendMsg(who, text) {
  const div = document.createElement("div");
  div.className = `msg ${who}`;
  div.textContent = text;
  chatTranscript.appendChild(div);
  chatTranscript.scrollTop = chatTranscript.scrollHeight;
}

// --- party log ------------------------------------------------------------

function pushLog(text) {
  const li = document.createElement("div");
  li.className = "log-entry";
  const time = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  li.innerHTML = `<span class="time">${time}</span>${escapeHtml(text)}`;
  logList.prepend(li);
  while (logList.children.length > 40) logList.lastChild.remove();
}

// --- inbound events + status (called by net) ------------------------------

export function onStatus(text) { statusEl.textContent = text; }

export function onEvent(msg) {
  switch (msg.type) {
    case "agent_spoke":
      if (msg.conversation_id != null) {
        noteLine(msg.conversation_id, msg.text);          // cluster bubble
      } else if (msg.agent_id === ui.chatId) {
        appendMsg("agent", msg.text);                      // chat reply
      }
      break;
    case "agent_arrived":
      pushLog(`${msg.name} arrived.`);
      break;
    case "agent_drank":
      pushLog(`${msg.name} grabbed a drink.`);
      break;
    case "conversation_started":
      pushLog(`${(msg.names || []).join(" and ")} started talking.`);
      break;
    case "conversation_ended":
      pushLog(`${(msg.names || []).join(" and ")} wrapped up.`);
      clearLine(msg.conversation_id);
      break;
  }
}

// --- controls -------------------------------------------------------------

function updateBadge() {
  pausedBadge.classList.toggle("hidden", !(ui.paused || ui.chatId != null));
}

export function initControls() {
  pauseBtn.addEventListener("click", () => {
    ui.paused = !ui.paused;
    send({ type: ui.paused ? "pause" : "resume" });
    pauseBtn.textContent = ui.paused ? "Resume" : "Pause";
    updateBadge();
  });

  speedBtn.addEventListener("click", () => {
    ui.speed = ui.speed === 1 ? 2 : ui.speed === 2 ? 3 : 1;
    send({ type: "set_speed", value: ui.speed });
    speedBtn.textContent = `${ui.speed}x`;
  });

  modeBtn.addEventListener("click", () => {
    ui.dark = !ui.dark;
    modeBtn.textContent = ui.dark ? "Night" : "Day";
  });

  document.getElementById("chatClose").addEventListener("click", closeChat);
  chatOverlay.addEventListener("click", closeChat);

  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = chatInput.value.trim();
    if (!text || ui.chatId == null) return;
    appendMsg("user", text);
    send({ type: "user_message", agent_id: ui.chatId, text });
    chatInput.value = "";
  });
}

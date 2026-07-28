// Render loop: DOM-based (like the design), driven by our state store.
//
// Each agent is an absolutely-positioned <img> sprite. Every frame we ease its
// render position toward the authoritative one (interpolation) and re-place the
// element. The room, cluster rings, and speech bubbles are DOM too. This runs at
// ~60fps off requestAnimationFrame, decoupled from the ~30Hz snapshot stream.

import { agents, conversationLines, ui } from "./state.js";
import { spriteFor, roomFor } from "./sprites.js";
import { openChat, statsHTML } from "./ui.js";
import { escapeHtml } from "./util.js";

const stage = document.getElementById("stage");
const roomBg = document.getElementById("roomBg");
const agentLayer = document.getElementById("agentLayer");
const clusterLayer = document.getElementById("clusterLayer");
const tooltip = document.getElementById("tooltip");

const SMOOTH = 12;        // easing rate toward the authoritative position
const els = new Map();    // agent id -> <img>
let lastRoomKey = null;
let last = performance.now();

function ensureEl(id) {
  let el = els.get(id);
  if (!el) {
    el = document.createElement("img");
    el.className = "agent";
    el.addEventListener("mouseenter", () => { ui.hoveredId = id; });
    el.addEventListener("mouseleave", () => { if (ui.hoveredId === id) ui.hoveredId = null; });
    el.addEventListener("click", () => openChat(id));
    agentLayer.appendChild(el);
    els.set(id, el);
  }
  return el;
}

function frame(now) {
  const dt = Math.min((now - last) / 1000, 0.1);
  last = now;
  const k = 1 - Math.exp(-dt * SMOOTH);

  // room background (swap on day/night)
  const roomKey = ui.dark ? "dark" : "light";
  if (roomKey !== lastRoomKey) { roomBg.src = roomFor(ui.dark); lastRoomKey = roomKey; }

  // agents
  for (const a of agents.values()) {
    a.rx += (a.x - a.rx) * k;
    a.ry += (a.y - a.ry) * k;
    const el = ensureEl(a.id);
    el.src = spriteFor(a.id, a.action === "drinking");
    el.style.left = `${Math.round(a.rx - 21)}px`;
    el.style.top = `${Math.round(a.ry - 63)}px`;
    el.style.zIndex = Math.round(a.ry);
    const walking = a.action === "walking";
    if (walking !== el._walking) { el.classList.toggle("walking", walking); el._walking = walking; }
  }
  // drop elements for agents that left
  for (const [id, el] of [...els.entries()]) {
    if (!agents.has(id)) { el.remove(); els.delete(id); }
  }

  drawClusters();
  drawTooltip();
  requestAnimationFrame(frame);
}

function drawClusters() {
  // group agents by conversation_id
  const groups = new Map();
  for (const a of agents.values()) {
    if (!a.conversation_id) continue;
    if (!groups.has(a.conversation_id)) groups.set(a.conversation_id, []);
    groups.get(a.conversation_id).push(a);
  }
  let html = "";
  for (const [cid, members] of groups) {
    if (members.length < 2) continue;
    const xs = members.map(m => m.rx), ys = members.map(m => m.ry);
    const minX = Math.min(...xs) - 45, maxX = Math.max(...xs) + 45;
    const minY = Math.min(...ys) - 88, maxY = Math.max(...ys) + 14;
    html += `<div class="cluster-ring" style="left:${minX}px;top:${minY}px;width:${maxX - minX}px;height:${maxY - minY}px;"></div>`;
    const line = conversationLines.get(cid);
    if (line) {
      html += `<div class="cluster-bubble" style="left:${(minX + maxX) / 2}px;top:${minY - 26}px;">${escapeHtml(line)}</div>`;
    }
  }
  clusterLayer.innerHTML = html;
}

function drawTooltip() {
  const a = ui.hoveredId != null ? agents.get(ui.hoveredId) : null;
  if (!a) { tooltip.classList.add("hidden"); return; }
  tooltip.innerHTML =
    `<div class="tt-head"><span class="tt-name">${escapeHtml(a.name)}</span><span class="tt-age">age ${a.age}</span></div>` +
    statsHTML(a.stats);
  tooltip.style.left = `${Math.min(750, Math.max(10, a.rx - 100))}px`;
  tooltip.style.top = `${Math.max(10, a.ry - 63 - 190)}px`;
  tooltip.classList.remove("hidden");
}

export function start() {
  requestAnimationFrame(frame);
}

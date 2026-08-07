// The room on screen: guests, the rings around conversations, and the tooltip.
//
// Painted from the DOM rather than a canvas — each guest is one absolutely
// positioned <img>, which is enough for a dozen of them and means the browser's
// own hit-testing does the hovering and clicking for us.
//
// It repaints sixty times a second off requestAnimationFrame, which is
// deliberately unrelated to the thirty snapshots a second arriving on the
// socket. The two rates are decoupled by the guests easing toward the position
// they were last reported at, so motion stays smooth whatever the network does.

import { world } from "./world.js";
import { viewer } from "./viewer.js";
import { spriteFor, roomFor } from "./sprites.js";
import { statsHtml } from "./stats.js";
import { text } from "./html.js";

const background = document.getElementById("roomBg");
const guestLayer = document.getElementById("agentLayer");
const ringLayer = document.getElementById("clusterLayer");
const tooltip = document.getElementById("tooltip");

const EASING = 12;          // how hard a sprite is pulled toward the truth
const FEET = 63;            // a sprite's origin is its head, its position is its feet
const WAIST = 21;

const sprites = new Map();  // guest id -> <img>
let pick = () => {};
let lastPainted = null;     // which room art is currently up
let lastFrameAt = performance.now();

export function show({ onPick }) {
  pick = onPick;
  requestAnimationFrame(paint);
}

function paint(now) {
  const elapsed = Math.min((now - lastFrameAt) / 1000, 0.1);
  lastFrameAt = now;

  hangTheRightRoom();
  drawGuests(1 - Math.exp(-elapsed * EASING));
  drawConversations();
  drawTooltip();

  requestAnimationFrame(paint);
}

function hangTheRightRoom() {
  const wanted = viewer.night ? "night" : "day";
  if (wanted === lastPainted) return;
  background.src = roomFor(viewer.night);
  lastPainted = wanted;
}

// --- guests -----------------------------------------------------------------

function drawGuests(easing) {
  for (const guest of world.everyone()) {
    guest.driftTowardsTruth(easing);
    place(spriteOf(guest), guest);
  }
  for (const [id, sprite] of [...sprites.entries()]) {
    if (world.guest(id)) continue;
    sprite.remove();
    sprites.delete(id);
  }
}

function place(sprite, guest) {
  const [x, y] = guest.drawnAt;
  sprite.src = spriteFor(guest.id, guest.hasADrink);
  sprite.style.left = `${Math.round(x - WAIST)}px`;
  sprite.style.top = `${Math.round(y - FEET)}px`;
  // Further down the room means closer to the viewer, so y is the stacking order.
  sprite.style.zIndex = Math.round(y);
  // Only touch the class when it actually changes, or the walk animation
  // restarts from its first frame sixty times a second and nobody ever moves.
  if (String(guest.isWalking) !== sprite.dataset.walking) {
    sprite.classList.toggle("walking", guest.isWalking);
    sprite.dataset.walking = String(guest.isWalking);
  }
}

function spriteOf(guest) {
  let sprite = sprites.get(guest.id);
  if (sprite) return sprite;

  sprite = document.createElement("img");
  sprite.className = "agent";
  sprite.addEventListener("mouseenter", () => { viewer.hovering = guest.id; });
  sprite.addEventListener("mouseleave", () => {
    if (viewer.hovering === guest.id) viewer.hovering = null;
  });
  sprite.addEventListener("click", () => pick(guest.id));
  guestLayer.appendChild(sprite);
  sprites.set(guest.id, sprite);
  return sprite;
}

// --- conversations ----------------------------------------------------------

function drawConversations() {
  ringLayer.innerHTML = world.conversations().map(ringHtml).join("");
}

function ringHtml({ members, line }) {
  const xs = members.map((guest) => guest.drawnAt[0]);
  const ys = members.map((guest) => guest.drawnAt[1]);
  const left = Math.min(...xs) - 45;
  const right = Math.max(...xs) + 45;
  const top = Math.min(...ys) - 88;
  const bottom = Math.max(...ys) + 14;

  const ring = `<div class="cluster-ring" style="left:${left}px;top:${top}px;`
    + `width:${right - left}px;height:${bottom - top}px;"></div>`;
  if (!line) return ring;
  return ring + `<div class="cluster-bubble" style="left:${(left + right) / 2}px;`
    + `top:${top - 26}px;">${text(line)}</div>`;
}

// --- the hover tooltip ------------------------------------------------------

function drawTooltip() {
  const guest = viewer.hovering ? world.guest(viewer.hovering) : null;
  if (!guest) {
    tooltip.classList.add("hidden");
    return;
  }
  const [x, y] = guest.drawnAt;
  tooltip.innerHTML = `<div class="tt-head"><span class="tt-name">${text(guest.name)}</span>`
    + `<span class="tt-age">age ${text(guest.age)}</span></div>`
    + statsHtml(guest.stats);
  tooltip.style.left = `${Math.min(750, Math.max(10, x - 100))}px`;
  tooltip.style.top = `${Math.max(10, y - FEET - 190)}px`;
  tooltip.classList.remove("hidden");
}

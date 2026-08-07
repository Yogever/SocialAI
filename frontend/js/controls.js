// The top bar: pause, speed, the lights, and the connection status.
//
// Every button here asks the backend for something and then relabels itself.
// The one exception is the lights, which are nobody's business but this
// browser's — the party looks the same to the guests either way.

import { ask } from "./connection.js";
import { viewer } from "./viewer.js";

const status = document.getElementById("status");
const pauseButton = document.getElementById("pauseBtn");
const speedButton = document.getElementById("speedBtn");
const lightsButton = document.getElementById("modeBtn");
const pausedBadge = document.getElementById("pausedBadge");

const SPEEDS = [1, 2, 3];

export function arm() {
  pauseButton.addEventListener("click", togglePause);
  speedButton.addEventListener("click", cycleSpeed);
  lightsButton.addEventListener("click", toggleLights);
}

function togglePause() {
  viewer.paused = !viewer.paused;
  ask({ type: viewer.paused ? "pause" : "resume" });
  pauseButton.textContent = viewer.paused ? "Resume" : "Pause";
  showWhetherFrozen();
}

function cycleSpeed() {
  viewer.speed = SPEEDS[(SPEEDS.indexOf(viewer.speed) + 1) % SPEEDS.length];
  ask({ type: "set_speed", value: viewer.speed });
  speedButton.textContent = `${viewer.speed}x`;
}

function toggleLights() {
  viewer.night = !viewer.night;
  lightsButton.textContent = viewer.night ? "Night" : "Day";
}

export function showWhetherFrozen() {
  // Opening a chat pauses the party too, so the badge asks both questions.
  const frozen = viewer.paused || viewer.chattingWith !== null;
  pausedBadge.classList.toggle("hidden", !frozen);
}

export function showStatus(line) {
  status.textContent = line;
}

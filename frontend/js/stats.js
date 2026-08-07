// How a guest is doing, as four little bars.
//
// Shared by the hover tooltip and the chat drawer, because they are the same
// question asked from two places. Two of the four run 0..100 and fill from the
// left; the other two run -100..100 and grow out from the middle, which is the
// only honest way to draw a number that can be negative.

import { ICONS } from "./sprites.js";
import { text } from "./html.js";

const GOOD = "#7fae6b";
const BAD = "#c15c5c";

const BARS = [
  { key: "drunkenness", label: "Drunkenness", icon: ICONS.drink, colour: "#e8b34d" },
  { key: "confidence", label: "Confidence", icon: ICONS.bolt, fromMiddle: true },
  { key: "fun", label: "Fun", icon: ICONS.star, fromMiddle: true },
  { key: "attractiveness", label: "Attractiveness", icon: ICONS.heart, colour: "#e0607a" },
];

export function statsHtml(stats) {
  return BARS.map((bar) => barHtml(bar, stats?.[bar.key] ?? 0)).join("");
}

function barHtml(bar, value) {
  const { colour, left, width, reading, middle } = bar.fromMiddle
    ? aroundTheMiddle(value)
    : fromTheLeft(bar, value);
  return `<div class="stat">
      <img src="${bar.icon}" alt="" />
      <div class="body">
        <div class="row"><span>${bar.label}</span>
          <span class="val" style="color:${colour}">${text(reading)}</span></div>
        <div class="track">${middle}<div class="fill"
          style="left:${left}%;width:${width}%;background:${colour}"></div></div>
      </div>
    </div>`;
}

function fromTheLeft(bar, value) {
  return {
    colour: bar.colour,
    left: 0,
    width: Math.max(0, Math.min(100, value)),
    reading: Math.round(value),
    middle: "",
  };
}

function aroundTheMiddle(value) {
  // Half the track is each direction, so a full -100 or +100 reaches an end.
  const reach = Math.min(50, (Math.abs(value) / 100) * 50);
  return {
    colour: value >= 0 ? GOOD : BAD,
    left: value >= 0 ? 50 : 50 - reach,
    width: reach,
    reading: (value >= 0 ? "+" : "") + Math.round(value),
    middle: '<div class="mid"></div>',
  };
}

// Procedural pixel art: the guests, the room, and the little stat icons.
//
// Everything here is drawn to an offscreen canvas and handed back as a data URL,
// so the project ships no image files. Nothing in this file knows where world
// state comes from — it is the one part of the browser that would be exactly the
// same if there were no backend at all.
//
// A guest's appearance is derived from their id and nothing else. It is pure
// decoration: it never travels over the wire, and the backend has no idea what
// anybody looks like.

const SKIN = ["#e8b48a", "#c68958", "#8d5a3c", "#f0c9a0"];
const HAIR = ["#3a2a1e", "#8a4a2f", "#d9a441", "#2b2b2b", "#b23a5e", "#5b6ee1", "#6b3f2a"];
const SHIRT = ["#c0533e", "#3f7d63", "#4a6fa5", "#a3477a", "#d98c3a",
               "#5a4a7a", "#3f8f8f", "#b8543f", "#6b5b95", "#c9a227"];
const PANTS = ["#2c2430", "#3a2e28", "#26313a", "#33262e"];
const HAIRCUTS = ["short", "long", "mohawk", "cap"];

const SHOE = "#1c140f";
const EYE = "#1c140f";

// --- picking what somebody looks like ---------------------------------------

export function looksOf(id) {
  const seed = seedFrom(id);
  return {
    skin: SKIN[seed % SKIN.length],
    hair: HAIR[seed % HAIR.length],
    shirt: SHIRT[seed % SHIRT.length],
    pants: PANTS[seed % PANTS.length],
    haircut: HAIRCUTS[seed % HAIRCUTS.length],
    glasses: seed % 4 === 2,
  };
}

function seedFrom(id) {
  // "a7" -> 7, so ids that read as numbers give stable, spread-out choices.
  const digits = /\d+/.exec(id);
  if (digits) return parseInt(digits[0], 10);
  let hash = 0;
  for (const character of id) hash = (hash * 31 + character.charCodeAt(0)) & 0xffff;
  return hash;
}

function shade(hex, by) {
  const packed = parseInt(hex.slice(1), 16);
  const channels = [(packed >> 16) & 255, (packed >> 8) & 255, packed & 255];
  return `rgb(${channels.map((c) => clampByte(Math.round(c * (1 + by)))).join(",")})`;
}

function clampByte(value) {
  return Math.max(0, Math.min(255, value));
}

function pixels(width, height) {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ink = canvas.getContext("2d");
  ink.imageSmoothingEnabled = false;
  return [canvas, ink];
}

// --- one guest, 14x22 pixels ------------------------------------------------

function drawGuest(looks, holdingDrink) {
  const [canvas, ink] = pixels(14, 22);
  castShadow(ink);
  drawLegs(ink, looks);
  drawTorso(ink, looks);
  drawHead(ink, looks);
  drawHair(ink, looks);
  drawFace(ink, looks);
  if (holdingDrink) drawDrink(ink);
  return canvas.toDataURL();
}

function castShadow(ink) {
  ink.fillStyle = "rgba(0,0,0,0.35)";
  ink.beginPath();
  ink.ellipse(7, 21, 5, 1.4, 0, 0, Math.PI * 2);
  ink.fill();
}

function drawLegs(ink, looks) {
  ink.fillStyle = looks.pants;
  ink.fillRect(4, 15, 2, 4);
  ink.fillRect(8, 15, 2, 4);
  ink.fillStyle = SHOE;
  ink.fillRect(4, 19, 2, 2);
  ink.fillRect(8, 19, 2, 2);
}

function drawTorso(ink, looks) {
  ink.fillStyle = looks.shirt;
  ink.fillRect(3, 9, 8, 6);
  ink.fillStyle = shade(looks.shirt, -0.25);   // arms, a shade darker than the front
  ink.fillRect(2, 10, 1, 4);
  ink.fillRect(11, 10, 1, 4);
}

function drawHead(ink, looks) {
  ink.fillStyle = looks.skin;
  ink.fillRect(5, 4, 4, 4);
}

function drawHair(ink, looks) {
  ink.fillStyle = looks.haircut === "cap" ? shade(looks.hair, 0.15) : looks.hair;
  switch (looks.haircut) {
    case "long":
      ink.fillRect(4, 2, 6, 3);
      ink.fillRect(3, 5, 1, 4);
      ink.fillRect(10, 5, 1, 4);
      break;
    case "mohawk":
      ink.fillRect(6, 1, 2, 4);
      ink.fillRect(4, 3, 1, 2);
      ink.fillRect(9, 3, 1, 2);
      break;
    case "cap":
      ink.fillRect(4, 2, 6, 3);
      ink.fillRect(3, 4, 8, 1);   // the peak
      break;
    default:
      ink.fillRect(4, 2, 6, 3);
  }
}

function drawFace(ink, looks) {
  ink.fillStyle = EYE;
  ink.fillRect(6, 6, 1, 1);
  ink.fillRect(8, 6, 1, 1);
  if (looks.glasses) {
    ink.fillStyle = "rgba(20,20,26,0.85)";
    ink.fillRect(5, 5, 5, 2);
  }
}

function drawDrink(ink) {
  ink.fillStyle = "#f2d98a";
  ink.fillRect(11, 11, 2, 1);
  ink.fillStyle = "#e8b34d";
  ink.fillRect(11, 12, 2, 2);
}

// --- the room, 320x200 pixels, stretched to fill the stage ------------------

const DAY = {
  wall: "#e7d9c9", floor: "#c9905f", floorboard: "#b87a4a", rug: "#c96a5a",
  rugEdge: "#a5493c", bar: "#8a6248", barTop: "#a9835f", barShelf: "#5c3d2a",
  couch: "#9a6b5a", couchBack: "#b98a72", couchShadow: "#7a4c3c", frame: "#5c3d2a",
  sky: "#bfe0f2", star: "#ffffff", snack: "#a9835f", snackTop: "#f0ddb8",
  wire: "#5c3d2a", bulb: "#ffe9a8",
};

const NIGHT = {
  wall: "#3b2a35", floor: "#5a3d2e", floorboard: "#6b4a38", rug: "#7a2e2e",
  rugEdge: "#5c1f1f", bar: "#4a2f22", barTop: "#6b4632", barShelf: "#2a1c16",
  couch: "#6b3a3a", couchBack: "#8a4c4c", couchShadow: "#4d2626", frame: "#2a1c16",
  sky: "#131022", star: "#f4e7c1", snack: "#5c3a2a", snackTop: "#e8d9b0",
  wire: "#2a1c16", bulb: "#ffdb7a",
};

const ROOM_W = 320;
const ROOM_H = 200;

function drawRoom(dark) {
  const [canvas, ink] = pixels(ROOM_W, ROOM_H);
  const paint = dark ? NIGHT : DAY;
  layFloor(ink, paint);
  layRug(ink, paint);
  hangWindow(ink, paint, dark);
  hangLights(ink, paint, dark);
  buildBar(ink, paint);
  putCouch(ink, paint);
  layOutSnacks(ink, paint);
  if (dark) dimTheCorners(ink);
  return canvas.toDataURL();
}

function layFloor(ink, paint) {
  ink.fillStyle = paint.floor;
  ink.fillRect(0, 0, ROOM_W, ROOM_H);
  ink.fillStyle = paint.wall;
  ink.fillRect(0, 0, ROOM_W, 40);
  ink.fillStyle = paint.floorboard;
  for (let y = 44; y < ROOM_H; y += 9) ink.fillRect(0, y, ROOM_W, 1);
}

function layRug(ink, paint) {
  ink.fillStyle = paint.rug;
  ink.fillRect(90, 120, 140, 65);
  ink.fillStyle = paint.rugEdge;
  ink.fillRect(90, 120, 140, 3);
  ink.fillRect(90, 182, 140, 3);
  ink.fillRect(90, 120, 3, 65);
  ink.fillRect(227, 120, 3, 65);
}

function hangWindow(ink, paint, dark) {
  ink.fillStyle = paint.frame;
  ink.fillRect(18, 6, 58, 30);
  ink.fillStyle = paint.sky;
  ink.fillRect(22, 10, 50, 22);
  ink.fillStyle = paint.star;
  if (dark) {
    for (const [x, y] of [[28, 14], [40, 18], [55, 12], [62, 20], [34, 24]]) {
      ink.fillRect(x, y, 1, 1);
    }
  } else {
    ink.beginPath();
    ink.arc(60, 16, 6, 0, Math.PI * 2);
    ink.fill();
  }
  ink.fillStyle = paint.frame;     // the cross-bars, drawn over the sky
  ink.fillRect(46, 10, 2, 22);
  ink.fillRect(22, 20, 50, 2);
}

function hangLights(ink, paint, dark) {
  ink.fillStyle = paint.wire;
  for (let x = 4; x < ROOM_W - 4; x += 4) ink.fillRect(x, sagAt(x) - 2, 2, 1);
  if (!dark) return;               // by day the bulbs don't read at all
  ink.fillStyle = paint.bulb;
  for (let x = 6; x < ROOM_W - 6; x += 17) {
    const y = sagAt(x);
    ink.globalAlpha = 0.35;
    ink.fillRect(x - 2, y - 1, 5, 3);   // the glow
    ink.globalAlpha = 1;
    ink.fillRect(x, y, 1, 1);           // the bulb
  }
}

function sagAt(x) {
  return 5 + Math.round(Math.sin(x / 24) * 2 + 2);
}

function buildBar(ink, paint) {
  ink.fillStyle = paint.barShelf;
  ink.fillRect(238, 48, 72, 20);
  ["#7fae6b", "#c15c5c", "#e8b34d", "#6fb1f2", "#a3477a"].forEach((bottle, i) => {
    ink.fillStyle = bottle;
    ink.fillRect(244 + i * 13, 52, 5, 12);
  });
  ink.fillStyle = paint.bar;
  ink.fillRect(235, 108, 75, 32);
  ink.fillStyle = paint.barTop;
  ink.fillRect(232, 72, 80, 14);
}

function putCouch(ink, paint) {
  ink.fillStyle = paint.couchShadow;
  ink.fillRect(15, 178, 80, 10);
  ink.fillStyle = paint.couch;
  ink.fillRect(15, 155, 80, 28);
  ink.fillStyle = paint.couchBack;
  ink.fillRect(15, 150, 80, 10);
  ink.fillStyle = paint.couchShadow;
  ink.fillRect(54, 152, 3, 28);    // the seam between the two cushions
}

function layOutSnacks(ink, paint) {
  ink.fillStyle = paint.snack;
  ink.fillRect(140, 158, 50, 20);
  ink.fillStyle = paint.snackTop;
  ink.fillRect(138, 150, 54, 9);
  ["#c15c5c", "#7fae6b", "#e8b34d", "#f2c46d"].forEach((bowl, i) => {
    ink.fillStyle = bowl;
    ink.beginPath();
    ink.arc(148 + i * 11, 154, 2, 0, Math.PI * 2);
    ink.fill();
  });
}

function dimTheCorners(ink) {
  const gloom = ink.createRadialGradient(ROOM_W / 2, ROOM_H / 2, 60,
                                         ROOM_W / 2, ROOM_H / 2, 220);
  gloom.addColorStop(0, "rgba(0,0,0,0)");
  gloom.addColorStop(1, "rgba(0,0,0,0.4)");
  ink.fillStyle = gloom;
  ink.fillRect(0, 0, ROOM_W, ROOM_H);
}

// --- the little icons beside each stat bar ----------------------------------

function drawIcon(kind) {
  const [canvas, ink] = pixels(10, 10);
  if (kind === "drink") {
    ink.fillStyle = "#f2d98a";
    ink.fillRect(1, 1, 8, 1);
    ink.fillStyle = "#e8b34d";
    ink.fillRect(2, 2, 6, 1);
    ink.fillRect(3, 3, 4, 1);
    ink.fillRect(4, 4, 2, 1);
    ink.fillRect(4, 5, 2, 3);
    ink.fillRect(2, 8, 6, 1);
  } else if (kind === "bolt") {
    ink.fillStyle = "#6fb1f2";
    ink.fillRect(5, 0, 2, 3);
    ink.fillRect(3, 3, 3, 2);
    ink.fillRect(5, 5, 2, 2);
    ink.fillRect(2, 7, 3, 2);
  } else if (kind === "star") {
    ink.fillStyle = "#f2c14e";
    ink.fillRect(4, 0, 2, 10);
    ink.fillRect(0, 4, 10, 2);
    ink.fillRect(2, 2, 6, 6);
  } else {
    ink.fillStyle = "#e0607a";
    ink.beginPath();
    ink.arc(3.2, 3, 2.2, 0, Math.PI * 2);
    ink.fill();
    ink.beginPath();
    ink.arc(6.8, 3, 2.2, 0, Math.PI * 2);
    ink.fill();
    ink.beginPath();
    ink.moveTo(1, 4);
    ink.lineTo(5, 9);
    ink.lineTo(9, 4);
    ink.fill();
  }
  return canvas.toDataURL();
}

// --- drawn once, then remembered --------------------------------------------

const guestArt = new Map();
const roomArt = new Map();

export function spriteFor(id, holdingDrink) {
  const key = `${id}|${holdingDrink ? 1 : 0}`;
  if (!guestArt.has(key)) guestArt.set(key, drawGuest(looksOf(id), holdingDrink));
  return guestArt.get(key);
}

export function roomFor(dark) {
  const key = dark ? "night" : "day";
  if (!roomArt.has(key)) roomArt.set(key, drawRoom(dark));
  return roomArt.get(key);
}

export const ICONS = {
  drink: drawIcon("drink"),
  bolt: drawIcon("bolt"),
  star: drawIcon("star"),
  heart: drawIcon("heart"),
};

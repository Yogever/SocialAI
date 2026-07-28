// Procedural pixel art, harvested from the Claude Design mockup.
//
// Everything here draws to an offscreen <canvas> and returns a data-URL — no
// external image assets. This is the *architecture-neutral* half of the design:
// it doesn't know or care where world state comes from. Appearance is derived
// deterministically from an agent's id (pure cosmetics, never on the wire).

const SKIN = ["#e8b48a", "#c68958", "#8d5a3c", "#f0c9a0"];
const HAIR = ["#3a2a1e", "#8a4a2f", "#d9a441", "#2b2b2b", "#b23a5e", "#5b6ee1", "#6b3f2a"];
const SHIRT = ["#c0533e", "#3f7d63", "#4a6fa5", "#a3477a", "#d98c3a", "#5a4a7a", "#3f8f8f", "#b8543f", "#6b5b95", "#c9a227"];
const PANTS = ["#2c2430", "#3a2e28", "#26313a", "#33262e"];
const HAIRSTYLES = ["short", "long", "mohawk", "cap"];

function shade(hex, pct) {
  const n = parseInt(hex.slice(1), 16);
  let r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  r = Math.max(0, Math.min(255, Math.round(r * (1 + pct))));
  g = Math.max(0, Math.min(255, Math.round(g * (1 + pct))));
  b = Math.max(0, Math.min(255, Math.round(b * (1 + pct))));
  return `rgb(${r},${g},${b})`;
}

function idIndex(id) {
  // "a7" -> 7 ; fall back to a char hash for non-numeric ids
  const m = /\d+/.exec(id);
  if (m) return parseInt(m[0], 10);
  let h = 0;
  for (const c of id) h = (h * 31 + c.charCodeAt(0)) & 0xffff;
  return h;
}

export function paletteFor(id) {
  const i = idIndex(id);
  return {
    skin: SKIN[i % SKIN.length],
    hair: HAIR[i % HAIR.length],
    shirt: SHIRT[i % SHIRT.length],
    pants: PANTS[i % PANTS.length],
    hairStyle: HAIRSTYLES[i % HAIRSTYLES.length],
    glasses: i % 4 === 2,
  };
}

function drawAgentSprite(palette, holdingDrink) {
  const c = document.createElement("canvas"); c.width = 14; c.height = 22;
  const ctx = c.getContext("2d"); ctx.imageSmoothingEnabled = false;
  ctx.fillStyle = "rgba(0,0,0,0.35)"; ctx.beginPath(); ctx.ellipse(7, 21, 5, 1.4, 0, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = palette.pants;
  ctx.fillRect(4, 15, 2, 4); ctx.fillRect(8, 15, 2, 4);
  ctx.fillStyle = "#1c140f";
  ctx.fillRect(4, 19, 2, 2); ctx.fillRect(8, 19, 2, 2);
  ctx.fillStyle = palette.shirt;
  ctx.fillRect(3, 9, 8, 6);
  ctx.fillStyle = shade(palette.shirt, -0.25);
  ctx.fillRect(2, 10, 1, 4); ctx.fillRect(11, 10, 1, 4);
  ctx.fillStyle = palette.skin;
  ctx.fillRect(5, 4, 4, 4);
  if (palette.hairStyle === "short") { ctx.fillStyle = palette.hair; ctx.fillRect(4, 2, 6, 3); }
  else if (palette.hairStyle === "long") { ctx.fillStyle = palette.hair; ctx.fillRect(4, 2, 6, 3); ctx.fillRect(3, 5, 1, 4); ctx.fillRect(10, 5, 1, 4); }
  else if (palette.hairStyle === "mohawk") { ctx.fillStyle = palette.hair; ctx.fillRect(6, 1, 2, 4); ctx.fillRect(4, 3, 1, 2); ctx.fillRect(9, 3, 1, 2); }
  else { ctx.fillStyle = shade(palette.hair, 0.15); ctx.fillRect(4, 2, 6, 3); ctx.fillRect(3, 4, 8, 1); }
  ctx.fillStyle = "#1c140f";
  ctx.fillRect(6, 6, 1, 1); ctx.fillRect(8, 6, 1, 1);
  if (palette.glasses) { ctx.fillStyle = "rgba(20,20,26,0.85)"; ctx.fillRect(5, 5, 5, 2); }
  if (holdingDrink) {
    ctx.fillStyle = "#f2d98a"; ctx.fillRect(11, 11, 2, 1);
    ctx.fillStyle = "#e8b34d"; ctx.fillRect(11, 12, 2, 2);
  }
  return c.toDataURL();
}

function drawIcon(type) {
  const c = document.createElement("canvas"); c.width = 10; c.height = 10;
  const ctx = c.getContext("2d"); ctx.imageSmoothingEnabled = false;
  if (type === "drink") {
    ctx.fillStyle = "#f2d98a"; ctx.fillRect(1, 1, 8, 1);
    ctx.fillStyle = "#e8b34d";
    ctx.fillRect(2, 2, 6, 1); ctx.fillRect(3, 3, 4, 1); ctx.fillRect(4, 4, 2, 1);
    ctx.fillRect(4, 5, 2, 3); ctx.fillRect(2, 8, 6, 1);
  } else if (type === "bolt") {
    ctx.fillStyle = "#6fb1f2";
    ctx.fillRect(5, 0, 2, 3); ctx.fillRect(3, 3, 3, 2); ctx.fillRect(5, 5, 2, 2); ctx.fillRect(2, 7, 3, 2);
  } else if (type === "star") {
    ctx.fillStyle = "#f2c14e";
    ctx.fillRect(4, 0, 2, 10); ctx.fillRect(0, 4, 10, 2);
    ctx.fillRect(2, 2, 6, 6);
  } else {
    ctx.fillStyle = "#e0607a";
    ctx.beginPath(); ctx.arc(3.2, 3, 2.2, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.arc(6.8, 3, 2.2, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.moveTo(1, 4); ctx.lineTo(5, 9); ctx.lineTo(9, 4); ctx.fill();
  }
  return c.toDataURL();
}

function drawRoom(dark) {
  const W = 320, H = 200;
  const c = document.createElement("canvas"); c.width = W; c.height = H;
  const ctx = c.getContext("2d"); ctx.imageSmoothingEnabled = false;
  const p = dark ? {
    wall: "#3b2a35", floor: "#5a3d2e", floorLine: "#6b4a38", rug: "#7a2e2e", rugBorder: "#5c1f1f",
    bar: "#4a2f22", barTop: "#6b4632", barShelf: "#2a1c16", couch: "#6b3a3a", couchTop: "#8a4c4c", couchShadow: "#4d2626",
    frame: "#2a1c16", sky: "#131022", star: "#f4e7c1", snack: "#5c3a2a", snackTop: "#e8d9b0", wire: "#2a1c16", bulb: "#ffdb7a"
  } : {
    wall: "#e7d9c9", floor: "#c9905f", floorLine: "#b87a4a", rug: "#c96a5a", rugBorder: "#a5493c",
    bar: "#8a6248", barTop: "#a9835f", barShelf: "#5c3d2a", couch: "#9a6b5a", couchTop: "#b98a72", couchShadow: "#7a4c3c",
    frame: "#5c3d2a", sky: "#bfe0f2", star: "#ffffff", snack: "#a9835f", snackTop: "#f0ddb8", wire: "#5c3d2a", bulb: "#ffe9a8"
  };
  ctx.fillStyle = p.floor; ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = p.wall; ctx.fillRect(0, 0, W, 40);
  ctx.fillStyle = p.floorLine;
  for (let y = 44; y < H; y += 9) ctx.fillRect(0, y, W, 1);
  ctx.fillStyle = p.rug; ctx.fillRect(90, 120, 140, 65);
  ctx.fillStyle = p.rugBorder; ctx.fillRect(90, 120, 140, 3); ctx.fillRect(90, 182, 140, 3); ctx.fillRect(90, 120, 3, 65); ctx.fillRect(227, 120, 3, 65);
  ctx.fillStyle = p.frame; ctx.fillRect(18, 6, 58, 30);
  ctx.fillStyle = p.sky; ctx.fillRect(22, 10, 50, 22);
  ctx.fillStyle = p.star;
  if (dark) { [[28, 14], [40, 18], [55, 12], [62, 20], [34, 24]].forEach(([x, y]) => ctx.fillRect(x, y, 1, 1)); }
  else { ctx.beginPath(); ctx.arc(60, 16, 6, 0, Math.PI * 2); ctx.fill(); }
  ctx.fillStyle = p.frame; ctx.fillRect(46, 10, 2, 22); ctx.fillRect(22, 20, 50, 2);
  ctx.fillStyle = p.wire;
  for (let x = 4; x < W - 4; x += 4) ctx.fillRect(x, 3 + Math.round(Math.sin(x / 24) * 2 + 2), 2, 1);
  if (dark) {
    ctx.fillStyle = p.bulb;
    for (let x = 6; x < W - 6; x += 17) {
      const y = 5 + Math.round(Math.sin(x / 24) * 2 + 2);
      ctx.globalAlpha = 0.35; ctx.fillRect(x - 2, y - 1, 5, 3);
      ctx.globalAlpha = 1; ctx.fillRect(x, y, 1, 1);
    }
  }
  ctx.fillStyle = p.barShelf; ctx.fillRect(238, 48, 72, 20);
  const bottles = ["#7fae6b", "#c15c5c", "#e8b34d", "#6fb1f2", "#a3477a"];
  bottles.forEach((col, i) => { ctx.fillStyle = col; ctx.fillRect(244 + i * 13, 52, 5, 12); });
  ctx.fillStyle = p.bar; ctx.fillRect(235, 108, 75, 32);
  ctx.fillStyle = p.barTop; ctx.fillRect(232, 72, 80, 14);
  ctx.fillStyle = p.couchShadow; ctx.fillRect(15, 178, 80, 10);
  ctx.fillStyle = p.couch; ctx.fillRect(15, 155, 80, 28);
  ctx.fillStyle = p.couchTop; ctx.fillRect(15, 150, 80, 10);
  ctx.fillStyle = p.couchShadow; ctx.fillRect(54, 152, 3, 28);
  ctx.fillStyle = p.snack; ctx.fillRect(140, 158, 50, 20);
  ctx.fillStyle = p.snackTop; ctx.fillRect(138, 150, 54, 9);
  const snackDots = ["#c15c5c", "#7fae6b", "#e8b34d", "#f2c46d"];
  snackDots.forEach((col, i) => { ctx.fillStyle = col; ctx.beginPath(); ctx.arc(148 + i * 11, 154, 2, 0, Math.PI * 2); ctx.fill(); });
  if (dark) {
    const grad = ctx.createRadialGradient(W / 2, H / 2, 60, W / 2, H / 2, 220);
    grad.addColorStop(0, "rgba(0,0,0,0)"); grad.addColorStop(1, "rgba(0,0,0,0.4)");
    ctx.fillStyle = grad; ctx.fillRect(0, 0, W, H);
  }
  return c.toDataURL();
}

// --- cached accessors -----------------------------------------------------

const _spriteCache = new Map(); // `${id}|${drink}` -> dataURL
const _roomCache = {};

export function spriteFor(id, holdingDrink) {
  const key = `${id}|${holdingDrink ? 1 : 0}`;
  let url = _spriteCache.get(key);
  if (!url) { url = drawAgentSprite(paletteFor(id), holdingDrink); _spriteCache.set(key, url); }
  return url;
}

export function roomFor(dark) {
  const key = dark ? "dark" : "light";
  if (!_roomCache[key]) _roomCache[key] = drawRoom(dark);
  return _roomCache[key];
}

export const ICONS = {
  drink: drawIcon("drink"),
  bolt: drawIcon("bolt"),
  star: drawIcon("star"),
  heart: drawIcon("heart"),
};

// Central client store: authoritative world truth + a little UI state.
//
// STATE has overwrite / latest-wins semantics — a world_state snapshot fully
// replaces what we knew, which is why reconnecting is self-healing. Each agent
// also carries a *render* position (rx, ry) that the render loop eases toward
// the authoritative (x, y) for smooth motion between snapshots (interpolation).

export const agents = new Map();            // id -> agent view
export const conversationLines = new Map(); // conversation_id -> latest spoken line

// small UI-only state (not world truth; never sent as authority)
export const ui = {
  hoveredId: null, chatId: null, dark: true, paused: false, speed: 1,
  debugOpen: false, debugAgentId: null,
};

export function applySnapshot(snapshot) {
  const seen = new Set();
  for (const a of snapshot.agents) {
    seen.add(a.id);
    let v = agents.get(a.id);
    if (!v) {
      v = { rx: a.pos[0], ry: a.pos[1] }; // start render pos on the real pos
      agents.set(a.id, v);
    }
    v.id = a.id;
    v.name = a.name;
    v.age = a.age;
    v.x = a.pos[0];
    v.y = a.pos[1];
    v.stats = a.stats;
    v.action = a.action;
    v.conversation_id = a.conversation_id;
  }
  for (const id of [...agents.keys()]) {
    if (!seen.has(id)) agents.delete(id);
  }
}

export function noteLine(cid, text) {
  conversationLines.set(cid, text);
}
export function clearLine(cid) {
  conversationLines.delete(cid);
}
